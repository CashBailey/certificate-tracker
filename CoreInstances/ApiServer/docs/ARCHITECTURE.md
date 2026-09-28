# Architecture

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.

## High-Level Overview

`ApiServer` is the HTTP/API boundary for the system. It exposes auth and business routes, coordinates persistence and storage dependencies, and hands off extraction work through Redis-backed queue messages. The service is orchestrated as `api` in root compose and depends on healthy `postgres`, `redis`, and `minio` services. (Evidence: `src/main.py`, `src/routes/documents.py`, `src/deps.py`, `../../docker-compose.yml` service `api` with `depends_on`)

## Deployment/Runtime Topology

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

(Evidence: `src/main.py`, `src/routes/__init__.py`, `src/routes/documents.py`, `src/shared/repository.py`, `src/shared/storage.py`, `../../docker-compose.yml`)

## Runtime Entry Variants

| Context | Entrypoint | Command Source |
|---|---|---|
| Dev container | `src.main:app` | `../../docker/api/Dockerfile.dev` CMD (`uvicorn ... --reload`) |
| Production build recipe | `src.main:app` | `../../docker/api/Dockerfile` CMD (`gunicorn ... uvicorn worker`) |
| Production compose runtime | `laredo-certs/api:latest` image | `../../docker-compose.prod.yml` (`api.image`) |

## Router And Access Model

`src/main.py` mounts `auth` routes directly and all business routers under `/api`.

| Router | Module | Prefix | Primary Guard |
|---|---|---|---|
| Authentication | `src/auth/router.py` | `/auth` | `get_current_user` on protected auth endpoints |
| Admin | `src/routes/admin.py` | `/api/admin` | `require_coordinator_or_admin` |
| Audit Logs | `src/routes/audit_logs.py` | `/api/audit-logs` | `require_coordinator_or_admin` |
| Certificate Types | `src/routes/certificate_types.py` | `/api/certificate-types` | `get_current_user` |
| Documents | `src/routes/documents.py` | `/api/documents` | mostly `require_coordinator` |
| Employees | `src/routes/employees.py` | `/api/employees` | `require_coordinator_or_admin` |
| Extractions | `src/routes/extractions.py` | `/api/extractions` | `require_coordinator` |
| Notifications | `src/routes/notifications.py` | `/api/notifications` | `get_current_user` |
| Reports | `src/routes/reports.py` | `/api/reports` | `require_coordinator` |
| Requirements | `src/routes/requirements.py` | `/api/requirements` | `require_coordinator` |
| Templates | `src/routes/templates.py` | `/api/templates` | `require_coordinator` |
| Verified Records | `src/routes/verified_records.py` | `/api/verified-records` | `require_coordinator` |

(Evidence: `src/main.py`, `src/auth/router.py`, `src/routes/admin.py`, `src/routes/documents.py`, `src/routes/requirements.py`, `src/routes/extractions.py`, `src/routes/reports.py`, `src/routes/templates.py`, `src/routes/notifications.py`, `src/routes/employees.py`, `src/routes/verified_records.py`, `src/routes/audit_logs.py`, `src/routes/certificate_types.py`, `src/deps.py`)

## Module Responsibilities

| Module/Folder | Responsibility | Evidence |
|---|---|---|
| `src/main.py` | App creation, middleware, router registration, health/root endpoints | `src/main.py` |
| `src/deps.py` | Dependency providers (DB/repo/storage/redis) and auth guards. `get_current_user()` and `get_current_user_from_token()` compare the `token_version` claim in each JWT against the current DB value, raising 401 "Session invalidated" on mismatch. | `src/deps.py` |
| `src/auth/` | Login/refresh/logout/password-change/forgot-password/reset-password flows and JWT utilities. Token payloads embed `token_version` (sourced from `employees.token_version`); password change increments this value, invalidating all prior tokens. Password validation enforces only min length (8) and max length (128) — no composition rules per NIST SP 800-63B. Passwords are hashed with Argon2id; legacy bcrypt hashes are upgraded transparently on login. Rate-limiting (slowapi) is applied to login and forgot-password endpoints. | `src/auth/router.py`, `src/auth/service.py`, `src/auth/security.py`, `src/auth/config.py`, `src/auth/schemas.py` |
| `src/routes/employees.py` | Employee CRUD. New employees are created with `password_hash = NULL`; a setup email containing a one-time `/reset-password` link is sent automatically on creation. Coordinators/Admins cannot set passwords for others. `POST /{id}/send-setup-email` resends the link. | `src/routes/employees.py`, `src/auth/service.py` |
| `src/routes/` | Endpoint-level business workflows | `src/routes/documents.py`, `src/routes/requirements.py`, `src/routes/extractions.py`, `src/routes/reports.py`, etc. |
| `src/review.py` | Review approval/rejection workflow with optimistic concurrency | `src/review.py` |
| `src/authorizer.py` | RBAC and separation-of-duties checks | `src/authorizer.py` |
| `src/shared/models.py` | Domain enums/entities | `src/shared/models.py` |
| `src/shared/protocols.py` | Interface contracts and domain exceptions | `src/shared/protocols.py` |
| `src/shared/orm_models.py` | SQLAlchemy DB mapping/constraints | `src/shared/orm_models.py` |
| `src/shared/repository.py` | Monolithic repository implementation | `src/shared/repository.py` |
| `src/shared/repositories/` | Split repository modules | `src/shared/repositories/__init__.py` |
| `src/shared/storage.py` | MinIO/S3-compatible storage implementation with mTLS support | `src/shared/storage.py` |
| `src/shared/tls.py` | Shared mTLS helper: `build_ssl_context()` for asyncpg/urllib3, `redis_tls_kwargs()` for redis-py; gated on `TLS_ENABLED=true` | `src/shared/tls.py` |
| `src/shared/template_registry.py` | Template loading/validation/version selection | `src/shared/template_registry.py` |
| `alembic/` | Migration runtime + revision history | `alembic.ini`, `alembic/env.py`, `alembic/versions/` |
| `templates/` | Template data consumed by template APIs/registry | `templates/demo_cert.json`, `templates/lms_certificate.json` |

## Data Flow

### Upload -> Queue

1. File upload enters `/api/documents`.
2. API validates file bytes and filename.
3. API stores file in object storage and creates document/extraction records.
4. API enqueues extraction task on Redis (`extraction_tasks`).

(Evidence: `src/routes/documents.py`, `src/shared/file_validation.py`, `src/shared/storage.py`)

### Review -> Verified Record

1. Coordinator calls approve/reject extraction endpoints.
2. Review service validates state and applies optimistic-lock transition.
3. Approval path writes verified record and links requirement when applicable.

(Evidence: `src/routes/extractions.py`, `src/review.py`)

### Reporting

1. Reports endpoints bulk-load employees/requirements/cert types/verified records.
2. Status computation utilities derive compliance/lifecycle statuses.
3. Results are emitted as JSON/CSV/XLSX.

(Evidence: `src/routes/reports.py`, `src/shared/status_computation.py`)

### Templates

1. Template routes read/write JSON files (`templates` or `TEMPLATES_DIR`).
2. Registry enforces canonical field names and bbox validity.
3. Registry returns latest/specific versions by template ID.

(Evidence: `src/routes/templates.py`, `src/shared/template_registry.py`, `templates/demo_cert.json`, `templates/lms_certificate.json`)

## Configuration Model

| Configuration Source | Scope | Evidence |
|---|---|---|
| Root compose + `.env` | Service-level runtime env and wiring | `../../docker-compose.yml`, `../../docker-compose.prod.yml` |
| Dependency/env guards in code | Runtime-required values and defaults | `src/deps.py`, `src/auth/config.py`, `src/shared/storage.py`, `src/shared/email_sender.py` |
| Alembic config | Migration execution model | `alembic.ini`, `alembic/env.py` |
| Python project config | pytest/coverage/ruff + Python version | `pyproject.toml` |
| Route/auth schemas | API contracts | `src/routes/schemas.py`, `src/auth/schemas.py` |
| mTLS env vars | Service-to-service TLS (east-west); all resolved by `src/shared/tls.py` | `TLS_ENABLED`, `TLS_CA_CERT`, `TLS_CLIENT_CERT`, `TLS_CLIENT_KEY` (see `docs/TLS.md`) |

## Extension Points

- Add new endpoint domain: add `src/routes/<new>.py`, export in `src/routes/__init__.py`, include in `src/main.py`.
- Extend persistence: update contracts in `src/shared/protocols.py`, implement in `src/shared/repository.py` and/or `src/shared/repositories/`.
- Add schema changes: add Alembic revision in `alembic/versions/`.
- Add template support: add/update JSON templates and satisfy registry validation constraints.

(Evidence: `src/routes/__init__.py`, `src/main.py`, `src/shared/protocols.py`, `src/shared/repository.py`, `alembic/versions/`, `src/shared/template_registry.py`)
