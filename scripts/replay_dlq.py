#!/usr/bin/env python3
"""Inspect and replay dead-lettered worker tasks.

The extraction and OCR workers push exhausted tasks to Redis dead-letter
queues (`extraction_tasks:dead_letter`, `ocr_tasks:dead_letter`) but nothing
consumes them. This tool lists DLQ contents and re-enqueues tasks onto their
origin queue with the retry counter reset.

Run inside the api container (has REDIS_URL + mTLS client certs):

    docker compose exec api python3 /data/scripts/replay_dlq.py extraction list
    docker compose exec api python3 /data/scripts/replay_dlq.py extraction replay
    docker compose exec api python3 /data/scripts/replay_dlq.py ocr replay --limit 5

Replay pushes the task to the origin queue BEFORE removing the DLQ entry, so
a crash mid-replay can duplicate a task but never lose one. Workers are
idempotent, so duplicates are safe.
"""

import argparse
import json
import os
import sys

QUEUES = {
    "extraction": ("extraction_tasks:dead_letter", "extraction_tasks"),
    "ocr": ("ocr_tasks:dead_letter", "ocr_tasks"),
}


def make_client():
    import redis

    # src.shared.tls lives at /app in the api container; workers mount it as /app/shared.
    sys.path.insert(0, "/app")
    try:
        from src.shared.tls import redis_tls_kwargs
    except ImportError:
        from shared.tls import redis_tls_kwargs

    url = os.environ.get("REDIS_URL")
    if not url:
        sys.exit("REDIS_URL is not set")
    return redis.from_url(url, **redis_tls_kwargs())


def _summarize(raw: bytes) -> str:
    try:
        entry = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "<unparseable entry>"
    task = entry.get("task") or {}
    ident = task.get("document_id") or task.get("request_id") or "-"
    replayable = "yes" if isinstance(task, dict) and task else "NO (no task payload)"
    return (
        f"id={ident} failed_at={entry.get('failed_at', '-')} "
        f"replayable={replayable} error={str(entry.get('error', ''))[:120]}"
    )


def list_entries(client, dlq: str) -> int:
    entries = client.lrange(dlq, 0, -1)
    print(f"{dlq}: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}")
    for i, raw in enumerate(entries):
        print(f"  [{i}] {_summarize(raw)}")
    return 0


def replay(client, dlq: str, origin: str, limit: int | None) -> int:
    total = client.llen(dlq)
    to_process = total if limit is None else min(total, limit)
    replayed = skipped = 0

    for _ in range(to_process):
        raw = client.lindex(dlq, 0)
        if raw is None:
            break
        task = None
        try:
            entry = json.loads(raw)
            candidate = entry.get("task")
            if isinstance(candidate, dict) and candidate:
                task = candidate
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

        if task is None:
            # Unreplayable (invalid original payload) - rotate to the tail so
            # the scan can continue; the entry stays in the DLQ for forensics.
            client.lrem(dlq, 1, raw)
            client.rpush(dlq, raw)
            skipped += 1
            continue

        task["retries"] = 0
        client.rpush(origin, json.dumps(task))
        client.lrem(dlq, 1, raw)
        replayed += 1
        ident = task.get("document_id") or task.get("request_id") or "-"
        print(f"replayed id={ident} -> {origin}")

    print(f"done: {replayed} replayed, {skipped} skipped (kept in {dlq})")
    return 0


class _FakeRedis:
    """Minimal list-command fake for --self-test (no external deps)."""

    def __init__(self):
        self.lists: dict[str, list[bytes]] = {}

    def _l(self, key):
        return self.lists.setdefault(key, [])

    def llen(self, key):
        return len(self._l(key))

    def lindex(self, key, i):
        lst = self._l(key)
        return lst[i] if -len(lst) <= i < len(lst) else None

    def lrange(self, key, start, stop):
        lst = self._l(key)
        stop = len(lst) if stop == -1 else stop + 1
        return lst[start:stop]

    def rpush(self, key, val):
        self._l(key).append(val if isinstance(val, bytes) else val.encode())

    def lrem(self, key, count, val):
        val = val if isinstance(val, bytes) else val.encode()
        lst = self._l(key)
        if val in lst:
            lst.remove(val)
            return 1
        return 0


def self_test() -> int:
    fake = _FakeRedis()
    dlq, origin = "dlq", "main"
    good = json.dumps({"task": {"document_id": 7, "retries": 3}, "error": "boom"})
    bad = json.dumps({"error": "invalid_task_payload", "failed_at": "x"})
    fake.rpush(dlq, bad)
    fake.rpush(dlq, good)
    fake.rpush(dlq, good)

    replay(fake, dlq, origin, limit=None)

    assert fake.llen(origin) == 2, "both good entries replayed"
    assert fake.llen(dlq) == 1, "bad entry kept in DLQ"
    replayed_task = json.loads(fake.lindex(origin, 0))
    assert replayed_task["retries"] == 0, "retry counter reset"
    assert replayed_task["document_id"] == 7

    replay(fake, dlq, origin, limit=None)
    assert fake.llen(dlq) == 1, "bad entry survives repeat replay without looping"
    print("self-test OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("queue", choices=[*QUEUES, "self-test"])
    parser.add_argument("command", nargs="?", choices=["list", "replay"], default="list")
    parser.add_argument("--limit", type=int, default=None, help="max tasks to replay")
    args = parser.parse_args()

    if args.queue == "self-test":
        return self_test()

    dlq, origin = QUEUES[args.queue]
    client = make_client()
    if args.command == "replay":
        return replay(client, dlq, origin, args.limit)
    return list_entries(client, dlq)


if __name__ == "__main__":
    sys.exit(main())
