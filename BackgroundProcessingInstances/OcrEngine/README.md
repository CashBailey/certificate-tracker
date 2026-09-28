# OcrEngine

Purpose

- OCR engine runtime or adapter service

Expected contents

- OCR configuration
- Language packs or models
- Service integration notes

## Directory overview

This directory contains the OCR worker implementation and its Python dependency manifest.

- Runtime code: `src/`
- Python dependencies: `requirements.txt`
- Developer docs: `docs/README.md`, `docs/DIRECTORY_MAP.md`, `docs/OPERATIONS.md`, `docs/ARCHITECTURE.md`

## Quick start

Full stack (recommended, from repository root):

```bash
cd ../..
make up
make logs-workers
```

Standalone (from this directory):

```bash
python -m pip install -r requirements.txt
python -m src.worker
```

Project test suite (from repository root):

```bash
cd ../..
make test
```

Queue/recovery test dependencies (host preflight, optional):

```bash
python3 scripts/check_ocr_test_deps.py --profile tesseract --format text
```

Run OCR queue/recovery tests directly:

```bash
python3 -m pytest BackgroundProcessingInstances/OcrEngine/tests -q
```

Strict mode (recommended for CI) fails instead of skipping when dependencies are missing:

```bash
OCR_TESTS_REQUIRE_DEPS=1 python3 -m pytest BackgroundProcessingInstances/OcrEngine/tests -q
```

Authoritative queue gate (Docker runtime, recommended for release checks):

```bash
make test-worker-queues-docker
```

Runtime configuration (optional overrides):
- `REDIS_URL` default: `rediss://redis:6380/0` (TLS); use `redis://localhost:6380/0` for standalone non-TLS mode
- `TESSERACT_LANG` default: `eng+spa`
- `shared.models` must be importable (shared source in `../../CoreInstances/ApiServer/src/shared/models.py`)
- Redis must support `BLMOVE` (Redis 6.2+)
- `WORKER_ID` default: `<hostname>-<pid>`
- `WORKER_HEARTBEAT_INTERVAL_SEC` default: `10`
- `WORKER_HEARTBEAT_TTL_SEC` default: `30` (must be > 2x interval)
- `WORKER_RECOVERY_LOCK_TTL_SEC` default: `15`
- `WORKER_STALE_SCAN_INTERVAL_SEC` default: `30`
