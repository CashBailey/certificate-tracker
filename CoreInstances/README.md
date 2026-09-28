# CoreInstances

Core runtime services for the system.

## Directory Overview

- `ApiServer`: backend API, auth, document/review flows, and migrations.
- `FrontendWebServer`: browser UI for login, dashboard, review, requirements, templates, and reporting.
- `SqlDatabase`: listed historically, but no `SqlDatabase/` path is currently present in this directory.

## Entrypoints

- Backend runtime: `ApiServer/src/main.py`
- Backend migrations: `ApiServer/alembic/env.py`
- Frontend runtime: `FrontendWebServer/src/main.tsx`
- Frontend route map: `FrontendWebServer/src/App.tsx`
- Shared stack orchestration: `../Makefile`, `../docker-compose.yml`, `../docker-compose.prod.yml`

## Local Documentation

- Root docs hub: `docs/README.md`
- Structure map: `docs/DIRECTORY_MAP.md`
- Operations runbook: `docs/OPERATIONS.md`
- Architecture and data flow: `docs/ARCHITECTURE.md`
- Backend local docs: `ApiServer/docs/README.md`
- Frontend local docs: `FrontendWebServer/docs/README.md`
