"""
Unit tests for extraction worker retry/dead-letter behavior.
"""

import json
import sys
from pathlib import Path

import pytest


_project_root = Path(__file__).resolve().parents[3]
_extraction_src = str(
    _project_root / "BackgroundProcessingInstances" / "ExtractionWorker" / "src"
)
if _extraction_src not in sys.path:
    sys.path.insert(0, _extraction_src)

import worker as extraction_worker_module
from worker import (
    EXTRACTION_ACTIVE_WORKERS_KEY,
    EXTRACTION_DLQ,
    EXTRACTION_HEARTBEAT_KEY_PREFIX,
    EXTRACTION_PROCESSING_QUEUE_PREFIX,
    EXTRACTION_QUEUE,
    EXTRACTION_RECOVERY_LOCK_KEY,
    ExtractionWorker,
)


class _FakeRedis:
    def __init__(self):
        self.calls: list[tuple[str, str | bytes]] = []
        self.queues: dict[str, list[str | bytes]] = {
            EXTRACTION_QUEUE: [],
            EXTRACTION_DLQ: [],
        }
        self.kv: dict[str, str | bytes] = {}
        self.sets: dict[str, set[str]] = {EXTRACTION_ACTIVE_WORKERS_KEY: set()}

    def _queue(self, key: str) -> list[str | bytes]:
        return self.queues.setdefault(key, [])

    def rpush(self, queue: str, payload: str | bytes):
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

    def lrem(self, queue: str, count: int, value: str | bytes) -> int:
        items = self._queue(queue)
        if count <= 0:
            raise NotImplementedError("Test fake only supports positive count")

        removed = 0
        kept: list[str | bytes] = []
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
        claimed_payload: str | bytes,
        destination_payload: str | bytes,
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


class _BlmoveUnsupportedRedis(_FakeRedis):
    def execute_command(self, command: str, *args):
        if command == "BLMOVE":
            raise extraction_worker_module.redis.ResponseError("ERR unknown command 'BLMOVE'")
        return super().execute_command(command, *args)


def _processing_queue(worker_id: str) -> str:
    return f"{EXTRACTION_PROCESSING_QUEUE_PREFIX}:{worker_id}"


def _heartbeat_key(worker_id: str) -> str:
    return f"{EXTRACTION_HEARTBEAT_KEY_PREFIX}:{worker_id}"


def test_claim_task_uses_worker_specific_processing_queue():
    fake_redis = _FakeRedis()
    worker = ExtractionWorker(
        "redis://localhost:6379/0",
        "postgresql://db",
        "/tmp",
        worker_id="worker-a",
    )
    worker.redis_client = fake_redis

    payload = json.dumps({"document_id": 444}).encode("utf-8")
    fake_redis.queues[EXTRACTION_QUEUE].append(payload)

    claimed = worker._claim_task(timeout=1)

    assert claimed == payload
    assert fake_redis.queues[EXTRACTION_QUEUE] == []
    assert fake_redis.queues[worker.processing_queue] == [payload]


def test_claim_task_raises_when_blmove_not_supported():
    fake_redis = _BlmoveUnsupportedRedis()
    worker = ExtractionWorker(
        "redis://localhost:6379/0",
        "postgresql://db",
        "/tmp",
        worker_id="worker-a",
    )
    worker.redis_client = fake_redis

    with pytest.raises(RuntimeError, match="BLMOVE"):
        worker._claim_task(timeout=1)


def test_requeue_task_before_max_retries():
    fake_redis = _FakeRedis()
    worker = ExtractionWorker("redis://localhost:6379/0", "postgresql://db", "/tmp", worker_id="worker-a")
    worker.redis_client = fake_redis
    worker.max_retries = 2

    task = {"document_id": 123}
    task_json = json.dumps(task).encode("utf-8")
    fake_redis.queues[worker.processing_queue] = [task_json]
    worker._requeue_or_dead_letter(task_json, task, "temporary failure")

    assert len(fake_redis.calls) == 1
    queue, payload = fake_redis.calls[0]
    assert queue == EXTRACTION_QUEUE
    parsed = json.loads(payload)
    assert parsed["document_id"] == 123
    assert parsed["retries"] == 1
    assert fake_redis.queues[worker.processing_queue] == []


def test_send_task_to_dead_letter_after_max_retries():
    fake_redis = _FakeRedis()
    worker = ExtractionWorker("redis://localhost:6379/0", "postgresql://db", "/tmp", worker_id="worker-a")
    worker.redis_client = fake_redis
    worker.max_retries = 2

    task = {"document_id": 123, "retries": 2}
    task_json = json.dumps(task).encode("utf-8")
    fake_redis.queues[worker.processing_queue] = [task_json]
    worker._requeue_or_dead_letter(task_json, task, "permanent failure")

    assert len(fake_redis.calls) == 1
    queue, payload = fake_redis.calls[0]
    assert queue == EXTRACTION_DLQ
    parsed = json.loads(payload)
    assert parsed["task"]["document_id"] == 123
    assert parsed["task"]["retries"] == 3
    assert fake_redis.queues[worker.processing_queue] == []


def test_recover_inflight_tasks_moves_only_target_worker_queue():
    fake_redis = _FakeRedis()
    worker = ExtractionWorker("redis://localhost:6379/0", "postgresql://db", "/tmp", worker_id="worker-a")
    worker.redis_client = fake_redis

    own_first = b'{"document_id": 1}'
    own_second = b'{"document_id": 2}'
    other_task = b'{"document_id": 3}'
    fake_redis.queues[_processing_queue("worker-a")] = [own_first, own_second]
    fake_redis.queues[_processing_queue("worker-b")] = [other_task]

    recovered = worker.recover_inflight_tasks()

    assert recovered == 2
    assert fake_redis.queues[_processing_queue("worker-a")] == []
    assert fake_redis.queues[_processing_queue("worker-b")] == [other_task]
    assert fake_redis.queues[EXTRACTION_QUEUE][0] == own_first
    assert fake_redis.queues[EXTRACTION_QUEUE][1] == own_second


def test_recover_stale_worker_tasks_skips_live_worker():
    fake_redis = _FakeRedis()
    worker = ExtractionWorker("redis://localhost:6379/0", "postgresql://db", "/tmp", worker_id="worker-b")
    worker.redis_client = fake_redis

    candidate_payload = b'{"document_id": 42}'
    fake_redis.queues[_processing_queue("worker-a")] = [candidate_payload]
    fake_redis.sets[EXTRACTION_ACTIVE_WORKERS_KEY] = {"worker-a", "worker-b"}
    fake_redis.kv[_heartbeat_key("worker-a")] = "1"

    recovered = worker.recover_stale_worker_tasks()

    assert recovered == 0
    assert fake_redis.queues[_processing_queue("worker-a")] == [candidate_payload]
    assert "worker-a" in fake_redis.sets[EXTRACTION_ACTIVE_WORKERS_KEY]


def test_recover_stale_worker_tasks_recovers_expired_worker_queue():
    fake_redis = _FakeRedis()
    worker = ExtractionWorker("redis://localhost:6379/0", "postgresql://db", "/tmp", worker_id="worker-b")
    worker.redis_client = fake_redis

    stale_payload = b'{"document_id": 77}'
    fake_redis.queues[_processing_queue("worker-a")] = [stale_payload]
    fake_redis.sets[EXTRACTION_ACTIVE_WORKERS_KEY] = {"worker-a", "worker-b"}

    recovered = worker.recover_stale_worker_tasks()

    assert recovered == 1
    assert fake_redis.queues[_processing_queue("worker-a")] == []
    assert fake_redis.queues[EXTRACTION_QUEUE] == [stale_payload]
    assert "worker-a" not in fake_redis.sets[EXTRACTION_ACTIVE_WORKERS_KEY]


@pytest.mark.asyncio
async def test_run_loop_acknowledges_successful_task():
    fake_redis = _FakeRedis()
    worker = ExtractionWorker("redis://localhost:6379/0", "postgresql://db", "/tmp", worker_id="worker-a")
    worker.redis_client = fake_redis
    worker.max_retries = 2

    payload = json.dumps({"document_id": 777}).encode("utf-8")
    fake_redis.queues[EXTRACTION_QUEUE].append(payload)

    original_shutdown = extraction_worker_module.shutdown_requested
    extraction_worker_module.shutdown_requested = False
    try:
        async def _process_task(task_data: dict) -> bool:
            assert task_data["document_id"] == 777
            extraction_worker_module.shutdown_requested = True
            return True

        worker.process_task = _process_task
        await worker.run()
    finally:
        extraction_worker_module.shutdown_requested = original_shutdown

    assert fake_redis.queues[EXTRACTION_QUEUE] == []
    assert fake_redis.queues[worker.processing_queue] == []


@pytest.mark.asyncio
async def test_run_loop_requeues_failed_task():
    fake_redis = _FakeRedis()
    worker = ExtractionWorker("redis://localhost:6379/0", "postgresql://db", "/tmp", worker_id="worker-a")
    worker.redis_client = fake_redis
    worker.max_retries = 2

    payload = json.dumps({"document_id": 888}).encode("utf-8")
    fake_redis.queues[EXTRACTION_QUEUE].append(payload)

    original_shutdown = extraction_worker_module.shutdown_requested
    extraction_worker_module.shutdown_requested = False
    try:
        async def _process_task(task_data: dict) -> bool:
            assert task_data["document_id"] == 888
            task_data["last_error"] = "simulated failure"
            extraction_worker_module.shutdown_requested = True
            return False

        worker.process_task = _process_task
        await worker.run()
    finally:
        extraction_worker_module.shutdown_requested = original_shutdown

    assert fake_redis.queues[worker.processing_queue] == []
    assert len(fake_redis.queues[EXTRACTION_QUEUE]) == 1
    requeued = json.loads(fake_redis.queues[EXTRACTION_QUEUE][0])
    assert requeued["document_id"] == 888
    assert requeued["retries"] == 1


@pytest.mark.asyncio
async def test_run_loop_dead_letters_invalid_payload_atomically():
    fake_redis = _FakeRedis()
    worker = ExtractionWorker("redis://localhost:6379/0", "postgresql://db", "/tmp", worker_id="worker-a")
    worker.redis_client = fake_redis
    worker.max_retries = 2

    invalid_payload = b"{not-json"
    fake_redis.queues[EXTRACTION_QUEUE].append(invalid_payload)

    original_shutdown = extraction_worker_module.shutdown_requested
    extraction_worker_module.shutdown_requested = False
    try:
        original_claim = worker._claim_task
        saw_first_claim = False

        def _claim_task_once(timeout: int = 5):
            nonlocal saw_first_claim
            if saw_first_claim:
                extraction_worker_module.shutdown_requested = True
                return None
            saw_first_claim = True
            return original_claim(timeout=timeout)

        worker._claim_task = _claim_task_once
        await worker.run()
    finally:
        extraction_worker_module.shutdown_requested = original_shutdown

    assert fake_redis.queues[worker.processing_queue] == []
    assert fake_redis.queues[EXTRACTION_QUEUE] == []
    assert len(fake_redis.queues[EXTRACTION_DLQ]) == 1
    dlq_entry = json.loads(fake_redis.queues[EXTRACTION_DLQ][0])
    assert "invalid_task_payload" in dlq_entry["error"]
    assert EXTRACTION_RECOVERY_LOCK_KEY not in fake_redis.kv
