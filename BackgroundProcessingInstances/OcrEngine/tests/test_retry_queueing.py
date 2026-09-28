"""
Unit tests for OCR worker retry/dead-letter behavior.
"""

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest


_project_root = Path(__file__).resolve().parents[3]
_api_src = _project_root / "CoreInstances" / "ApiServer" / "src"
_ocr_src = _project_root / "BackgroundProcessingInstances" / "OcrEngine" / "src"
for _path in (_api_src, _ocr_src):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

_STRICT_DEPS = os.getenv("OCR_TESTS_REQUIRE_DEPS", "0") == "1"


def _detect_missing_test_deps() -> str | None:
    missing: list[str] = []
    for module_name in ("redis", "structlog", "PIL", "pytesseract"):
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)

    if missing:
        return (
            "Missing OCR test dependencies: "
            + ", ".join(sorted(missing))
            + ". Install required packages or set OCR_TESTS_REQUIRE_DEPS=0 for local skip behavior."
        )
    return None


_MISSING_DEPS_MESSAGE = _detect_missing_test_deps()
if _MISSING_DEPS_MESSAGE and _STRICT_DEPS:
    raise RuntimeError(_MISSING_DEPS_MESSAGE)
if _MISSING_DEPS_MESSAGE and not _STRICT_DEPS:
    pytestmark = pytest.mark.skip(reason=_MISSING_DEPS_MESSAGE)


class _FakeRedis:
    def __init__(self, worker_mod):
        self.calls: list[tuple[str, bytes | str]] = []
        self.queues: dict[str, list[bytes | str]] = {
            worker_mod.OCR_QUEUE: [],
            worker_mod.OCR_DLQ: [],
        }
        self.kv: dict[str, bytes | str] = {}
        self.sets: dict[str, set[str]] = {worker_mod.OCR_ACTIVE_WORKERS_KEY: set()}

    def _queue(self, key: str) -> list[bytes | str]:
        return self.queues.setdefault(key, [])

    def rpush(self, queue: str, payload):
        self.calls.append((queue, payload))
        self._queue(queue).append(payload)

    def execute_command(self, command: str, *args):
        if command == "BLMOVE":
            source_queue, destination_queue, from_side, to_side, _timeout = args
            if from_side != "LEFT" or to_side != "RIGHT":
                raise NotImplementedError("Test fake only supports LEFT->RIGHT moves")
            source = self._queue(source_queue)
            if not source:
                return None
            item = source.pop(0)
            self._queue(destination_queue).append(item)
            return item

        if command == "COMMAND" and len(args) == 2 and args[0] == "INFO" and args[1] == "BLMOVE":
            return [[b"blmove", 6, [b"write", b"blocking"]]]

        raise NotImplementedError(f"Unsupported command: {command}")

    def lrem(self, queue: str, count: int, value: bytes | str) -> int:
        items = self._queue(queue)
        if count <= 0:
            raise NotImplementedError("Test fake only supports positive count")

        removed = 0
        kept: list[bytes | str] = []
        for item in items:
            if removed < count and item == value:
                removed += 1
                continue
            kept.append(item)
        self.queues[queue] = kept
        return removed

    def eval(
        self,
        _script: str,
        _num_keys: int,
        processing_queue: str,
        destination_queue: str,
        claimed_payload: bytes | str,
        destination_payload: bytes | str,
    ) -> int:
        removed = self.lrem(processing_queue, 1, claimed_payload)
        if removed > 0:
            self.rpush(destination_queue, destination_payload)
        return removed

    def rpoplpush(self, source_queue: str, destination_queue: str):
        source = self._queue(source_queue)
        if not source:
            return None
        item = source.pop()
        self._queue(destination_queue).insert(0, item)
        return item

    def setex(self, key: str, _ttl: int, value: str):
        self.kv[key] = value

    def sadd(self, key: str, value: str):
        self.sets.setdefault(key, set()).add(value)

    def smembers(self, key: str):
        return self.sets.get(key, set())

    def srem(self, key: str, value: str):
        self.sets.setdefault(key, set()).discard(value)

    def exists(self, key: str) -> int:
        return 1 if key in self.kv else 0

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        _ = ex
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        return True

    def get(self, key: str):
        return self.kv.get(key)

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.kv:
                del self.kv[key]
                removed += 1
            if key in self.queues:
                del self.queues[key]
                removed += 1
            if key in self.sets:
                del self.sets[key]
                removed += 1
        return removed


def _load_worker_module():
    worker_path = _ocr_src / "worker.py"
    spec = importlib.util.spec_from_file_location("ocr_engine_worker_test_module", worker_path)
    if not spec or not spec.loader:
        message = "Could not load OCR worker module"
        if _STRICT_DEPS:
            pytest.fail(message, pytrace=False)
        pytest.skip(message)

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        message = f"OCR worker dependencies are not installed: {exc}"
        if _STRICT_DEPS:
            pytest.fail(message, pytrace=False)
        pytest.skip(message)
    return module


def _build_worker(worker_mod, fake_redis: _FakeRedis, worker_id: str):
    worker = object.__new__(worker_mod.OcrWorker)
    worker.redis_client = fake_redis
    worker.max_retries = 2
    worker.worker_id = worker_id
    worker.processing_queue = f"{worker_mod.OCR_PROCESSING_QUEUE_PREFIX}:{worker_id}"
    worker.stale_scan_interval_sec = 30.0
    worker._next_stale_recovery_at = time.monotonic() + worker.stale_scan_interval_sec
    worker.recovery_lock_ttl_sec = 15
    worker.heartbeat_ttl_sec = 30
    worker.heartbeat_interval_sec = 10.0
    return worker


def test_claim_task_uses_worker_specific_processing_queue():
    worker_mod = _load_worker_module()
    fake_redis = _FakeRedis(worker_mod)
    worker = _build_worker(worker_mod, fake_redis, "worker-a")

    payload = json.dumps({"request_id": "claim-1"}).encode("utf-8")
    fake_redis.queues[worker_mod.OCR_QUEUE].append(payload)

    claimed = worker._claim_task(timeout=1)

    assert claimed == payload
    assert fake_redis.queues[worker_mod.OCR_QUEUE] == []
    assert fake_redis.queues[worker.processing_queue] == [payload]


def test_claim_task_raises_when_blmove_not_supported():
    worker_mod = _load_worker_module()
    fake_redis = _FakeRedis(worker_mod)
    worker = _build_worker(worker_mod, fake_redis, "worker-a")
    original_execute = fake_redis.execute_command

    def _unsupported_blmove(command: str, *args):
        if command == "BLMOVE":
            raise worker_mod.redis.ResponseError("ERR unknown command 'BLMOVE'")
        return original_execute(command, *args)

    fake_redis.execute_command = _unsupported_blmove

    with pytest.raises(RuntimeError, match="BLMOVE"):
        worker._claim_task(timeout=1)


def test_requeue_ocr_task_before_max_retries():
    worker_mod = _load_worker_module()
    fake_redis = _FakeRedis(worker_mod)
    worker = _build_worker(worker_mod, fake_redis, "worker-a")

    task = {
        "request_id": "abc-123",
        "page_num": 1,
        "image_b64": "ZmFrZQ==",
        "width_px": 100,
        "height_px": 100,
        "dpi": 300,
        "bbox_norm": [0.0, 0.0, 1.0, 1.0],
    }
    encoded = json.dumps(task).encode("utf-8")
    fake_redis.queues[worker.processing_queue] = [encoded]
    worker._requeue_or_dead_letter(encoded, "temporary failure")

    assert len(fake_redis.calls) == 1
    queue, payload = fake_redis.calls[0]
    assert queue == worker_mod.OCR_QUEUE
    parsed = json.loads(payload.decode("utf-8"))
    assert parsed["request_id"] == "abc-123"
    assert parsed["retries"] == 1
    assert fake_redis.queues[worker.processing_queue] == []


def test_send_ocr_task_to_dead_letter_after_max_retries():
    worker_mod = _load_worker_module()
    fake_redis = _FakeRedis(worker_mod)
    worker = _build_worker(worker_mod, fake_redis, "worker-a")
    worker.max_retries = 1

    task = {
        "request_id": "abc-123",
        "page_num": 1,
        "image_b64": "ZmFrZQ==",
        "width_px": 100,
        "height_px": 100,
        "dpi": 300,
        "bbox_norm": [0.0, 0.0, 1.0, 1.0],
        "retries": 1,
    }
    encoded = json.dumps(task).encode("utf-8")
    fake_redis.queues[worker.processing_queue] = [encoded]
    worker._requeue_or_dead_letter(encoded, "permanent failure")

    assert len(fake_redis.calls) == 1
    queue, payload = fake_redis.calls[0]
    assert queue == worker_mod.OCR_DLQ
    parsed = json.loads(payload)
    assert parsed["task"]["request_id"] == "abc-123"
    assert parsed["task"]["retries"] == 2
    assert "image_b64" not in parsed["task"]
    assert parsed["image_b64_chars"] == len(task["image_b64"])
    assert fake_redis.queues[worker.processing_queue] == []


def test_recover_inflight_tasks_moves_only_target_worker_queue():
    worker_mod = _load_worker_module()
    fake_redis = _FakeRedis(worker_mod)
    worker = _build_worker(worker_mod, fake_redis, "worker-a")

    first = b'{"request_id":"a"}'
    second = b'{"request_id":"b"}'
    other = b'{"request_id":"c"}'
    fake_redis.queues[f"{worker_mod.OCR_PROCESSING_QUEUE_PREFIX}:worker-a"] = [first, second]
    fake_redis.queues[f"{worker_mod.OCR_PROCESSING_QUEUE_PREFIX}:worker-b"] = [other]

    recovered = worker.recover_inflight_tasks()

    assert recovered == 2
    assert fake_redis.queues[f"{worker_mod.OCR_PROCESSING_QUEUE_PREFIX}:worker-a"] == []
    assert fake_redis.queues[f"{worker_mod.OCR_PROCESSING_QUEUE_PREFIX}:worker-b"] == [other]
    assert fake_redis.queues[worker_mod.OCR_QUEUE][0] == first
    assert fake_redis.queues[worker_mod.OCR_QUEUE][1] == second


def test_recover_stale_worker_tasks_skips_live_worker():
    worker_mod = _load_worker_module()
    fake_redis = _FakeRedis(worker_mod)
    worker = _build_worker(worker_mod, fake_redis, "worker-b")

    stale_queue = f"{worker_mod.OCR_PROCESSING_QUEUE_PREFIX}:worker-a"
    heartbeat_key = f"{worker_mod.OCR_HEARTBEAT_KEY_PREFIX}:worker-a"
    fake_redis.queues[stale_queue] = [b'{"request_id":"x"}']
    fake_redis.sets[worker_mod.OCR_ACTIVE_WORKERS_KEY] = {"worker-a", "worker-b"}
    fake_redis.kv[heartbeat_key] = "1"

    recovered = worker.recover_stale_worker_tasks()

    assert recovered == 0
    assert fake_redis.queues[stale_queue] == [b'{"request_id":"x"}']
    assert "worker-a" in fake_redis.sets[worker_mod.OCR_ACTIVE_WORKERS_KEY]


def test_recover_stale_worker_tasks_recovers_expired_worker_queue():
    worker_mod = _load_worker_module()
    fake_redis = _FakeRedis(worker_mod)
    worker = _build_worker(worker_mod, fake_redis, "worker-b")

    stale_queue = f"{worker_mod.OCR_PROCESSING_QUEUE_PREFIX}:worker-a"
    fake_redis.queues[stale_queue] = [b'{"request_id":"y"}']
    fake_redis.sets[worker_mod.OCR_ACTIVE_WORKERS_KEY] = {"worker-a", "worker-b"}

    recovered = worker.recover_stale_worker_tasks()

    assert recovered == 1
    assert fake_redis.queues[stale_queue] == []
    assert fake_redis.queues[worker_mod.OCR_QUEUE] == [b'{"request_id":"y"}']
    assert "worker-a" not in fake_redis.sets[worker_mod.OCR_ACTIVE_WORKERS_KEY]


def test_run_loop_acknowledges_successful_task(monkeypatch: pytest.MonkeyPatch):
    worker_mod = _load_worker_module()
    fake_redis = _FakeRedis(worker_mod)
    worker = _build_worker(worker_mod, fake_redis, "worker-a")

    payload = json.dumps({"request_id": "ok-1"}).encode("utf-8")
    fake_redis.queues[worker_mod.OCR_QUEUE].append(payload)

    original_shutdown = worker_mod.shutdown_requested
    worker_mod.shutdown_requested = False
    try:
        def _process_task(task_data: bytes) -> bool:
            assert json.loads(task_data.decode("utf-8"))["request_id"] == "ok-1"
            worker_mod.shutdown_requested = True
            return True

        worker.process_task = _process_task
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        worker.run()
    finally:
        worker_mod.shutdown_requested = original_shutdown

    assert fake_redis.queues[worker_mod.OCR_QUEUE] == []
    assert fake_redis.queues[worker.processing_queue] == []


def test_run_loop_requeues_failed_task(monkeypatch: pytest.MonkeyPatch):
    worker_mod = _load_worker_module()
    fake_redis = _FakeRedis(worker_mod)
    worker = _build_worker(worker_mod, fake_redis, "worker-a")

    payload = json.dumps({"request_id": "fail-1"}).encode("utf-8")
    fake_redis.queues[worker_mod.OCR_QUEUE].append(payload)

    original_shutdown = worker_mod.shutdown_requested
    worker_mod.shutdown_requested = False
    try:
        def _process_task(_task_data: bytes) -> bool:
            worker_mod.shutdown_requested = True
            return False

        worker.process_task = _process_task
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        worker.run()
    finally:
        worker_mod.shutdown_requested = original_shutdown

    assert fake_redis.queues[worker.processing_queue] == []
    assert len(fake_redis.queues[worker_mod.OCR_QUEUE]) == 1
    requeued = json.loads(fake_redis.queues[worker_mod.OCR_QUEUE][0].decode("utf-8"))
    assert requeued["request_id"] == "fail-1"
    assert requeued["retries"] == 1
