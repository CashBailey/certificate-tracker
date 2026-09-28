# CoreInstances Architecture

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.

## High-Level Overview

`CoreInstances` contains two cooperating application runtimes. `FrontendWebServer` provides a browser UI (React + Vite) and calls backend HTTP endpoints. `ApiServer` provides authenticated API routes, persistence, object storage integration, queue handoff for extraction work, and schema migrations. Evidence: `FrontendWebServer/src/main.tsx`, `FrontendWebServer/src/App.tsx`, `FrontendWebServer/src/api/client.ts`, `ApiServer/src/main.py`, `ApiServer/src/routes/documents.py`, `ApiServer/alembic/env.py`.

Runtime orchestration for these services is defined at the parent project root with Docker Compose and Make targets. This is the canonical stack startup path for local and production modes. Evidence: `../Makefile`, `../docker-compose.yml`, `../docker-compose.prod.yml`.

The backend starts a FastAPI app and registers route modules for auth, documents, extraction/review, requirements, reports, templates, and admin workflows. Frontend route access is role-gated through `ProtectedRoute`, and API calls are centralized in the frontend API client layer with refresh-cookie token recovery logic. Evidence: `ApiServer/src/main.py`, `ApiServer/src/routes/`, `FrontendWebServer/src/App.tsx`, `FrontendWebServer/src/components/ProtectedRoute.tsx`, `FrontendWebServer/src/api/client.ts`.

## Component Diagram

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

## Entrypoint Selection

| Entrypoint | Use It For | Evidence |
|---|---|---|
| `ApiServer/src/main.py` | API runtime startup, router wiring, health/root endpoints | `ApiServer/src/main.py` |
| `ApiServer/alembic/env.py` | Migration runtime wiring and DB URL adaptation | `ApiServer/alembic/env.py` |
| `FrontendWebServer/src/main.tsx` | Frontend runtime bootstrap into DOM root | `FrontendWebServer/src/main.tsx`, `FrontendWebServer/index.html` |
| `FrontendWebServer/src/App.tsx` | Route topology and role-based screen access | `FrontendWebServer/src/App.tsx`, `FrontendWebServer/src/components/ProtectedRoute.tsx` |
| `../Makefile` | Command façade for stack lifecycle and operator tasks | `../Makefile` |
| `../docker-compose.yml` | Development service graph and environment wiring | `../docker-compose.yml` |
| `../docker-compose.prod.yml` | Production service graph using prebuilt images | `../docker-compose.prod.yml` |

## Module Responsibilities

| Module/Folder | Responsibility | Evidence |
|---|---|---|
| `ApiServer/src/main.py` | Creates FastAPI app, middleware, and router registration | `ApiServer/src/main.py` |
| `ApiServer/src/auth/` | Login/refresh/logout flows, JWT config, password/security helpers | `ApiServer/src/auth/router.py`, `ApiServer/src/auth/config.py`, `ApiServer/src/auth/security.py` |
| `ApiServer/src/routes/` | Endpoint implementations for documents/review/reports/templates/admin/etc. | `ApiServer/src/routes/*.py` |
| `ApiServer/src/shared/models.py` | Domain entities and enums used across routes/services | `ApiServer/src/shared/models.py` |
| `ApiServer/src/shared/orm_models.py` | SQLAlchemy schema/constraints for persistence model | `ApiServer/src/shared/orm_models.py` |
| `ApiServer/src/shared/repository.py` | Data-access abstraction and DB persistence operations | `ApiServer/src/shared/repository.py` |
| `ApiServer/alembic/` | Migration runtime + revision history | `ApiServer/alembic.ini`, `ApiServer/alembic/env.py`, `ApiServer/alembic/versions/` |
| `ApiServer/templates/` | JSON template contracts loaded at startup/runtime | `ApiServer/templates/*.json`, `ApiServer/src/routes/templates.py`, `ApiServer/src/shared/template_registry.py` |
| `FrontendWebServer/src/App.tsx` | Route topology + role-gated views | `FrontendWebServer/src/App.tsx` |
| `FrontendWebServer/src/api/` | HTTP wrappers, token/session behavior, frontend-side API contracts | `FrontendWebServer/src/api/client.ts`, `FrontendWebServer/src/api/index.ts`, `FrontendWebServer/src/api/auth.ts` |
| `FrontendWebServer/src/pages/` | User-facing workflow screens | `FrontendWebServer/src/pages/*.tsx` |
| `FrontendWebServer/src/types/` | Shared TypeScript type contracts for auth/domain objects | `FrontendWebServer/src/types/auth.ts` |
| `../Makefile` | Stack lifecycle, logs, shell, migration, test/lint command entrypoints | `../Makefile` |
| `../docker/api/Dockerfile*` | Backend container runtime commands (dev/prod) | `../docker/api/Dockerfile.dev`, `../docker/api/Dockerfile` |
| `../docker/frontend/Dockerfile*` | Frontend container runtime commands (dev/prod) | `../docker/frontend/Dockerfile.dev`, `../docker/frontend/Dockerfile` |

## Key Conventions

| Convention | Rule | Evidence |
|---|---|---|
| RBAC role model | Roles are `Coordinator`, `Admin`, `Employee`; certificate operations are coordinator-gated. | `ApiServer/src/shared/models.py`, `ApiServer/src/authorizer.py`, `FrontendWebServer/src/types/auth.ts` |
| Separation of duties for review | Coordinator cannot review certificates that belong to them (employee_id match), but CAN review certificates they uploaded for other employees. | `ApiServer/src/authorizer.py`, `ApiServer/src/routes/extractions.py` |
| Review state machine | `Processing -> PendingReview -> (Approved or Rejected)`; review requires `PendingReview`. | `ApiServer/src/shared/models.py`, `ApiServer/src/review.py` |
| Optimistic concurrency on review | Review transitions validate expected state/version and raise conflict on concurrent modification. | `ApiServer/src/review.py` |
| Upload validation contract | Allowed types: PDF/PNG/JPEG/TIFF; default max upload size: 20 MB; MIME detection uses file bytes. | `ApiServer/src/shared/file_validation.py`, `FrontendWebServer/src/pages/UploadPage.tsx` |
| Session token model | Access token kept in-memory; refresh via httpOnly cookie + `/auth/refresh`; failed refresh triggers logout flow. | `ApiServer/src/auth/router.py`, `FrontendWebServer/src/api/client.ts`, `FrontendWebServer/src/contexts/AuthContext.tsx` |
| Template geometry contract | Template zone coordinates are normalized `[0,1]` with `x0<x1` and `y0<y1`; canonical fields enforced. | `ApiServer/src/routes/templates.py`, `ApiServer/src/shared/models.py` |

## Data Flow

1. User opens frontend routes and authenticates.
Evidence: `FrontendWebServer/src/App.tsx`, `FrontendWebServer/src/pages/LoginPage.tsx`, `FrontendWebServer/src/api/auth.ts`.
2. Frontend sends API requests to backend base URL (`VITE_API_URL` or fallback).
Evidence: `FrontendWebServer/src/api/client.ts`, `FrontendWebServer/src/api/index.ts`.
3. Backend validates access/session and executes route handlers.
Evidence: `ApiServer/src/deps.py`, `ApiServer/src/auth/router.py`, `ApiServer/src/routes/*.py`.
4. Document upload flow writes bytes to storage, creates DB records, and enqueues extraction task in Redis.
Evidence: `ApiServer/src/routes/documents.py`, `ApiServer/src/shared/storage.py`.
5. Template-based extraction/review artifacts and requirement/report data are persisted and returned to frontend.
Evidence: `ApiServer/src/routes/templates.py`, `ApiServer/src/routes/extractions.py`, `ApiServer/src/routes/requirements.py`, `ApiServer/src/routes/reports.py`.
6. Approved/derived data appears in UI pages and dashboards.
Evidence: `FrontendWebServer/src/pages/ReviewDetailPage.tsx`, `FrontendWebServer/src/pages/CompliancePage.tsx`, `FrontendWebServer/src/pages/RequirementsPage.tsx`.

## Configuration Model

| Config Type | Source | Purpose |
|---|---|---|
| Backend runtime env | `ApiServer/src/deps.py`, `ApiServer/src/auth/config.py`, `ApiServer/src/shared/storage.py`, `ApiServer/src/shared/email_sender.py` | DB/auth/storage/SMTP runtime wiring |
| Backend migration config | `ApiServer/alembic.ini`, `ApiServer/alembic/env.py` | Alembic migration execution and DB URL handoff |
| Backend Python/tooling config | `ApiServer/pyproject.toml` | Python version, pytest options, coverage/ruff behavior |
| Backend dependency list | `ApiServer/requirements.txt` | Python package inventory |
| Frontend build/runtime config | `FrontendWebServer/package.json`, `FrontendWebServer/vite.config.ts`, `FrontendWebServer/src/vite-env.d.ts` | Scripts, dev server setup, env typing |
| Frontend API target env | `FrontendWebServer/src/api/client.ts` and related API files | Backend base URL resolution |
| Stack orchestration config | `../Makefile`, `../docker-compose.yml`, `../docker-compose.prod.yml` | Service lifecycle and cross-service wiring |
| Shared env template | `../.env.example` | Standard environment variable names for compose-based stack |

## Extension Points

1. Add backend endpoint/module:
Create route module under `ApiServer/src/routes/` and register it in `ApiServer/src/main.py`.
2. Add backend schema capability:
Update ORM/domain models and add an Alembic revision under `ApiServer/alembic/versions/`.
3. Add/modify extraction templates:
Add or update JSON files in `ApiServer/templates/` (or configured `TEMPLATES_DIR`) and use template routes.
4. Add frontend page:
Create page under `FrontendWebServer/src/pages/`, then wire route + role guard in `FrontendWebServer/src/App.tsx`.
5. Add frontend API integration:
Add contract/wrapper in `FrontendWebServer/src/api/` and consume it from pages/components.
6. Add or change stack lifecycle commands:
Update `../Makefile` targets and/or compose manifests (`../docker-compose.yml`, `../docker-compose.prod.yml`) when runtime topology changes.
