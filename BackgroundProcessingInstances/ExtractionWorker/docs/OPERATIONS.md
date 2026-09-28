# Operations Guide

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Setup Prerequisites

### Runtime prerequisites confirmed by code
- Python runtime: required (this directory is Python-only source/tests). Evidence: `requirements.txt:1`, `src/worker.py:1`, `tests/test_pipeline_branching.py:1`.
- Redis: required for worker queue polling and OCR queue RPC. Evidence: `src/worker.py:82`, `src/worker.py:363`, `src/ocr_client.py:66`.
- PostgreSQL-compatible database: required by SQLAlchemy async engine usage in worker. Evidence: `src/worker.py:89`, `src/worker.py:92`.
- Object storage: required via `MinioStorageClient` usage in task processing. Evidence: `src/worker.py:136`, `src/worker.py:175`, `src/worker.py:323`.
- Template directory content: required at runtime via `JsonTemplateRegistry(templates_dir)`; defaults to `/app/templates`. Evidence: `src/pipeline.py:60`, `src/pipeline.py:65`, `src/worker.py:394`.
- Container baseline Python runtime is `3.12` (`python:3.12-slim-bookworm`). Evidence: `../../docker/workers/extraction/Dockerfile:4`.

### Optional/runtime-enhancement prerequisites
- Ollama endpoint for LLM cleanup/correction (`OLLAMA_URL`); failures are handled gracefully. Evidence: `src/llm_client.py:26`, `src/llm_client.py:158`.
- GPU for parallel LLM consensus mode (or override with `GPU_VRAM_MB`). Evidence: `src/gpu_detect.py:22`, `src/gpu_detect.py:82`, `src/llm_client.py:35`.
- `pdf2image`/poppler-based rasterization path for scanned PDFs. Evidence: `src/pdf_raster.py:2`, `src/normalize.py:78`.
- OpenCV-backed preprocessing is optional (falls back if unavailable). Evidence: `src/preprocess.py:29`, `src/preprocess.py:31`.
- For full-stack local operation (outside this directory), repository docs require Docker Desktop + Docker Compose. Evidence: `../../README.md:45`.
- Worker container installs OS libraries/tools including `libmagic1`, `poppler-utils`, and `python3-opencv`. Evidence: `../../docker/workers/extraction/Dockerfile:12`, `../../docker/workers/extraction/Dockerfile:15`, `../../docker/workers/extraction/Dockerfile:18`.

### Version prerequisites
- Python version:
  - Containerized mode: `3.12` (verified).
  - Nearest repository-level explicit requirement: `>=3.11` (`CoreInstances/ApiServer/pyproject.toml`).
  - Evidence: `../../docker/workers/extraction/Dockerfile:4`, `../../CoreInstances/ApiServer/pyproject.toml:5`.
- OS package prerequisites:
  - Containerized mode: installed by worker Dockerfile (`libmagic1`, `poppler-utils`, `python3-opencv`, plus related build/runtime packages).
  - Host install command: `Unknown` (OS-specific and not defined in this directory).
  - Evidence: `../../docker/workers/extraction/Dockerfile:12`, `../../docker/workers/extraction/Dockerfile:15`, `../../docker/workers/extraction/Dockerfile:18`.

## Install Steps

- Local Python dependency install command (verified from worker image build process):

```bash
pip install -r requirements.txt
```

- Dependency manifest is present in `requirements.txt`. Evidence: `requirements.txt:1`.
- Evidence: `../../docker/workers/extraction/Dockerfile:26`, `../../docker/workers/extraction/Dockerfile:27`.
- Full-stack setup command (repository-level, outside this directory) is documented as `make setup`. Evidence: `../../README.md:62`.

## Run Modes

Choose mode by intent:
- Use Worker mode for queue-driven production/background processing.
- Use Programmatic mode when embedding extraction inside another Python process.
- Use Test mode for behavioral validation/regression checks.

### Worker mode (documented entrypoint)
```bash
python -m src.worker
```
Evidence: `src/__init__.py:7`, `src/worker.py:415`, `src/worker.py:428`.

Notes:
- Worker imports external `shared.*` modules; in full-stack mode these are mounted at `/app/shared`.
- Evidence: `src/worker.py:135`, `../../docker-compose.yml:243`.
- Local non-container `PYTHONPATH` setup for `shared.*` imports is `Unknown` (not explicitly documented in this directory).

### Full-stack container mode (repository-level context)
- This worker is defined as the `extraction-worker` service in `../../docker-compose.yml`.
- Repository common start/log commands are documented as `make up` and `make logs-workers`.
- Evidence: `../../docker-compose.yml:214`, `../../README.md:246`, `../../README.md:257`.

### Test mode (documented workflow)
```bash
# from repository root
make test
make test-cov
```
Evidence: `../../Makefile:200`, `../../Makefile:203`, `../../README.md:230`.

Notes:
- Several test files include `if __name__ == "__main__": pytest.main(...)`, but direct `python tests/...` execution is environment-dependent because import-path bootstrapping is inconsistent across files.
- Evidence (has local path bootstrap): `tests/test_pipeline_branching.py:29`, `tests/test_name_mismatch_handling.py:17`.
- Evidence (imports worker modules directly, no local path bootstrap block): `tests/test_visual_template_matching.py:16`, `tests/test_zone_extraction.py:17`.

## Testing

- Framework: `pytest` (including async tests via markers). Evidence: `tests/test_pipeline_branching.py:23`, `tests/test_pipeline_branching.py:206`, `tests/test_zone_extraction.py:132`.
- Canonical execution command in project docs is `make test` (runs `pytest -v` in API container context). Evidence: `../../Makefile:200`, `../../Makefile:201`.
- Coverage focus areas in this directory:
  - Path A vs Path B branching behavior. Evidence: `tests/test_pipeline_branching.py:2`.
  - Hash-only template matching behavior. Evidence: `tests/test_visual_template_matching.py:2`.
  - Zone extraction raw-text semantics and handwriting routing. Evidence: `tests/test_zone_extraction.py:2`.
  - GAL name replacement and mismatch handling semantics. Evidence: `tests/test_gal_name_replacement.py:2`, `tests/test_name_mismatch_handling.py:2`.

## Lint / Format

- Local extraction-worker-specific lint config files are not present in this directory.
- Repository-level lint command (outside this directory): `make lint` (runs `ruff check src/` in API container context), with Ruff target/version config in `CoreInstances/ApiServer/pyproject.toml`.
- Evidence: `../../Makefile:206`, `../../Makefile:207`, `../../CoreInstances/ApiServer/pyproject.toml:39`, `../../CoreInstances/ApiServer/pyproject.toml:40`.

## Build / Release

- Container build for this worker is defined at `docker/workers/extraction/Dockerfile` and wired via `extraction-worker` service in compose.
- Evidence: `../../docker-compose.yml:214`, `../../docker-compose.yml:217`, `../../docker/workers/extraction/Dockerfile:1`.
- Repository-level rebuild command (outside this directory): `make rebuild`. Evidence: `../../README.md:251`.

## Environment Variables

| Variable | Required | Default | Where Used |
|---|---|---|---|
| `REDIS_URL` | No (default exists) | `rediss://redis:6380/0` | Worker Redis connection and queue polling. Use `rediss://` (TLS) scheme; plain `redis://` only when `TLS_ENABLED=false`. Evidence: `src/worker.py:389`, `src/worker.py:82`. |
| `DATABASE_URL` | No (default exists) | `postgresql://<redacted>` | SQLAlchemy async engine setup; `postgresql://` is converted to `postgresql+asyncpg://`. Evidence: `src/worker.py:390`, `src/worker.py:89`. |
| `MINIO_ENDPOINT` | Yes (via `shared.storage`) | `minio:9000` in compose | Required by `MinioStorageClient` for object storage endpoint. Evidence: `src/worker.py:136`, `../../CoreInstances/ApiServer/src/shared/storage.py:35`, `../../CoreInstances/ApiServer/src/shared/storage.py:37`, `../../docker-compose.yml:223`. |
| `MINIO_ACCESS_KEY` | Yes (via `shared.storage`) | `<redacted>` (compose/env) | Required by `MinioStorageClient` for object storage auth. Evidence: `../../CoreInstances/ApiServer/src/shared/storage.py:39`, `../../CoreInstances/ApiServer/src/shared/storage.py:41`, `../../docker-compose.yml:224`. |
| `MINIO_SECRET_KEY` | Yes (via `shared.storage`) | `<redacted>` (compose/env) | Required by `MinioStorageClient` for object storage auth. Evidence: `../../CoreInstances/ApiServer/src/shared/storage.py:43`, `../../CoreInstances/ApiServer/src/shared/storage.py:45`, `../../docker-compose.yml:225`. |
| `MINIO_SECURE` | No (default exists) | `true` | Enables HTTPS for MinIO client. Set to `false` only when `TLS_ENABLED=false`. Evidence: `../../CoreInstances/ApiServer/src/shared/storage.py:46`. |
| `TLS_ENABLED` | No (default exists) | `true` | Enable mutual TLS for all service connections. Set `false` for plain-TCP local debugging only. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CA_CERT` | No (default exists) | `/tls/ca.crt` | CA certificate path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CLIENT_CERT` | No (default exists) | `/tls/client.crt` | Client certificate path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CLIENT_KEY` | No (default exists) | `/tls/client.key` | Client private key path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TEMPLATES_DIR` | No (default exists) | `/app/templates` | Worker startup and pipeline template registry path. Evidence: `src/worker.py:394`, `src/pipeline.py:60`. |
| `OLLAMA_URL` | No (default exists) | `http://ollama:11434` | LLM HTTP endpoint. Evidence: `src/llm_client.py:26`, `src/llm_client.py:144`. |
| `LLM_MODEL` | No (default exists) | `llama3.2:3b` | Primary model for cleanup/correction calls. Evidence: `src/llm_client.py:27`, `src/llm_client.py:146`. |
| `LLM_TIMEOUT` | No (default exists) | `60` | HTTP timeout for LLM requests. Evidence: `src/llm_client.py:28`, `src/llm_client.py:142`. |
| `LLM_CONSENSUS_N` | No (default exists) | `3` | Number of consensus runs. Evidence: `src/llm_client.py:30`. |
| `LLM_CONSENSUS_ENABLED` | No (default exists) | `true` | Toggle for consensus strategy. Evidence: `src/llm_client.py:31`. |
| `LLM_CONSENSUS_TEMP` | No (default exists) | `0.3` | Consensus temperature baseline. Evidence: `src/llm_client.py:32`. |
| `LLM_NUEXTRACT_TEMP_STEP` | No (default exists) | `0.05` | NuExtract temp stepping for consensus runs. Evidence: `src/llm_client.py:33`. |
| `LLM_PARALLEL_CONSENSUS` | No (default exists) | `auto` | Override parallel/sequential consensus mode. Evidence: `src/llm_client.py:40`. |
| `GPU_VRAM_MB` | No (optional override) | None | Manual GPU VRAM override for consensus mode selection. Evidence: `src/gpu_detect.py:82`. |
| `LOG_LEVEL` | No (default exists) | `INFO` | Read at worker startup; sets root logging level for structlog filter_by_level processor. Evidence: `src/worker.py:21`. |

## Queue / Key Contracts

| Name | Type | Producer | Consumer | Purpose | Evidence |
|---|---|---|---|---|---|
| `extraction_tasks` | Redis list | API upload route (`documents.py`) and EmailIntakeWorker (`_queue_extraction_task`) | `ExtractionWorker` | Main extraction job queue (`BLPOP`). | `../../CoreInstances/ApiServer/src/routes/documents.py:148`, `../../BackgroundProcessingInstances/EmailIntakeWorker/src/worker.py:329`, `src/worker.py:363` |
| `ocr_tasks` | Redis list | `RedisOcrClient` in ExtractionWorker | `OcrWorker` in OcrEngine | OCR request queue. | `src/ocr_client.py:66`, `src/ocr_client.py:118`, `../../BackgroundProcessingInstances/OcrEngine/src/worker.py:183` |
| `ocr_results:{request_id}` | Redis key | `OcrWorker` in OcrEngine (`SETEX`, TTL 300s) | `RedisOcrClient` in ExtractionWorker | OCR response payload lookup key. | `../../BackgroundProcessingInstances/OcrEngine/src/worker.py:162`, `../../BackgroundProcessingInstances/OcrEngine/src/worker.py:165`, `src/ocr_client.py:69`, `src/ocr_client.py:121` |

## Safety and Security Notes

- Source includes a development default for `DATABASE_URL`; do not rely on that value for non-local environments.
  - Evidence: `src/worker.py:390`.
- Worker startup logs include `redis_url`; avoid embedding credentials in URL strings if logs are broadly visible.
  - Evidence: `src/worker.py:396`, `src/worker.py:398`.
- Name mismatch handling and rejection email logic process personally identifiable information (names, email addresses, message IDs).
  - Evidence: `src/worker.py:218`, `src/worker.py:249`, `src/worker.py:252`.
- LLM cleanup sends OCR-derived text/prompt content to the configured Ollama endpoint; ensure endpoint trust boundary is appropriate for document data.
  - Evidence: `src/llm_client.py:143`, `src/llm_client.py:147`.

## Troubleshooting

- Worker does not receive jobs:
  - Confirm Redis connectivity and queue producer writes to `extraction_tasks`.
  - Worker polls `BLPOP extraction_tasks` with timeout 5s and retries Redis connection on errors.
  - Evidence: `src/worker.py:363`, `src/worker.py:370`.

- OCR requests stall or timeout:
  - OCR RPC is Redis-backed (`ocr_tasks` -> `ocr_results:{request_id}`) and raises `TimeoutError` on expiry.
  - Evidence: `src/ocr_client.py:66`, `src/ocr_client.py:69`, `src/ocr_client.py:85`.

- Template match unexpectedly falls back:
  - Template identification is hash-only; if no hash match within threshold, pipeline switches to Path B generic extraction.
  - Evidence: `src/identify.py:67`, `src/identify.py:195`, `src/pipeline.py:133`.

- Handwriting zones produce weak results:
  - If no handwriting OCR client is configured, code logs warning and uses standard OCR client.
  - Evidence: `src/zone_extract.py:144`, `src/zone_extract.py:148`.

- LLM cleanup not applied:
  - Ollama connection/timeouts are handled by returning `None`; pipeline continues with non-LLM fallback behavior.
  - Evidence: `src/llm_client.py:158`, `src/llm_client.py:162`, `src/llm_client.py:165`.

- Import errors while running tests directly:
  - Tests rely on injecting repository sibling paths into `sys.path` (`CoreInstances/ApiServer/src` and this worker `src`).
  - Evidence: `tests/conftest.py:12`, `tests/conftest.py:13`, `tests/conftest.py:14`.
