# Operations

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Setup Prerequisites
| Requirement | Required | Version/Source | Evidence | Notes |
|---|---|---|---|---|
| Python runtime | Yes | Container: Python 3.12 (`python:3.12-slim-bookworm`); local version not pinned in this directory | `../../docker/workers/ocr/Dockerfile:4`, `requirements.txt:1` | Standalone local runs are possible; container runtime is explicitly pinned. |
| Redis | Yes | URL defaults to `rediss://redis:6380/0` (TLS); use `redis://localhost:6380/0` for standalone non-TLS mode | `src/worker.py:207`, `src/worker.py:99`, `src/worker.py:183` | Worker blocks on Redis queue for tasks. |
| Tesseract OCR binaries | Yes | Installed in OCR container image | `../../docker/workers/ocr/Dockerfile:13`, `../../docker/workers/ocr/Dockerfile:14`, `../../docker/workers/ocr/Dockerfile:15` | Local host package/version is not pinned here. |
| Shared models package | Yes | `../../CoreInstances/ApiServer/src/shared/models.py` | `src/ocr_service.py:14`, `../../CoreInstances/ApiServer/src/shared/models.py:413`, `../../CoreInstances/ApiServer/src/shared/models.py:422` | Needed for `PageImage` and `TextSpan`. |
| EasyOCR + Torch | Custom image only | Excluded from the standard lock/image | `requirements.txt`, `src/worker.py` | Requires explicit `OCR_ENABLE_EASYOCR=true` and an operator-approved timeout/resource policy; otherwise Tesseract is used. |

## Command Provenance
| Command | Status | Evidence |
|---|---|---|
| `python -m pip install -r requirements.txt` | Verified in dependency manifest | `requirements.txt:1` |
| `python -m src.worker` | Verified entrypoint | `src/worker.py:202`, `src/worker.py:232`, `../../docker/workers/ocr/Dockerfile:46` |
| `cd ../.. && make up` | Verified project-level startup command | `../../README.md:62`, `../../Makefile:85` |
| `cd ../.. && make logs-workers` | Verified project-level logs command (includes OCR worker) | `../../Makefile:118` |

## Install
### Standalone install in this directory
```bash
python -m pip install -r requirements.txt
```
Evidence: `requirements.txt:1`.

### Full-stack install/build from repository root
```bash
cd ../..
make setup
make up
```
Evidence: `../../README.md:59`, `../../README.md:62`, `../../Makefile:65`, `../../Makefile:85`.

## Run Modes
### 1) Full-stack container mode (recommended)
```bash
cd ../..
make up
make logs-workers
```
This starts the compose-defined `ocr-engine` service and streams worker logs with the other workers. Evidence: `../../docker-compose.yml:261`, `../../docker-compose.yml:265`, `../../Makefile:118`.

### 2) Standalone Python process mode (from this directory)
```bash
python -m src.worker
```
Behavior:
- Consumes queue key `ocr_tasks`.
- Publishes result key `ocr_results:{request_id}` using `SETEX` with 300-second TTL.
- Handles `SIGTERM`/`SIGINT` for graceful shutdown.
Evidence: `src/worker.py:183`, `src/worker.py:162`, `src/worker.py:165`, `src/worker.py:204`, `src/worker.py:205`.

Note for standalone mode:
- Ensure `shared.models` is importable in your runtime environment (this directory does not contain the `shared` package). Evidence: `src/ocr_service.py:14`, `../../CoreInstances/ApiServer/src/shared/models.py:413`.

### 3) Library mode (no worker loop)
Import and call service classes directly:
- `TesseractOcrService`
- `EasyOcrService`
- `EnsembleOcrEngine`
Evidence: `src/ocr_service.py:17`, `src/easyocr_service.py:17`, `src/ensemble_ocr.py:18`.

## Testing
- Directory-local test command/config: Unknown in this directory scope (no test runner config file is present here).
Evidence: `README.md:1`, `requirements.txt:1`, `src/worker.py:1`.

- Related OCR tests exist in the API component:
  - `../../CoreInstances/ApiServer/tests/integration/test_ocr_pipeline.py`
  - `../../CoreInstances/ApiServer/tests/ocr/test_ocr_preprocessed.py`
Evidence: `../../CoreInstances/ApiServer/tests/integration/test_ocr_pipeline.py:1`, `../../CoreInstances/ApiServer/tests/ocr/test_ocr_preprocessed.py:1`.

- Project-level test command:
```bash
cd ../..
make test
```
Evidence: `../../Makefile:200`, `../../Makefile:201`.

## Lint/Format
- Project-level lint command:
```bash
cd ../..
make lint
```
Evidence: `../../Makefile:206`, `../../Makefile:207`.

Note:
- `make lint` runs `ruff` in API `src/` path from root Makefile; this directory does not define an OCR-specific lint target. Evidence: `../../Makefile:207`.

## Build/Release
### Development compose build
- OCR worker image is built from `../../docker/workers/ocr/Dockerfile` via `ocr-engine` service in `../../docker-compose.yml`.
Evidence: `../../docker-compose.yml:262`, `../../docker-compose.yml:264`.

### Production compose release
- Production compose expects prebuilt image `laredo-certs/ocr-engine:latest`.
Evidence: `../../docker-compose.prod.yml:218`, `../../docker-compose.prod.yml:219`.

## Environment Variables
| Name | Required | Default | Where used | Notes |
|---|---|---|---|---|
| `REDIS_URL` | No | `rediss://redis:6380/0` (compose default) | `src/worker.py` (`os.getenv` and Redis connect) | Core connection setting. Use `rediss://` (TLS) scheme; plain `redis://` only when `TLS_ENABLED=false`. Evidence: `src/worker.py:207`, `src/worker.py:99`. |
| `TESSERACT_LANG` | No | `eng+spa` (code default) | `src/worker.py` -> `TesseractOcrService` | OCR language selection. Evidence: `src/worker.py:208`, `src/worker.py:80`, `../../.env.example:50`. |
| `PYTHONPATH` | Container-required | `/app` (Dockerfile) | Container runtime import path for `shared` + `src` | Ensures imports resolve in containerized mode. Evidence: `../../docker/workers/ocr/Dockerfile:9`, `../../docker/workers/ocr/Dockerfile:36`. |
| `LOG_LEVEL` | No | `INFO` | `src/worker.py` | Read at worker startup; sets root logging level for structlog filter_by_level processor. Evidence: `src/worker.py:17`. |
| `TLS_ENABLED` | No | `true` | Redis TLS toggle | Enable mutual TLS for Redis connection. Set `false` for plain-TCP debugging only. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CA_CERT` | No | `/tls/ca.crt` | Redis TLS | CA certificate path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CLIENT_CERT` | No | `/tls/client.crt` | Redis TLS | Client certificate path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CLIENT_KEY` | No | `/tls/client.key` | Redis TLS | Client private key path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |

## Queue And Payload Contracts
| Contract | Defined in | Evidence |
|---|---|---|
| Input queue key | Worker and OCR client | `src/worker.py:183`, `../ExtractionWorker/src/ocr_client.py:66` |
| Result key pattern | Worker and OCR client | `src/worker.py:162`, `../ExtractionWorker/src/ocr_client.py:69` |
| Result key cleanup | OCR client deletes key after read | `../ExtractionWorker/src/ocr_client.py:79`, `../ExtractionWorker/src/ocr_client.py:128` |
| Request payload schema | Serializer in OCR service | `src/ocr_service.py:168`, `src/ocr_service.py:175` |
| Result payload schema | Serializer in OCR service | `src/ocr_service.py:218`, `src/ocr_service.py:224` |

## Troubleshooting
### `ModuleNotFoundError: No module named 'redis'`
- Cause: dependencies not installed.
- Evidence: `src/worker.py:14`.
- Fix:
```bash
python -m pip install -r requirements.txt
```

### `ModuleNotFoundError: No module named 'shared'`
- Cause: `shared.models` is external to this directory.
- Evidence: `src/ocr_service.py:14`, `../../CoreInstances/ApiServer/src/shared/models.py:413`.
- Resolution path:
  - Use compose mode (`make up`) where shared code is mounted/copied automatically.
  - Or configure your standalone Python path to include the external shared package location.
  Evidence: `../../docker-compose.yml:279`, `../../docker/workers/ocr/Dockerfile:36`.

### Redis disconnect/reconnect loop
- Behavior: worker logs reconnect warnings and retries.
- Evidence: `src/worker.py:189`, `src/worker.py:193`, `src/worker.py:195`.

### EasyOCR initialization fails
- Behavior: the standard image logs that EasyOCR is unavailable and continues in bounded Tesseract-only mode. Custom images also fall back if initialization fails.

## Safety and Security Notes
- Startup logging redacts credentials embedded in `REDIS_URL`; still treat worker logs as internal operational data.

- OCR request payloads include base64-encoded image bytes; treat queue traffic and logs as potentially sensitive.
Evidence: `src/ocr_service.py:171`.
