# Operations

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Setup Prerequisites
### Runtime dependencies
- Python-based worker code and pinned runtime dependencies in `requirements.txt`. Evidence: `src/*.py`, `requirements.txt`.
- Python 3.12 is the container baseline and CI Python version for project tooling. Evidence: `../../docker/workers/scheduler/Dockerfile`, `../../.github/workflows/ci.yml`.
- PostgreSQL connectivity via `DATABASE_URL`. The worker normalizes `postgresql://` to async driver format. Evidence: `src/scheduler.py`.
- Redis connectivity via `REDIS_URL` with startup `PING` health check. Evidence: `src/scheduler.py`.
- Importable `shared` package (`shared.repository`, `shared.models`, `shared.email_sender`, `shared.logging_utils`). Evidence: `src/scheduler.py`, `src/notifications.py`.

### Containerized prerequisites (recommended path)
- Docker Compose service definition exists for `scheduler-worker`. Evidence: `../../docker-compose.yml`.
- Worker image/runtime command are defined in `../../docker/workers/scheduler/Dockerfile`.
- Root automation commands are provided in `../../Makefile`.

## Install Steps
### Local Python install
```bash
python -m pip install -r requirements.txt
```
Evidence: `requirements.txt`.

### Container image build (repo root)
```bash
cd ../..
make build
```
Evidence: `../../Makefile`.

## Run Modes
### Mode A: Docker Compose worker (recommended)
From repo root:
```bash
cd ../..
make up
make logs-workers
```
- `make up` starts all services with Compose.
- `make logs-workers` tails worker logs and includes `scheduler-worker`.
Evidence: `../../Makefile`.

### Mode B: Production-style compose run (image-based)
From repo root:
```bash
cd ../..
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
This combines base and production overrides as documented in Docker guidance.
Evidence: `../../DOCKER.md`, `../../docker-compose.yml`, `../../docker-compose.prod.yml`.

### Mode C: Local module execution (advanced)
```bash
python -m pip install -r requirements.txt
export PYTHONPATH='../../CoreInstances/ApiServer/src'
export DATABASE_URL='postgresql://<user>:<pass>@<host>:<port>/<db>'
export REDIS_URL='redis://localhost:6380/0'
python -m src.scheduler
```
Use this mode only when DB/Redis are reachable and `PYTHONPATH` includes shared sources.
Evidence: `src/scheduler.py`, `src/notifications.py`, `../../CoreInstances/ApiServer/src/shared`, `../../docker/workers/scheduler/Dockerfile`.

### Scheduled jobs in this worker
| Job ID | Function | Frequency |
|---|---|---|
| `generate_notifications_daily` | `SchedulerWorker.generate_notifications_daily` | Daily at 06:00 |
| `process_notification_queue` | `SchedulerWorker.process_notification_queue` | Every 5 minutes |

Evidence: `src/scheduler.py`.

## Testing
- There is no worker-local `tests/` directory or worker-local Python test config in this directory.
- Root test target exists: `make test`, which executes `docker compose exec api pytest -v` (API container tests, not a scheduler-worker-specific target).
- Closest notification-logic coverage appears in `../../CoreInstances/ApiServer/tests/unit/test_notifications.py`, which explicitly duplicates pure logic instead of importing worker code directly.
Evidence: local file inventory, `../../Makefile`, `../../CoreInstances/ApiServer/tests/unit/test_notifications.py`.

## Lint / Format
- No worker-specific lint target exists in this directory.
- Root lint targets exist:
```bash
cd ../..
make lint
make lint-fix
```
These run inside the API container over `src/` there.
CI also runs `ruff format --check` and `mypy` in `CoreInstances/ApiServer`.
Evidence: `../../Makefile`, `../../.github/workflows/ci.yml`.

## Build / Release
### Build
- Dev compose builds the scheduler worker from `../../docker/workers/scheduler/Dockerfile`.
- Dockerfile entrypoint command is `python -m src.scheduler`.
Evidence: `../../docker-compose.yml`, `../../docker/workers/scheduler/Dockerfile`.

### Release
- Production compose references image `laredo-certs/scheduler-worker:latest`.
- Repository CI workflow does not include scheduler-worker image publish steps (it includes API image build-check only).
- Manual image build/export/push flow is documented in `scripts/export-project.sh`:
  - `bash scripts/export-project.sh`
  - `PUSH_TO_REGISTRY=true REGISTRY_PREFIX=<registry-prefix> bash scripts/export-project.sh`
Evidence: `../../docker-compose.prod.yml`, `../../.github/workflows/ci.yml`, `../../scripts/export-project.sh`.

## Environment Variables
| Name | Required | Default | Where used |
|---|---|---|---|
| `DATABASE_URL` | Yes | None in code | Required by startup; used for SQLAlchemy async engine creation. Evidence: `src/scheduler.py`. |
| `REDIS_URL` | No in code | `rediss://redis:6380/0` | Used for Redis startup connectivity check. Use `rediss://` (TLS) scheme; plain `redis://` only when `TLS_ENABLED=false`. Evidence: `src/scheduler.py`. |
| `LOG_LEVEL` | No | `INFO` | Passed to secure logging config. Evidence: `src/scheduler.py`. |
| `SMTP_HOST` | No | `greenmail` (compose), `localhost` (shared sender fallback) | SMTP host for outbound email sender path. Evidence: `../../docker-compose.yml`, `../../CoreInstances/ApiServer/src/shared/email_sender.py`. |
| `SMTP_PORT` | No | `3025` (compose), `1025` (shared sender fallback) | SMTP port; shared sender enables STARTTLS on port 587. Evidence: `../../docker-compose.yml`, `../../CoreInstances/ApiServer/src/shared/email_sender.py`. |
| `SMTP_USER` | No | empty | Optional SMTP auth username. Evidence: `../../docker-compose.yml`, `../../CoreInstances/ApiServer/src/shared/email_sender.py`. |
| `SMTP_PASSWORD` | No | empty | Optional SMTP auth password. Evidence: `../../docker-compose.yml`, `../../CoreInstances/ApiServer/src/shared/email_sender.py`. |
| `NOTIFICATION_FROM_EMAIL` | No | `noreply@ci.laredo.tx.us` | Outbound sender address. Evidence: `../../docker-compose.yml`, `../../CoreInstances/ApiServer/src/shared/email_sender.py`, `../../.env.example`. |
| `PYTHONPATH` | Required for local non-Docker run | `/app` in container; set locally to include shared source | Required so `from shared...` imports resolve when running outside compose container. Evidence: `src/scheduler.py`, `src/notifications.py`, `../../docker/workers/scheduler/Dockerfile`. |
| `TLS_ENABLED` | No | `true` | PostgreSQL + Redis TLS | Enable mutual TLS for all service connections. Set `false` for plain-TCP debugging only. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CA_CERT` | No | `/tls/ca.crt` | PostgreSQL + Redis TLS | CA certificate path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CLIENT_CERT` | No | `/tls/client.crt` | PostgreSQL + Redis TLS | Client certificate path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |
| `TLS_CLIENT_KEY` | No | `/tls/client.key` | PostgreSQL + Redis TLS | Client private key path inside container. Required when `TLS_ENABLED=true`. Evidence: `../../CoreInstances/ApiServer/src/shared/tls.py`. |

## Troubleshooting
### `ModuleNotFoundError: No module named 'redis'` when running locally
- Cause: local Python dependencies not installed.
- Fix:
```bash
python -m pip install -r requirements.txt
```
- Evidence: local runtime probe (`python -m src.scheduler`), `requirements.txt`.

### `ModuleNotFoundError: No module named 'shared'` when running locally
- Cause: `shared` is outside this directory and not on local import path.
- Evidence-backed mitigation:
  - Run via Compose (`make up`) where `./CoreInstances/ApiServer/src/shared` is mounted into worker container.
  - Or set local import path before running:
```bash
export PYTHONPATH='../../CoreInstances/ApiServer/src'
python -m src.scheduler
```
- Evidence: `src/scheduler.py`, `src/notifications.py`, `../../docker-compose.yml`, `../../CoreInstances/ApiServer/src/shared`, `../../docker/workers/scheduler/Dockerfile`.

### Worker exits with `DATABASE_URL environment variable is required`
- Cause: missing `DATABASE_URL`.
- Fix: set `DATABASE_URL` before running local mode, or use compose mode where it is supplied.
- Evidence: `src/scheduler.py`, `../../docker-compose.yml`.

### Worker exits with `Failed to connect to Redis`
- Cause: Redis unavailable or wrong `REDIS_URL`.
- Fix: verify Redis health and URL; compose mode provides a `redis` service dependency.
- Evidence: `src/scheduler.py`, `../../docker-compose.yml`.

## Safety / Security Notes
- Structured logging adds a redaction processor backed by shared redaction patterns before JSON rendering.
- Avoid adding new logs that include raw credentials or secret-bearing payloads.
Evidence: `src/scheduler.py`.
