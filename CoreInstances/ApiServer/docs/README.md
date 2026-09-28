# ApiServer Documentation

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## What This Directory Is

`ApiServer` is the backend API instance for the certificate-management system. It provides authentication/session flows, employee and requirement management, document upload + extraction/review workflows, reporting/export endpoints, notifications APIs, template management, and migration-backed persistence. (Evidence: `src/main.py`, `src/auth/router.py`, `src/routes/requirements.py`, `src/routes/documents.py`, `src/routes/extractions.py`, `src/routes/reports.py`, `src/routes/notifications.py`, `src/routes/templates.py`, `alembic/versions/`)

## Canonical Run Path (Repository Standard)

The repository’s documented and scripted way to run this API is via Docker Compose + Make targets from repo root:

```bash
cd ../..
make setup
make up
make db-migrate
make health
```

(Evidence: `../../README.md` Quick Start and Database Migrations sections, `../../Makefile` targets: `setup`, `up`, `db-migrate`, `health`)

API endpoints after startup:
- API base: `https://localhost/api`
- API docs: `https://api.localhost/docs`

(Evidence: `../../README.md` Services & Ports table, `src/main.py`)

## Entrypoints

| Entrypoint | Purpose | Evidence |
|---|---|---|
| `src/main.py` (`app = FastAPI(...)`) | API runtime entrypoint | `src/main.py` |
| `alembic/env.py` + `alembic.ini` | Migration runtime entrypoint | `alembic/env.py`, `alembic.ini` |
| `tests/ocr_fixtures/generator/generate_test_certs.py` | OCR fixture regeneration script | `tests/ocr_fixtures/generator/generate_test_certs.py` |
| `../../docker/api/Dockerfile.dev` (CMD) | Dev container API launch command (`uvicorn ... --reload`) | `../../docker/api/Dockerfile.dev` |
| `../../docker/api/Dockerfile` (CMD) | Production-image build recipe command (`gunicorn ...`) | `../../docker/api/Dockerfile` |

## Quick Start (Directory-Scoped Tasks)

From this directory, common development tasks are typically executed against the running `api` container:

```bash
cd ../..
make logs-api
make shell-api
make test
make lint
```

(Evidence: `../../Makefile` targets: `logs-api`, `shell-api`, `test`, `lint`)

Migration and DB access:

```bash
cd ../..
make db-migrate
make shell-db
```

(Evidence: `../../Makefile` targets: `db-migrate`, `shell-db`)

## Where To Look Next

- Structure and contract surfaces: [`./DIRECTORY_MAP.md`](./DIRECTORY_MAP.md)
- Operations/runbook and env vars: [`./OPERATIONS.md`](./OPERATIONS.md)
- Components and data flow: [`./ARCHITECTURE.md`](./ARCHITECTURE.md)

## Assumptions And Unknowns

- This directory is run as part of the repository-level Docker Compose stack (not as an isolated standalone service setup).  
  Evidence: `../../README.md`, `../../Makefile`, `../../docker-compose.yml`
- Developer workflows are executed from repository root using Make targets.  
  Evidence: `../../README.md` Quick Start, `../../Makefile`
- The API’s local development base URL is `https://localhost/api` (via Caddy) when the stack is up.  
  Evidence: `../../README.md` Services & Ports table, `src/main.py`

- Unknown: CI checks for this directory are defined (lint/type-check/tests/build-check), but a publish step for `laredo-certs/api:latest` is not present in discovered workflow files.
  Evidence: `../../.github/workflows/ci.yml` (`build-check` uses Docker build with `push: false`), `../../docker-compose.prod.yml` (`api.image: laredo-certs/api:latest`)
