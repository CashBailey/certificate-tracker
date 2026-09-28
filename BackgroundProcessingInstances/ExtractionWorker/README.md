# ExtractionWorker

## Purpose
- Template detection and zone-based extraction
- OCR orchestration
- Writes `ExtractionRun` records and artifacts
  - Evidence: `src/pipeline.py:95`, `src/ocr_client.py:66`, `src/worker.py:299`

## Directory Overview
- Architecture: `docs/ARCHITECTURE.md`
- Operations/runbook: `docs/OPERATIONS.md`
- Directory structure map: `docs/DIRECTORY_MAP.md`
- Documentation quick start: `docs/README.md`

## Entrypoint
- Worker process: `python -m src.worker` (details in `docs/OPERATIONS.md`)
  - Evidence: `src/__init__.py:7`, `src/worker.py:428`
- Test workflow: `make test` from repository root (details in `docs/OPERATIONS.md`)
  - Evidence: `../../Makefile:200`, `../../README.md:230`

## Queue Processing Semantics
- Requires Redis with `BLMOVE` support (Redis 6.2+).
- Uses worker-owned processing queues: `extraction_tasks:processing:{WORKER_ID}`.
- Uses heartbeat-based stale worker recovery to avoid cross-worker task stealing.

## Runtime Configuration
- `WORKER_ID` default: `<hostname>-<pid>`
- `WORKER_HEARTBEAT_INTERVAL_SEC` default: `10`
- `WORKER_HEARTBEAT_TTL_SEC` default: `30` (must be > 2x interval)
- `WORKER_RECOVERY_LOCK_TTL_SEC` default: `15`
- `WORKER_STALE_SCAN_INTERVAL_SEC` default: `30`

## Validation Commands
- Authoritative queue gate (Docker runtime): `make test-worker-queues-docker`
- Host-only preflight (optional): `make test-worker-queues-host`
