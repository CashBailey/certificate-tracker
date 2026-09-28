# CoreInstances Operations

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Setup Prerequisites

- Docker Desktop with Docker Compose for the canonical local workflow. Evidence: `../README.md`.
- Git. Evidence: `../README.md`.
- Optional no-container backend prerequisite: Python `>=3.11`. Evidence: `ApiServer/pyproject.toml`.
- Optional no-container frontend prerequisite: Node.js + npm; containerized mode pins Node 20 (`node:20-alpine`). Evidence: `FrontendWebServer/package.json`, `../docker/frontend/Dockerfile.dev`, `../docker/frontend/Dockerfile`.

## Install / Bootstrap

| Workflow | Command | Status | Evidence |
|---|---|---|---|
| Full stack bootstrap | `cd .. && make setup` | Verified | `../Makefile` (`setup` target) |
| Build containers | `cd .. && make build` | Verified | `../Makefile` (`build` target) |
| No-cache build | `cd .. && make build-nc` | Verified | `../Makefile` (`build-nc` target) |
| Backend local deps only | `cd ApiServer && python3 -m pip install -r requirements.txt` | Verified in CI/dev container build flow | `ApiServer/requirements.txt`, `../.github/workflows/ci.yml`, `../docker/api/Dockerfile.dev` |
| Frontend local deps only | `cd FrontendWebServer && npm install` | Verified in dev container build flow | `FrontendWebServer/package.json`, `FrontendWebServer/package-lock.json`, `../docker/frontend/Dockerfile.dev` |

## Run Modes

| Mode | Command | Status | Evidence |
|---|---|---|---|
| Dev stack (detached) | `cd .. && make up` | Verified | `../Makefile` (`up`) |
| Dev stack with optional tools profile | `cd .. && make up-dev` | Verified | `../Makefile` (`up-dev`) |
| Dev stack with foreground logs | `cd .. && make up-logs` | Verified | `../Makefile` (`up-logs`) |
| Stop stack | `cd .. && make down` | Verified | `../Makefile` (`down`) |
| Stop stack + remove volumes | `cd .. && make down-v` | Verified | `../Makefile` (`down-v`) |
| Restart stack | `cd .. && make restart` | Verified | `../Makefile` (`restart`) |
| Production compose run | `cd .. && docker compose -f docker-compose.prod.yml up -d` | Documented in file header | `../docker-compose.prod.yml` |
| Production compose + GPU override | `cd .. && docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d` | Documented in file header | `../docker-compose.prod.yml` |
| Optional backend no-container run | `cd ApiServer && uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload` | Verified by dev runtime command parity | `../docker/api/Dockerfile.dev`, `ApiServer/src/main.py` |
| Optional frontend no-container run | `cd FrontendWebServer && npm run dev -- --host 0.0.0.0 --port 3000` | Verified by dev runtime command parity | `../docker/frontend/Dockerfile.dev`, `FrontendWebServer/package.json` |

Component-local runtime commands (outside compose) are available but less canonical:
- Backend dev container command uses `uvicorn ... --reload`. Evidence: `../docker/api/Dockerfile.dev`.
- Backend prod container command uses `gunicorn` + Uvicorn worker. Evidence: `../docker/api/Dockerfile`.
- Frontend dev container command uses `npm run dev -- --host 0.0.0.0 --port 3000`. Evidence: `../docker/frontend/Dockerfile.dev`.
- Frontend prod container serves built assets via Nginx. Evidence: `../docker/frontend/Dockerfile`.

## Status / Logs / Shell

| Task | Command | Evidence |
|---|---|---|
| Stack status | `cd .. && make status` | `../Makefile` |
| Health check | `cd .. && make health` | `../Makefile` |
| Follow all logs | `cd .. && make logs` | `../Makefile` |
| API logs only | `cd .. && make logs-api` | `../Makefile` |
| Frontend logs only | `cd .. && make logs-frontend` | `../Makefile` |
| Worker logs | `cd .. && make logs-workers` | `../Makefile` |
| Shell in API container | `cd .. && make shell-api` | `../Makefile` |
| Shell in frontend container | `cd .. && make shell-frontend` | `../Makefile` |

## Database Operations

| Task | Command | Status | Evidence |
|---|---|---|---|
| Apply migrations in stack | `cd .. && make db-migrate` | Verified | `../Makefile` |
| Create migration (interactive message prompt) | `cd .. && make db-migration` | Verified | `../Makefile` |
| Reset DB (destructive) | `cd .. && make db-reset` | Verified | `../Makefile` |
| Direct migration command inside API container | `cd .. && docker compose exec api alembic upgrade head` | Verified via make target expansion | `../Makefile` |

## Testing

| Scope | Command | Status | Evidence |
|---|---|---|---|
| Default backend tests | `cd .. && make test` | Verified | `../Makefile` |
| Backend tests + coverage | `cd .. && make test-cov` | Verified | `../Makefile` |
| CI backend unit tests | `cd ../CoreInstances/ApiServer && pytest tests/unit -v --tb=short -x` | Verified in CI | `../.github/workflows/ci.yml` |
| CI backend integration tests (containerized) | `cd .. && docker compose exec -T api pytest tests/integration -v --tb=short || true` | Verified in CI | `../.github/workflows/ci.yml` |
| Frontend automated tests | No test command configured in this directory | Verified (absence) | `FrontendWebServer/package.json`, `../.github/workflows/ci.yml` |

## Lint / Format / Typecheck

| Task | Command | Status | Evidence |
|---|---|---|---|
| Backend lint (stack) | `cd .. && make lint` | Verified | `../Makefile` |
| Backend lint fix (stack) | `cd .. && make lint-fix` | Verified | `../Makefile` |
| Backend format check | `cd ../CoreInstances/ApiServer && ruff format --check src/` | Verified in CI | `../.github/workflows/ci.yml` |
| Backend mypy check | `cd ../CoreInstances/ApiServer && mypy src/ --ignore-missing-imports` | Verified in CI (advisory) | `../.github/workflows/ci.yml` |
| Frontend lint | `cd FrontendWebServer && npm run lint` | Verified | `FrontendWebServer/package.json` |

## Build / Release

| Task | Command | Status | Evidence |
|---|---|---|---|
| Build all images (dev compose context) | `cd .. && make build` | Verified | `../Makefile` |
| Rebuild and restart stack | `cd .. && make rebuild` | Verified | `../Makefile` |
| Production stack start (prebuilt images) | `cd .. && docker compose -f docker-compose.prod.yml up -d` | Documented in file header | `../docker-compose.prod.yml` |

## Environment Variables

### CoreInstances App Variables (from code)

| Name | Required | Default | Where Used |
|---|---|---|---|
| `DATABASE_URL` | Yes | None | `ApiServer/src/deps.py`, `ApiServer/alembic/env.py` |
| `SECRET_KEY` | Yes | None | `ApiServer/src/auth/config.py` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | `ApiServer/src/auth/config.py` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | `ApiServer/src/auth/config.py` |
| `SESSION_MAX_HOURS` | No | `8` | `ApiServer/src/auth/config.py` |
| `COOKIE_SECURE` | No | `true` | `ApiServer/src/auth/router.py` |
| `FRONTEND_URL` | No | `https://localhost` | `ApiServer/src/main.py` |
| `REDIS_URL` | No | `rediss://redis:6380/0` | `ApiServer/src/deps.py` — use `rediss://` (TLS) scheme; plain `redis://` only when `TLS_ENABLED=false` |
| `MINIO_ENDPOINT` | Yes | None | `ApiServer/src/shared/storage.py` |
| `MINIO_ACCESS_KEY` | Yes | None | `ApiServer/src/shared/storage.py` |
| `MINIO_SECRET_KEY` | Yes | None | `ApiServer/src/shared/storage.py` |
| `MINIO_SECURE` | No | `true` | `ApiServer/src/shared/storage.py` — enables HTTPS; set `false` only when `TLS_ENABLED=false` |
| `TLS_ENABLED` | No | `true` | `ApiServer/src/shared/tls.py` — enable mutual TLS for all service connections |
| `TLS_CA_CERT` | No | `/tls/ca.crt` | `ApiServer/src/shared/tls.py` — CA certificate path (container-internal) |
| `TLS_CLIENT_CERT` | No | `/tls/client.crt` | `ApiServer/src/shared/tls.py` — client certificate path (container-internal) |
| `TLS_CLIENT_KEY` | No | `/tls/client.key` | `ApiServer/src/shared/tls.py` — client private key path (container-internal) |
| `TEMPLATES_DIR` | No | `templates` | `ApiServer/src/routes/templates.py` |
| `SMTP_HOST` | No | `localhost` | `ApiServer/src/shared/email_sender.py` |
| `SMTP_PORT` | No | `1025` | `ApiServer/src/shared/email_sender.py` |
| `SMTP_USER` | No | empty string | `ApiServer/src/shared/email_sender.py` |
| `SMTP_PASSWORD` | No | empty string | `ApiServer/src/shared/email_sender.py` |
| `NOTIFICATION_FROM_EMAIL` | No | `noreply@ci.laredo.tx.us` | `ApiServer/src/shared/email_sender.py` |
| `VITE_API_URL` | No | `/api` (relative) | `FrontendWebServer/src/api/client.ts`, `FrontendWebServer/src/api/auth.ts`, `FrontendWebServer/src/api/index.ts` |
| `VITE_INACTIVITY_TIMEOUT_MINUTES` | No | `30` | `FrontendWebServer/src/contexts/AuthContext.tsx` — minutes of inactivity before auto-logout; warning modal appears 60 s before timeout |

### Shared Stack Variables (from parent env template / compose)

| Name | Scope | Where Defined/Used |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | DB service and DB URL composition | `../.env.example`, `../docker-compose.yml`, `../docker-compose.prod.yml` |
| `REDIS_PORT` | Redis port binding | `../.env.example`, `../docker-compose.yml` |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BIND_HOST`, `MINIO_API_PORT`, `MINIO_CONSOLE_PORT` | MinIO service credentials and host binding (`MINIO_ROOT_PASSWORD` is required; bind host defaults to localhost) | `../.env.example`, `../docker-compose.yml` |
| `API_PORT`, `FRONTEND_PORT` | API/frontend host port bindings | `../.env.example`, `../docker-compose.yml`, `../docker-compose.prod.yml` |
| `IMAP_*`, `ALLOWED_EMAIL_DOMAIN`, `EMAIL_POLL_INTERVAL_SECONDS` | Email intake worker behavior | `../.env.example`, `../docker-compose.prod.yml` |
| `CLAMAV_*` | Malware scanning profile behavior (`CLAMAV_FAIL_OPEN=false` default for fail-closed scanning) | `../.env.example`, `../docker-compose.yml`, `../docker-compose.prod.yml` |

## Troubleshooting (Evidence-Backed)

1. `make` commands fail from `CoreInstances/`:
Run them from the parent project root (`cd ..`) where `Makefile` exists. Evidence: `../Makefile`.
2. API fails at startup with missing `DATABASE_URL`:
Set/propagate `DATABASE_URL` before app import/start. Evidence: `ApiServer/src/deps.py`.
3. API auth import fails with missing `SECRET_KEY`:
Set `SECRET_KEY`; auth settings raise on missing value. Evidence: `ApiServer/src/auth/config.py`.
4. Upload succeeds but extraction is not queued:
Check Redis availability; queue push errors are logged and upload response still returns success. Evidence: `ApiServer/src/routes/documents.py`.
5. Storage initialization errors:
Set `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`. Evidence: `ApiServer/src/shared/storage.py`.
6. Frontend auth loops or frequent logout:
Failed refresh clears in-memory token and emits forced logout event. Evidence: `FrontendWebServer/src/api/client.ts`, `FrontendWebServer/src/contexts/AuthContext.tsx`.
7. CORS issues between frontend and backend:
Backend allowlist uses `https://localhost` and `FRONTEND_URL`. Evidence: `ApiServer/src/main.py`.
8. Backend imports fail for modules like `aiosmtplib` or `pypdf`:
These modules are imported in code and may require explicit installation if not present in local env. Evidence: `ApiServer/src/shared/email_sender.py`, `ApiServer/src/routes/documents.py`, `ApiServer/requirements.txt`.
