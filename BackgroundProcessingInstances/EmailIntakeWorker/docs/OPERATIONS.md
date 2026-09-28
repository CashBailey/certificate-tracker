# Operations

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Scope
This runbook documents operations for this directory, with root-level references only where required to run this worker (`../../docker-compose.yml`, `../../docker/workers/email-intake/Dockerfile`, `../../Makefile`).

## Verification Snapshot (2026-02-22 20:02:35 UTC)
| Check | Command | Status | Evidence |
|---|---|---|---|
| Python source syntax | `python -m compileall -q src` | Passed in this environment | local execution on 2026-02-22 |
| Unit test invocation (default) | `python -m pytest -q tests/test_directory_lookup.py` | Failed due external pytest plugin dependency (`yaml`) | local execution on 2026-02-22 |
| Unit test invocation (plugin-isolated) | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_directory_lookup.py` | Failed due missing installed dependency (`sqlalchemy`) | local execution on 2026-02-22 |
| Docker CLI validation | `docker compose ...` | Not executable here (`docker` command unavailable in this WSL distro) | local execution on 2026-02-22 |

## Prerequisites
### Docker path (recommended)
- Docker + Docker Compose.
- Repository root compose definitions and worker Dockerfile.
Evidence: `../../docker-compose.yml:324`, `../../docker/workers/email-intake/Dockerfile:1`

### Local Python path (advanced)
- Python packages from `requirements.txt`.
- System libraries needed by dependencies (for example `libmagic` for `python-magic`; PostgreSQL headers/toolchain are installed in container image).
- Access to shared module path used by imports (`shared.*`).
Evidence: `requirements.txt:1`, `src/worker.py:20`, `src/worker.py:25`, `src/directory_lookup.py:17`, `../../docker/workers/email-intake/Dockerfile:12`, `../../CoreInstances/ApiServer/src/shared/__init__.py`

### Python version
- Container image pins Python `3.12` (`python:3.12-slim-bookworm`).
- Directory-local Python version pin file: Unknown.
Evidence: `../../docker/workers/email-intake/Dockerfile:4`

## Install
### Docker build (from repository root)
```bash
docker compose build email-intake-worker
```
Evidence: `../../docker-compose.yml:324`, `../../docker-compose.yml:325`

### Local dependencies (from this directory)
```bash
python -m pip install -r requirements.txt
```
Evidence: `requirements.txt:1`

## Run Modes
### 1. Daemon via Docker Compose (recommended)
Run from repository root:
```bash
docker compose up -d email-intake-worker
docker compose logs -f email-intake-worker
```
Evidence: `../../docker-compose.yml:324`, `../../docker-compose.yml:359`

### 1b. Daemon with strict malware scanning (ClamAV service running)
Run from repository root:
```bash
docker compose --profile email-intake up -d clamav email-intake-worker
docker compose logs -f email-intake-worker clamav
```
Evidence: `../../docker-compose.yml:349`, `../../docker-compose.yml:376`, `../../docker-compose.yml:396`

### 2. Daemon via local Python
Run from this directory:
```bash
PYTHONPATH=../../CoreInstances/ApiServer/src python -m src.worker
```
Why `PYTHONPATH` is needed: this worker imports `shared.*` from the API source tree.
Evidence: `src/worker.py:25`, `src/directory_lookup.py:17`, `../../CoreInstances/ApiServer/src/shared/__init__.py`

### 3. Programmatic one-shot poll
Use `poll_once()` when you need a single mailbox pass in integration code.
```python
import asyncio
from src.worker import create_worker_from_env

async def main():
    worker = create_worker_from_env()
    worker.email_client.connect()
    try:
        processed = await worker.poll_once()
        print(f"processed={processed}")
    finally:
        worker.email_client.disconnect()

asyncio.run(main())
```
Evidence: `src/worker.py:618`, `src/worker.py:686`, `src/worker.py:642`, `src/worker.py:677`

## Testing
### Unit tests present in this directory
```bash
python -m pytest -q tests/test_directory_lookup.py
```
Evidence: `tests/test_directory_lookup.py:1`, `tests/test_directory_lookup.py:19`

## Notes on test environment
- Tests are async (`pytest.mark.asyncio`) and assume access to modules outside this directory.
- Local command execution in this environment failed without dependencies (observed missing `sqlalchemy`).
- If unrelated pytest plugins are auto-loaded in your shell, run with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
Evidence: `tests/test_directory_lookup.py:72`, `requirements.txt:5`

## Lint / Format
- Directory-local lint/format command: Unknown.
- Repo-level `make lint` exists but runs in API container against `src/` there, not explicitly this worker directory.
Evidence: `../../Makefile:206`

## Build / Release
- Dev compose builds from source via `docker/workers/email-intake/Dockerfile`.
- Prod compose uses prebuilt image `laredo-certs/email-intake-worker:latest`.
Evidence: `../../docker-compose.yml:325`, `../../docker-compose.yml:327`, `../../docker-compose.prod.yml:273`

## Environment Variables
Sensitive values are redacted.

| Variable | Required | Code Default | Compose Default (dev) | Used In |
|---|---|---|---|---|
| `DATABASE_URL` | Context-dependent | `[REDACTED_SENSITIVE_DEFAULT]` | postgres service URL | `src/directory_lookup.py:34`, `../../docker-compose.yml:331` |
| `ALLOWED_EMAIL_DOMAIN` | No | `ci.laredo.tx.us` | `ci.laredo.tx.us` | `src/directory_lookup.py:188`, `../../docker-compose.yml:345` |
| `IMAP_HOST` | No | `localhost` | `greenmail` | `src/email_client.py:227`, `../../docker-compose.yml:338` |
| `IMAP_PORT` | No | `993` | `3143` | `src/email_client.py:228`, `../../docker-compose.yml:339` |
| `IMAP_USER` | Context-dependent | empty string | empty string | `src/email_client.py:229`, `../../docker-compose.yml:340` |
| `IMAP_PASSWORD` | Context-dependent | `[REDACTED_SENSITIVE_DEFAULT]` | `[REDACTED_SENSITIVE_DEFAULT]` | `src/email_client.py:230`, `../../docker-compose.yml:341` |
| `IMAP_USE_SSL` | No | `false` | `false` | `src/email_client.py:231`, `../../docker-compose.yml:342` |
| `IMAP_INBOX_FOLDER` | No | `INBOX` | `INBOX` | `src/email_client.py:232`, `../../docker-compose.yml:343` |
| `IMAP_PROCESSED_FOLDER` | No | `Processed` | `Processed` | `src/email_client.py:233`, `../../docker-compose.yml:344` |
| `MINIO_ENDPOINT` | No | `minio:9000` | `minio:9000` | `src/worker.py:696`, `../../docker-compose.yml:333` |
| `MINIO_ACCESS_KEY` | Context-dependent | `[REDACTED_SENSITIVE_DEFAULT]` | `${MINIO_ROOT_USER:-...}` | `src/worker.py:697`, `../../docker-compose.yml:334` |
| `MINIO_SECRET_KEY` | Context-dependent | `[REDACTED_SENSITIVE_DEFAULT]` | `${MINIO_ROOT_PASSWORD:-...}` | `src/worker.py:698`, `../../docker-compose.yml:335` |
| `MINIO_SECURE` | No | `true` | `true` | Enables HTTPS for MinIO. Set to `false` only when `TLS_ENABLED=false`. `src/worker.py:699`, `../../docker-compose.yml:336` |
| `MINIO_BUCKET` | No | `documents` | `documents` | `src/worker.py:711`, `../../docker-compose.yml:337` |
| `REDIS_URL` | No | `rediss://redis:6380/0` | `rediss://redis:6380/0` | Use `rediss://` (TLS) scheme; plain `redis://` only when `TLS_ENABLED=false`. `src/worker.py:704`, `../../docker-compose.yml:332` |
| `EMAIL_POLL_INTERVAL_SECONDS` | No | `60` | `60` | `src/worker.py:708`, `../../docker-compose.yml:346` |
| `LOG_LEVEL` | No | `INFO` | `INFO` | `src/worker.py:51`, `../../docker-compose.yml:347` |
| `CLAMAV_ENABLED` | No | `true` | `true` | `src/malware_scanner.py:156`, `../../docker-compose.yml:349` |
| `CLAMAV_HOST` | No | `clamav` | `clamav` | `src/malware_scanner.py:160`, `../../docker-compose.yml:350` |
| `CLAMAV_PORT` | No | `3310` | `3310` | `src/malware_scanner.py:161`, `../../docker-compose.yml:351` |
| `CLAMAV_TIMEOUT` | No | `30` | `30` | `src/malware_scanner.py:162`, `../../docker-compose.yml:352` |
| `CLAMAV_FAIL_OPEN` | No | `false` | `false` | `src/malware_scanner.py:50`, `../../docker-compose.yml:410` |
| `TLS_ENABLED` | No | `true` | `true` | Enable mutual TLS for PostgreSQL, Redis, and MinIO connections. Set `false` for plain-TCP debugging only. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CA_CERT` | No | `/tls/ca.crt` | `/tls/ca.crt` | CA certificate path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CLIENT_CERT` | No | `/tls/client.crt` | `/tls/client.crt` | Client certificate path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CLIENT_KEY` | No | `/tls/client.key` | `/tls/client.key` | Client private key path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |

## Sender Validation Pipeline

Incoming emails are accepted only when they pass three sequential checks. All
logic is in `src/directory_lookup.py`, `lookup_or_quarantine()`.

| Step | Check | Failure action | Evidence |
|---|---|---|---|
| 1 | Sender domain matches `ALLOWED_EMAIL_DOMAIN` | Silently ignore | `src/directory_lookup.py:150` |
| 2 | Sender email is in the city GAL (`gal_entries` table) | Silently ignore | `src/directory_lookup.py:155` |
| 3 | GAL entry is a real person (`is_person=True`), not a distribution list | Silently ignore | `src/directory_lookup.py:160` |

All three checks must pass. Only then does the worker proceed to look up or
auto-create an employee record and enqueue the extraction task.

**Spoofing note:** The `From:` header in IMAP email is not cryptographically
verified. SPF, DKIM, and DMARC DNS records for `ci.laredo.tx.us` are required at the
mail-transfer level to prevent header spoofing. Confirming these records are in place
is an operational prerequisite for production deployment.

## Operational Checks
### Service health smoke checks
Run from repository root:
```bash
docker compose ps email-intake-worker
docker compose logs --tail=100 email-intake-worker
```
Evidence: service name in `../../docker-compose.yml:324`

### Behavioral smoke checks
- New mail with attachments should be fetched from inbox and moved to `Processed` on success.
- Invalid/failed mail should be moved to `Quarantine`.
- New documents should push payloads to Redis list `extraction_tasks`.
Evidence: `src/email_client.py:122`, `src/email_client.py:175`, `src/email_client.py:197`, `src/worker.py:67`, `src/worker.py:322`

## Troubleshooting
- `ModuleNotFoundError: magic` when running locally.  
  Fix: install dependencies and ensure `libmagic` is available on host.  
  Evidence: `src/worker.py:20`, `requirements.txt:17`, `../../docker/workers/email-intake/Dockerfile:14`

- `ModuleNotFoundError: shared` when running locally.  
  Fix: include `../../CoreInstances/ApiServer/src` on `PYTHONPATH`.  
  Evidence: `src/worker.py:25`, `src/directory_lookup.py:17`, `../../CoreInstances/ApiServer/src/shared/__init__.py`

- Worker fails at startup with `ClamAV is required but unreachable`.  
  Cause: `CLAMAV_ENABLED=true` with fail-closed policy (`CLAMAV_FAIL_OPEN=false`) and ClamAV service not started/reachable.  
  Fix: start ClamAV with `docker compose up -d clamav` (or bring up the full email-intake stack with `make up`), or explicitly set `CLAMAV_FAIL_OPEN=true` for local fail-open behavior.  
  Evidence: `src/malware_scanner.py:166`, `src/malware_scanner.py:169`, `../../docker-compose.yml:406`, `../../docker-compose.yml:410`

- `make logs-workers` does not include this worker.  
  Fix: use `docker compose logs -f email-intake-worker`.  
  Evidence: `../../Makefile:117`, `../../docker-compose.yml:324`
