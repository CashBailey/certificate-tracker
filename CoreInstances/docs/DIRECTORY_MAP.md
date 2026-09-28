# CoreInstances Directory Map

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Rendered Tree (Trimmed)

```text
.
├── ApiServer/
│   ├── README.md
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       ├── 001_initial_schema.py
│   │       ├── ...
│   │       └── 019_split_notification_read_from_delivered.py
│   ├── src/
│   │   ├── main.py
│   │   ├── deps.py
│   │   ├── auth/
│   │   ├── routes/
│   │   └── shared/
│   ├── templates/
│   │   ├── demo_cert.json
│   │   └── lms_certificate.json
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── ocr/
│   │   ├── performance/
│   │   ├── resilience/
│   │   └── security/
│   └── docs/
├── FrontendWebServer/
│   ├── README.md
│   ├── package.json
│   ├── package-lock.json
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── public/
│   │   └── logos/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   ├── components/
│   │   ├── contexts/
│   │   ├── pages/
│   │   ├── styles/
│   │   └── types/
│   └── docs/
├── README.md
└── docs/
    ├── README.md
    ├── DIRECTORY_MAP.md
    ├── OPERATIONS.md
    └── ARCHITECTURE.md
```

Evidence for structure: `ApiServer/`, `FrontendWebServer/`, `README.md`, and the tree from current directory.

## Path Guide

| Path | Purpose | Key Files Inside | Notes (Entrypoint/Config/Data) |
|---|---|---|---|
| `ApiServer/` | Backend API service | `src/main.py`, `pyproject.toml`, `requirements.txt` | Python/FastAPI service root. |
| `ApiServer/src/main.py` | Backend application entrypoint | `FastAPI(...)`, router registration, `/health` | Primary ASGI app object (`app`). |
| `ApiServer/src/deps.py` | Dependency wiring | DB/Redis/storage/auth dependencies | Requires `DATABASE_URL`; creates async SQLAlchemy engine. |
| `ApiServer/src/auth/` | Auth endpoints and token logic | `router.py`, `config.py`, `security.py` | Session cookie behavior and auth env settings. |
| `ApiServer/src/routes/` | API endpoint modules | `documents.py`, `requirements.py`, `reports.py`, etc. | Route-level business flows and request/response schemas. |
| `ApiServer/src/shared/` | Shared domain and infrastructure logic | `models.py`, `orm_models.py`, `repository.py`, `storage.py` | Core entities, DB models, storage adapter, utility code. |
| `ApiServer/alembic/` | Migration runtime | `env.py`, `script.py.mako` | Reads `DATABASE_URL`; applies migration history. |
| `ApiServer/alembic/versions/` | DB schema evolution history | `001_...py` ... `019_...py` | Interface/contract changes at DB layer. |
| `ApiServer/templates/` | Template contract data | `demo_cert.json`, `lms_certificate.json` | Runtime template registry input (`TEMPLATES_DIR` default). |
| `ApiServer/tests/` | Backend test suites | `unit/`, `integration/`, `ocr/`, `performance/`, `security/` | Integration fixtures call out service dependencies. |
| `FrontendWebServer/` | Frontend web app | `package.json`, `src/main.tsx`, `src/App.tsx` | Vite + React + TypeScript app root. |
| `FrontendWebServer/src/main.tsx` | Frontend entrypoint | React root mount | Mounts app from `index.html` to `#root`. |
| `FrontendWebServer/src/App.tsx` | Route composition and role gating | `ProtectedRoute` usage, route definitions | Main router map and role restrictions. |
| `FrontendWebServer/src/api/` | API client/contracts | `client.ts`, `auth.ts`, `index.ts` | Uses `VITE_API_URL` with localhost fallback. |
| `FrontendWebServer/src/pages/` | Route-level screens | `DashboardPage.tsx`, `UploadPage.tsx`, etc. | High-change UI workflow surfaces. |
| `FrontendWebServer/public/logos/` | Static brand assets | `CityOfLaredoLogo.png`, `CityOfLaredoPublicHealthLogo.png` | User-facing static image assets. |
| `README.md` | Directory summary | top-level component list | Current text references `SqlDatabase` path that is absent. |
| `docs/` | Root-level developer docs for this directory | this doc set | Local runbook/architecture/index for `CoreInstances`. |

## Interfaces and Contract Files

| Path | Contract Type | Evidence-backed Use |
|---|---|---|
| `ApiServer/src/routes/schemas.py` | API request/response DTOs | Pydantic models used by route handlers. |
| `ApiServer/src/auth/schemas.py` | Auth request/response DTOs | Login/token/user payload shape. |
| `ApiServer/src/shared/models.py` | Domain entities and enum contracts | Shared role/status/review/data model semantics. |
| `ApiServer/src/shared/orm_models.py` | Database schema contract | SQLAlchemy table/constraint definitions. |
| `ApiServer/alembic/versions/` | Schema-change history contract | Ordered migration revisions for DB evolution. |
| `ApiServer/templates/*.json` | Template extraction contract | JSON template definitions loaded by registry. |
| `FrontendWebServer/src/api/index.ts` | Frontend API contract wrappers | Interface and function wrappers for backend endpoints. |
| `FrontendWebServer/src/types/auth.ts` | Frontend auth type contract | Role/user/auth context typing. |

## Shared Build/Run Anchors (Outside This Directory)

These files live in the parent project root and are referenced because they directly define how `CoreInstances` services are built and run.

| Path | Purpose | Why It Matters For CoreInstances |
|---|---|---|
| `../Makefile` | Canonical local commands (`setup`, `up`, `db-migrate`, `test`, `lint`, logs/shell helpers) | Primary operator interface for API + frontend + dependencies. |
| `../docker-compose.yml` | Development stack service graph and env wiring | Defines `api` and `frontend` services plus Postgres/Redis/MinIO and dev dependencies. |
| `../docker-compose.prod.yml` | Production stack orchestration | Defines production service images and runtime env handoff for API/frontend/workers. |
| `../docker/api/Dockerfile.dev` | Backend dev runtime command | Uses `uvicorn ... --reload` for API dev container startup. |
| `../docker/api/Dockerfile` | Backend prod runtime command | Uses `gunicorn` with `uvicorn.workers.UvicornWorker`. |
| `../docker/frontend/Dockerfile.dev` | Frontend dev runtime command | Runs Vite dev server in container. |
| `../docker/frontend/Dockerfile` | Frontend prod runtime image | Builds static assets and serves via Nginx. |
| `../.env.example` | Environment template | Enumerates expected env variable names used by compose services. |

## Hotspots

- `ApiServer/src/routes/`: API behavior changes and endpoint additions are concentrated here. Evidence: route imports/registration in `ApiServer/src/main.py`.
- `ApiServer/src/shared/`: cross-cutting domain model and infrastructure changes propagate from here. Evidence: `ApiServer/src/shared/models.py`, `ApiServer/src/shared/orm_models.py`, `ApiServer/src/shared/repository.py`.
- `ApiServer/alembic/versions/`: schema-affecting features require new revisions here. Evidence: `ApiServer/alembic/versions/`.
- `FrontendWebServer/src/pages/` and `FrontendWebServer/src/api/`: most UI workflow and API wiring updates land here. Evidence: `FrontendWebServer/src/App.tsx`, `FrontendWebServer/src/api/index.ts`.
