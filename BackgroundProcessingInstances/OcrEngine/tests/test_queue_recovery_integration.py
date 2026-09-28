"""
Integration tests for OcrWorker queue ownership and stale-worker recovery semantics.

This test uses a live Redis instance (preferably an ephemeral Docker container).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

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
            "Missing OCR integration test dependencies: "
            + ", ".join(sorted(missing))
            + ". Install required packages or set OCR_TESTS_REQUIRE_DEPS=0 for local skip behavior."
        )
    return None


_MISSING_DEPS_MESSAGE = _detect_missing_test_deps()
if _MISSING_DEPS_MESSAGE and _STRICT_DEPS:
    raise RuntimeError(_MISSING_DEPS_MESSAGE)
if _MISSING_DEPS_MESSAGE and not _STRICT_DEPS:
    pytestmark = pytest.mark.skip(reason=_MISSING_DEPS_MESSAGE)


def _load_worker_module():
    worker_path = _ocr_src / "worker.py"
    spec = importlib.util.spec_from_file_location(
        "ocr_engine_worker_integration_module",
        worker_path,
    )
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


def _make_worker(worker_mod, client, worker_id: str):
    worker = object.__new__(worker_mod.OcrWorker)
    worker.redis_url = "redis://unused"
    worker.redis_client = client
    worker.max_retries = 3
    worker.worker_id = worker_id
    worker.processing_queue = f"{worker_mod.OCR_PROCESSING_QUEUE_PREFIX}:{worker_id}"
    worker.recovery_lock_ttl_sec = 15
    worker.heartbeat_ttl_sec = 30
    worker.heartbeat_interval_sec = 10.0
    worker.stale_scan_interval_sec = 30.0
    worker._next_stale_recovery_at = time.monotonic() + worker.stale_scan_interval_sec
    return worker


def _import_redis_module() -> Any:
    """Import redis lazily so dependency gating can control skip/fail behavior."""
    import redis  # type: ignore

    return redis


def _reserve_host_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_redis(url: str, timeout_s: float = 20.0):
    redis_mod = _import_redis_module()
    client = redis_mod.Redis.from_url(url, decode_responses=False)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if client.ping():
                return client
        except redis_mod.RedisError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for Redis at {url}")


@pytest.fixture
def live_redis_client():
    """
    Provide a live Redis client.

    Priority:
    1) OCR_REDIS_TEST_URL env var (pre-provisioned Redis)
    2) Ephemeral Docker container (redis:7-alpine), if Docker daemon is available
    """
    external_url = os.getenv("OCR_REDIS_TEST_URL")
    if external_url:
        client = _wait_for_redis(external_url)
        yield client
        return

    if not shutil.which("docker"):
        message = "docker CLI is not installed; skipping live Redis integration test"
        if _STRICT_DEPS:
            pytest.fail(message, pytrace=False)
        pytest.skip(message)

    info = subprocess.run(
        ["docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if info.returncode != 0:
        message = "docker daemon is not accessible; skipping live Redis integration test"
        if _STRICT_DEPS:
            pytest.fail(message, pytrace=False)
        pytest.skip(message)

    port = _reserve_host_port()
    container_name = f"laredo-ocr-redis-test-{uuid.uuid4().hex[:10]}"
    run_cmd = [
        "docker",
        "run",
        "--rm",
        "-d",
        "--name",
        container_name,
        "-p",
        f"{port}:6379",
        "redis:7-alpine",
    ]
    started = subprocess.run(
        run_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if started.returncode != 0:
        message = f"failed to start redis container: {started.stderr.strip()}"
        if _STRICT_DEPS:
            pytest.fail(message, pytrace=False)
        pytest.skip(message)

    redis_url = f"redis://127.0.0.1:{port}/14"
    try:
        client = _wait_for_redis(redis_url)
        yield client
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def _cleanup_worker_keys(client, worker_mod, worker_ids: list[str]) -> None:
    keys = [worker_mod.OCR_QUEUE, worker_mod.OCR_ACTIVE_WORKERS_KEY, worker_mod.OCR_RECOVERY_LOCK_KEY]
    for wid in worker_ids:
        keys.append(f"{worker_mod.OCR_PROCESSING_QUEUE_PREFIX}:{wid}")
        keys.append(f"{worker_mod.OCR_HEARTBEAT_KEY_PREFIX}:{wid}")
    client.delete(*keys)


def test_stale_worker_recovery_requires_missing_heartbeat(live_redis_client) -> None:
    worker_mod = _load_worker_module()
    client = live_redis_client
    worker_a_id = "worker-a"
    worker_b_id = "worker-b"
    _cleanup_worker_keys(client, worker_mod, [worker_a_id, worker_b_id])

    worker_a = _make_worker(worker_mod, client, worker_a_id)
    worker_b = _make_worker(worker_mod, client, worker_b_id)

    payload = json.dumps({"request_id": "int-ocr-4242"}).encode("utf-8")
    client.rpush(worker_mod.OCR_QUEUE, payload)

    claimed = worker_a._claim_task(timeout=1)
    assert claimed == payload
    assert client.llen(worker_mod.OCR_QUEUE) == 0
    assert client.llen(worker_a.processing_queue) == 1

    # Worker A is alive: present heartbeat and active membership.
    client.setex(f"{worker_mod.OCR_HEARTBEAT_KEY_PREFIX}:{worker_a_id}", 30, "1")
    client.sadd(worker_mod.OCR_ACTIVE_WORKERS_KEY, worker_a_id)
    client.sadd(worker_mod.OCR_ACTIVE_WORKERS_KEY, worker_b_id)

    recovered_live = worker_b.recover_stale_worker_tasks()
    assert recovered_live == 0
    assert client.llen(worker_a.processing_queue) == 1
    assert client.llen(worker_mod.OCR_QUEUE) == 0

    # Simulate worker A crash by dropping heartbeat; task should now be recoverable.
    client.delete(f"{worker_mod.OCR_HEARTBEAT_KEY_PREFIX}:{worker_a_id}")
    recovered_stale = worker_b.recover_stale_worker_tasks()
    assert recovered_stale == 1
    assert client.llen(worker_a.processing_queue) == 0
    assert client.llen(worker_mod.OCR_QUEUE) == 1

    reclaimed = worker_b._claim_task(timeout=1)
    assert reclaimed is not None
    assert json.loads(reclaimed.decode("utf-8"))["request_id"] == "int-ocr-4242"
    assert worker_b._ack_task(reclaimed) is True
    assert client.llen(worker_b.processing_queue) == 0
