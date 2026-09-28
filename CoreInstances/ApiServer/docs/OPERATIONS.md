# Operations

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Setup Prerequisites

| Prerequisite | Requirement | Evidence |
|---|---|---|
| Docker + Compose v2 | Required for canonical run/test/lint workflows (`docker compose ...`) | `../../Makefile`, `../../README.md`, `../../docker-compose.yml` |
| GNU Make | Required for canonical developer commands (`make setup`, `make up`, etc.) | `../../Makefile`, `../../README.md` |
| Python | `>=3.11` project requirement; CI uses `3.12` | `pyproject.toml` (`requires-python`), `../../.github/workflows/ci.yml` |

## Install Steps

### Canonical (Containerized)

```bash
cd ../..
make setup
```

`make setup` copies `.env.example` to `.env` if missing, then runs `make build`.
Evidence: `../../Makefile` (`setup`, `build`)

### Local Python Dependencies (for non-container lint/test workflows)

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install ruff mypy
```

Evidence: `../../.github/workflows/ci.yml` (lint job installs `ruff mypy` plus `-r requirements.txt`; unit-test job installs `-r requirements.txt`)

## Canonical Workflow (Recommended)

```bash
cd ../..
make up
make db-migrate
make health
```

Evidence: `../../README.md` Quick Start + Database Migrations sections, `../../Makefile`

## Run Modes

| Mode | Command | Evidence |
|---|---|---|
| Development stack (all services) | `cd ../.. && make up` | `../../Makefile` (`up`), `../../docker-compose.yml` |
| Development stack + optional dev tools | `cd ../.. && make up-dev` | `../../Makefile` (`up-dev`), `../../docker-compose.yml` profiles |
| Production stack (prebuilt images) | `cd ../.. && docker compose -f docker-compose.prod.yml up -d` | `../../docker-compose.prod.yml` header usage |
| DB migration in running stack | `cd ../.. && make db-migrate` | `../../Makefile` (`db-migrate`) |
| API logs | `cd ../.. && make logs-api` | `../../Makefile` (`logs-api`) |
| API shell | `cd ../.. && make shell-api` | `../../Makefile` (`shell-api`) |
| Stop stack | `cd ../.. && make down` | `../../Makefile` (`down`) |
| Stack status | `cd ../.. && make status` | `../../Makefile` (`status`) |

## API Service Runtime Details

### Dev Container Launch Command

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/src
```

Evidence: `../../docker/api/Dockerfile.dev` CMD

### Production Image Build Recipe Command

```bash
gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 --access-logfile - --error-logfile -
```

Evidence: `../../docker/api/Dockerfile` CMD

Production compose runs prebuilt image `laredo-certs/api:latest` and relies on image metadata for runtime command.
Evidence: `../../docker-compose.prod.yml`

## Testing

### Canonical

```bash
cd ../..
make test
make test-cov
```

Evidence: `../../Makefile` targets `test`, `test-cov`

### CI-Defined Suite Commands

```bash
pytest tests/unit -v --tb=short -x
pytest tests/unit --cov=src --cov-report=xml --cov-report=term-missing
docker compose exec -T api pytest tests/integration -v --tb=short
docker compose exec -T api pytest tests/api -v --tb=short
```

Evidence: `../../.github/workflows/ci.yml`

### Targeted Examples (documented in test modules)

```bash
pytest tests/ocr/ -v -m ocr
pytest tests/ocr/test_ocr_preprocessed.py -v -m ocr_preprocessed
python3 -m pytest tests/integration/test_llm_consensus_integration.py -v -s
```

Evidence: `tests/ocr/test_ocr_accuracy.py`, `tests/ocr/test_ocr_preprocessed.py`, `tests/integration/test_llm_consensus_integration.py`

## Lint / Format

| Task | Command | Evidence |
|---|---|---|
| Lint (canonical) | `cd ../.. && make lint` | `../../Makefile` (`lint`) |
| Lint auto-fix (canonical) | `cd ../.. && make lint-fix` | `../../Makefile` (`lint-fix`) |
| Ruff lint command | `ruff check src/` | `../../Makefile` (`lint` implementation), `../../.github/workflows/ci.yml` |
| Ruff formatter check | `ruff format --check src/` | `../../.github/workflows/ci.yml` |
| Type-check (advisory in CI) | `mypy src/ --ignore-missing-imports` | `../../.github/workflows/ci.yml` |

## Build / Release

| Step | Command / Behavior | Evidence |
|---|---|---|
| Build dev images | `cd ../.. && make build` | `../../Makefile` (`build`) |
| Build dev images without cache | `cd ../.. && make build-nc` | `../../Makefile` (`build-nc`) |
| CI image build validation | Docker build check runs with `push: false` | `../../.github/workflows/ci.yml` (`build-check`) |
| Production runtime startup | `cd ../.. && docker compose -f docker-compose.prod.yml up -d` | `../../docker-compose.prod.yml` |

Unknown: A CI/CD publish pipeline for `laredo-certs/api:latest` is not defined in discovered files.
Evidence: `../../.github/workflows/ci.yml`, `../../docker-compose.prod.yml`

## Environment Variables

### Required For API Startup

| Name | Required | Default | Where Defined/Used |
|---|---|---|---|
| `DATABASE_URL` | Yes | Set by compose interpolation | `src/deps.py`, `../../docker-compose.yml` (`api.environment`) |
| `SECRET_KEY` | Yes | none — startup fails with RuntimeError if unset | `src/auth/config.py`, `../../docker-compose.yml` |
| `MINIO_ENDPOINT` | Yes | `minio:9000` in compose | `src/shared/storage.py`, `../../docker-compose.yml` |
| `MINIO_ACCESS_KEY` | Yes | `${MINIO_ROOT_USER:-minioadmin}` | `src/shared/storage.py`, `../../docker-compose.yml` |
| `MINIO_SECRET_KEY` | Yes | Must be set from `.env` (`MINIO_ROOT_PASSWORD`) | `src/shared/storage.py`, `../../docker-compose.yml` |

### Optional / Defaulted In Code

| Name | Default In Code | Where Used |
|---|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | `src/auth/config.py` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | `src/auth/config.py` |
| `SESSION_MAX_HOURS` | `8` | `src/auth/config.py` |
| `COOKIE_SECURE` | `true` | `src/auth/router.py` |
| `FRONTEND_URL` | `https://localhost` | `src/main.py` |
| `REDIS_URL` | `rediss://redis:6380/0` | `src/deps.py` — use `rediss://` (TLS) scheme; plain `redis://` only when `TLS_ENABLED=false` |
| `MINIO_SECURE` | `true` | `src/shared/storage.py` — enables HTTPS; set `false` only when `TLS_ENABLED=false` |
| `TLS_ENABLED` | `true` | `src/shared/tls.py` — enable mutual TLS for all service connections |
| `TLS_CA_CERT` | `/tls/ca.crt` | `src/shared/tls.py` — CA certificate path (container-internal) |
| `TLS_CLIENT_CERT` | `/tls/client.crt` | `src/shared/tls.py` — client certificate path (container-internal) |
| `TLS_CLIENT_KEY` | `/tls/client.key` | `src/shared/tls.py` — client private key path (container-internal) |
| `TEMPLATES_DIR` | `templates` | `src/routes/templates.py` |
| `SMTP_HOST` | `localhost` | `src/shared/email_sender.py` |
| `SMTP_PORT` | `1025` | `src/shared/email_sender.py` |
| `SMTP_USER` | empty string | `src/shared/email_sender.py` |
| `SMTP_PASSWORD` | empty string | `src/shared/email_sender.py` |
| `NOTIFICATION_FROM_EMAIL` | `noreply@ci.laredo.tx.us` | `src/shared/email_sender.py` |

### Test Fixture Defaults

| Name | Evidence |
|---|---|
| `DATABASE_URL`, `SECRET_KEY`, `MINIO_*`, `REDIS_URL` defaults for tests | `tests/conftest.py`, `tests/integration/conftest.py` |
| `ALLOWED_EMAIL_DOMAIN` integration fixture default | `tests/integration/conftest.py` |

## Troubleshooting

1. API container is up but health check fails.  
Check `/health` endpoint and API logs.  
Evidence: `src/main.py` (`/health`), `../../Makefile` (`logs-api`, `health`).

2. Startup error: missing `DATABASE_URL`.  
Ensure compose/env passes `DATABASE_URL` or set it manually for direct execution.  
Evidence: `src/deps.py`, `../../docker-compose.yml`.

3. Startup/auth error: missing `SECRET_KEY`.  
Set `SECRET_KEY` in environment before starting API.  
Evidence: `src/auth/config.py`, `../../README.md`.

4. Upload succeeds but extraction is not processed.  
Redis publish failures log warnings; inspect worker and redis logs.  
Evidence: `src/routes/documents.py`, `../../Makefile` (`logs-workers`).

5. Template API errors after editing template JSON files.  
Registry enforces template structure and bounding-box validity; invalid files fail load.  
Evidence: `src/shared/template_registry.py`, `src/routes/templates.py`.

6. OCR/LLM tests skip or fail due missing infra.  
Ensure local stack includes required services and OCR/LLM prerequisites.  
Evidence: `tests/integration/test_llm_consensus_integration.py`, `tests/ocr/conftest.py`, `../../README.md`.

## Post-Deployment: Admin Password Setup (CRIT-01)

After a fresh deployment or after running migration 024, the admin account
(`admin@ci.laredo.tx.us`) has a NULL password hash. The admin **cannot log in**
until a password is set.

### Required Deployment Order

1. Deploy the new application code (container rebuild/restart)
2. Run `alembic upgrade head` (or `make db-migrate`)
3. Verify: `SELECT password_hash IS NULL FROM certificates.employees WHERE email = 'admin@ci.laredo.tx.us'`

### Setting the Admin Password

1. Navigate to `/forgot-password` in the web UI
2. Enter `admin@ci.laredo.tx.us`
3. Check the admin's email inbox (or Greenmail in dev) for the setup link
4. Click the link and set a password (minimum 15 characters, with digit + special character)
5. Log in with the new password

### Startup Warning

On startup, the API server checks whether the admin account still uses the
default password. If it does, a CRITICAL-level log message is emitted:

```
SECURITY: Admin account still uses the default password (CRIT-01).
Use the forgot-password flow at /forgot-password to set a secure password.
```

This covers the edge case where the admin logged in before migration 024 and
the hash was rehashed to Argon2id (so the migration's exact bcrypt match finds
zero rows). Operators should always use the forgot-password flow after deployment.

### Emergency Recovery

If the admin is locked out (e.g., migrations ran before code was deployed, or
email service is down), manually insert a password reset token via SQL:

```sql
INSERT INTO certificates.password_reset_tokens (employee_id, token_hash, expires_at, created_at)
VALUES (
  (SELECT id FROM certificates.employees WHERE email = 'admin@ci.laredo.tx.us'),
  encode(sha256(convert_to('emergency-token-value', 'UTF8')), 'hex'),
  NOW() + INTERVAL '30 minutes',
  NOW()
);
-- Then navigate to: /reset-password?token=emergency-token-value
-- (The new code must be deployed before using the token.)
```

## Safety / Security Notes

- Password storage uses Argon2id hashing with bcrypt legacy support. (Evidence: `src/auth/security.py`)
- JWT signing/validation requires env-backed secret. (Evidence: `src/auth/config.py`, `src/auth/security.py`)
- Upload validation enforces type by file bytes and max size boundaries. (Evidence: `src/shared/file_validation.py`)
- RBAC checks are enforced through dependency guards and authorizer helpers. (Evidence: `src/deps.py`, `src/authorizer.py`)
- Session invalidation on password change: `employees.token_version` increments on every password change; `get_current_user()` and `get_current_user_from_token()` compare the JWT `token_version` claim against the DB value and reject stale tokens with 401 "Session invalidated". (Evidence: `src/auth/security.py`, `src/deps.py`, `alembic/versions/019_add_token_version_to_employees.py`)
- Password strength enforcement: `PasswordChangeRequest` validates minimum length, uppercase, lowercase, digit, and special-character requirements (configurable via `auth_settings`). All violations are collected and raised as a single error. (Evidence: `src/auth/schemas.py`)
