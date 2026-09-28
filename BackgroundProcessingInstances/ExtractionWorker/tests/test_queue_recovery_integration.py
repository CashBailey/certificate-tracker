"""
Integration tests for ExtractionWorker queue ownership and stale-worker recovery semantics.

These tests use a live Redis instance (preferably an ephemeral Docker container).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import redis


_project_root = Path(__file__).resolve().parents[3]
_extraction_src = str(
    _project_root / "BackgroundProcessingInstances" / "ExtractionWorker" / "src"
)
if _extraction_src not in sys.path:
    sys.path.insert(0, _extraction_src)

_STRICT_DOCKER = os.getenv("EXTRACTION_TESTS_REQUIRE_DOCKER", "0") == "1"

from worker import (
    EXTRACTION_ACTIVE_WORKERS_KEY,
    EXTRACTION_HEARTBEAT_KEY_PREFIX,
    EXTRACTION_PROCESSING_QUEUE_PREFIX,
    EXTRACTION_QUEUE,
    EXTRACTION_RECOVERY_LOCK_KEY,
    ExtractionWorker,
)


def _processing_queue(worker_id: str) -> str:
    return f"{EXTRACTION_PROCESSING_QUEUE_PREFIX}:{worker_id}"


def _heartbeat_key(worker_id: str) -> str:
    return f"{EXTRACTION_HEARTBEAT_KEY_PREFIX}:{worker_id}"


def _reserve_host_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_redis(url: str, timeout_s: float = 20.0) -> redis.Redis:
    client = redis.Redis.from_url(url, decode_responses=False)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if client.ping():
                return client
        except redis.RedisError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for Redis at {url}")


@pytest.fixture
def live_redis_client():
    """
    Provide a live Redis client.

    Priority:
    1) EXTRACTION_REDIS_TEST_URL env var (pre-provisioned Redis)
    2) Ephemeral Docker container (redis:7-alpine), if Docker daemon is available
    """
    external_url = os.getenv("EXTRACTION_REDIS_TEST_URL")
    if external_url:
        client = _wait_for_redis(external_url)
        yield client
        return

    if not shutil.which("docker"):
        message = "docker CLI is not installed; skipping live Redis integration test"
        if _STRICT_DOCKER:
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
        if _STRICT_DOCKER:
            pytest.fail(message, pytrace=False)
        pytest.skip(message)

    port = _reserve_host_port()
    container_name = f"laredo-extraction-redis-test-{uuid.uuid4().hex[:10]}"
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
        if _STRICT_DOCKER:
            pytest.fail(message, pytrace=False)
        pytest.skip(message)

    redis_url = f"redis://127.0.0.1:{port}/15"
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


def _cleanup_worker_keys(client: redis.Redis, worker_ids: list[str]) -> None:
    keys = [EXTRACTION_QUEUE, EXTRACTION_ACTIVE_WORKERS_KEY, EXTRACTION_RECOVERY_LOCK_KEY]
    for wid in worker_ids:
        keys.append(_processing_queue(wid))
        keys.append(_heartbeat_key(wid))
    client.delete(*keys)


def test_stale_worker_recovery_requires_missing_heartbeat(live_redis_client: redis.Redis) -> None:
    client = live_redis_client
    worker_a_id = "worker-a"
    worker_b_id = "worker-b"
    _cleanup_worker_keys(client, [worker_a_id, worker_b_id])

    redis_url = (
        f"redis://{client.connection_pool.connection_kwargs['host']}:"
        f"{client.connection_pool.connection_kwargs['port']}/"
        f"{client.connection_pool.connection_kwargs['db']}"
    )

    worker_a = ExtractionWorker(redis_url, "postgresql://unused", "/tmp", worker_id=worker_a_id)
    worker_a.redis_client = client
    worker_b = ExtractionWorker(redis_url, "postgresql://unused", "/tmp", worker_id=worker_b_id)
    worker_b.redis_client = client

    payload = json.dumps({"document_id": 4242}).encode("utf-8")
    client.rpush(EXTRACTION_QUEUE, payload)

    claimed = worker_a._claim_task(timeout=1)
    assert claimed == payload
    assert client.llen(EXTRACTION_QUEUE) == 0
    assert client.llen(_processing_queue(worker_a_id)) == 1

    # Worker A is alive: present heartbeat and active membership.
    client.setex(_heartbeat_key(worker_a_id), 30, "1")
    client.sadd(EXTRACTION_ACTIVE_WORKERS_KEY, worker_a_id)
    client.sadd(EXTRACTION_ACTIVE_WORKERS_KEY, worker_b_id)

    recovered_live = worker_b.recover_stale_worker_tasks()
    assert recovered_live == 0
    assert client.llen(_processing_queue(worker_a_id)) == 1
    assert client.llen(EXTRACTION_QUEUE) == 0

    # Simulate worker A crash by dropping heartbeat; task should now be recoverable.
    client.delete(_heartbeat_key(worker_a_id))
    recovered_stale = worker_b.recover_stale_worker_tasks()
    assert recovered_stale == 1
    assert client.llen(_processing_queue(worker_a_id)) == 0
    assert client.llen(EXTRACTION_QUEUE) == 1

    reclaimed = worker_b._claim_task(timeout=1)
    assert reclaimed is not None
    assert json.loads(reclaimed.decode("utf-8"))["document_id"] == 4242
    assert worker_b._ack_task(reclaimed) is True
    assert client.llen(_processing_queue(worker_b_id)) == 0
