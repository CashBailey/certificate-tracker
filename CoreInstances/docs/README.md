# CoreInstances Documentation

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


`CoreInstances` is the runtime application layer containing two core services: `ApiServer/` (Python/FastAPI backend) and `FrontendWebServer/` (Vite/React frontend). Stack orchestration for these services is defined one level up in shared project configs (`../Makefile`, `../docker-compose*.yml`, `../docker/`). Evidence: `ApiServer/src/main.py`, `ApiServer/pyproject.toml`, `FrontendWebServer/src/main.tsx`, `FrontendWebServer/package.json`, `../Makefile`, `../docker-compose.yml`, `../docker-compose.prod.yml`.

## Entrypoints (How To Choose)

| Entrypoint | Choose This When | Evidence |
|---|---|---|
| `ApiServer/src/main.py` (`app`) | Running/debugging backend HTTP API behavior | `ApiServer/src/main.py` |
| `ApiServer/alembic/env.py` | Applying or authoring DB schema migrations | `ApiServer/alembic/env.py`, `ApiServer/alembic/versions/` |
| `FrontendWebServer/src/main.tsx` | Running/debugging frontend runtime bootstrapping | `FrontendWebServer/src/main.tsx`, `FrontendWebServer/index.html` |
| `FrontendWebServer/src/App.tsx` | Updating route map and role-based page access | `FrontendWebServer/src/App.tsx`, `FrontendWebServer/src/components/ProtectedRoute.tsx` |
| `../Makefile` | Starting/stopping/testing full local stack via Docker Compose | `../Makefile` |

## Quick Start

### Prerequisites
- Docker Desktop (Compose) for the standard local workflow. Evidence: `../README.md`.
- Git. Evidence: `../README.md`.
- Optional no-container local mode requires Python and Node toolchains. Evidence: `ApiServer/pyproject.toml`, `FrontendWebServer/package.json`.

### Recommended: Orchestrated Stack (Verified)

```bash
cd ..
make setup
make up
make status
make health
```

Evidence:
- `setup`, `up`, `status`, `health` targets: `../Makefile`.
- Compose-backed services for API/frontend/dependencies: `../docker-compose.yml`.

### Optional: Component-Local Dev

```bash
# Backend
cd ApiServer
python3 -m pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd ../FrontendWebServer
npm install
npm run dev -- --host 0.0.0.0 --port 3000
```

Evidence:
- Dependency manifests and scripts: `ApiServer/requirements.txt`, `FrontendWebServer/package.json`.
- Container dev runtime command alignment: `../docker/api/Dockerfile.dev`, `../docker/frontend/Dockerfile.dev`.
- Backend app object: `ApiServer/src/main.py`.

## Where To Look Next
- Root structure and hotspots: [`./DIRECTORY_MAP.md`](./DIRECTORY_MAP.md)
- Setup/run/test/lint/build operations: [`./OPERATIONS.md`](./OPERATIONS.md)
- Component responsibilities, data flow, conventions: [`./ARCHITECTURE.md`](./ARCHITECTURE.md)
- Component-local docs: [`../ApiServer/docs/README.md`](../ApiServer/docs/README.md), [`../FrontendWebServer/docs/README.md`](../FrontendWebServer/docs/README.md)

## Assumptions And Unknowns
- Assumption: canonical local operation uses parent-level Docker Compose orchestration (`../Makefile` + `../docker-compose*.yml`) rather than ad-hoc per-service commands. Evidence: `../Makefile`, `../docker-compose.yml`, `../docker-compose.prod.yml`.
- Assumption: Node 20 is the safest local no-container frontend target because containerized frontend builds run on `node:20-alpine`. Evidence: `../docker/frontend/Dockerfile`, `../docker/frontend/Dockerfile.dev`, `FrontendWebServer/package.json`.
- Unknown: intended frontend automated test command for this directory; `FrontendWebServer/package.json` has no `test` script and no dedicated frontend test workflow is defined in the discovered CI file. Evidence: `FrontendWebServer/package.json`, `../.github/workflows/ci.yml`.
- Unknown: whether the `SqlDatabase/` mention in `README.md` is legacy or planned; the path is not present in the current tree. Evidence: `README.md`, current tree.
