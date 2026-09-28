# Architecture (Scoped)

This document covers only:

- `CoreInstances/ApiServer`
- `CoreInstances/FrontendWebServer`
- `BackgroundProcessingInstances/EmailIntakeWorker`
- `BackgroundProcessingInstances/ExtractionWorker`
- `BackgroundProcessingInstances/OcrEngine`
- `BackgroundProcessingInstances/SchedulerNotificationWorker`

## High-Level Component View

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

## Module Responsibilities

| Path | Responsibility |
| --- | --- |
| `CoreInstances/FrontendWebServer/src/` | User-facing web app and API client integration |
| `CoreInstances/ApiServer/src/` | API host, route layer, auth, queue enqueue, persistence orchestration |
| `BackgroundProcessingInstances/EmailIntakeWorker/src/` | Email polling, sender validation, attachment handling, extraction enqueue |
| `BackgroundProcessingInstances/ExtractionWorker/src/` | Main extraction worker, template/generic extraction pipeline, OCR coordination |
| `BackgroundProcessingInstances/OcrEngine/src/` | OCR worker consuming OCR tasks and publishing OCR results |
| `BackgroundProcessingInstances/SchedulerNotificationWorker/src/` | Scheduled job runner: reads alert configuration from the `alert_configuration` table, polls the database for upcoming certificate expirations and requirement due dates, and sends email notifications at the configured reminder day offsets. Supports a daily overdue digest (togglable via configuration). |

## Primary Data Flow

1. Frontend uploads a document to the API.
2. API stores object metadata/state and enqueues `extraction_tasks`.
3. Extraction worker consumes `extraction_tasks` and runs extraction logic.
4. If OCR is needed, extraction worker sends a task to `ocr_tasks`.
5. OCR engine processes the image/PDF text pass and writes `ocr_results:<request_id>`.
6. Extraction worker merges OCR output and persists extraction/review state updates.
7. Email intake worker performs an alternate ingestion path (IMAP) and enqueues the same extraction pipeline.
8. Scheduler worker reads the `alert_configuration` singleton from the database for reminder day offsets, daily overdue toggle, and send time. It polls for certificates and requirements matching those offsets and sends notifications accordingly.

## Configuration Domain

The system exposes a Coordinator-managed Configuration section (replaces the former Upload card on the dashboard):

- **Certificate Types** — CRUD for certificate type definitions. Each type owns a `validity_period_days` (nullable for non-expiring types). Requirements reference certificate types by ID.
- **Alert Rules** — Singleton `alert_configuration` table controlling: requirement reminder day offsets, certificate reminder day offsets, daily overdue toggle, and global send time (hour + minute). The Scheduler worker reads this table at each run.
- **Issuing Authority** — Template-level metadata (`issuing_authority`, `certificate_type_ref`) stored on `TemplateDefinition`. The extraction pipeline uses `hardcoded_value` on `FieldZone` to inject template-authoritative values.
- **Audit Log** — Append-only audit trail. All mutating operations emit audit events via the shared `audit_employee_action` helper. Events carry dual timestamps (`occurred_at_utc`, `recorded_at_utc`), actor role, correlation ID, source service, and outcome. Admin-only read access.

## Contracts In Scope

- HTTP contracts: `CoreInstances/ApiServer/src/routes/schemas.py`, `CoreInstances/ApiServer/src/auth/schemas.py`
- Queue contracts: API + worker queue payload handling in:
  - `CoreInstances/ApiServer/src/routes/documents.py`
  - `BackgroundProcessingInstances/ExtractionWorker/src/worker.py`
  - `BackgroundProcessingInstances/OcrEngine/src/worker.py`
  - `BackgroundProcessingInstances/EmailIntakeWorker/src/worker.py`
- Persistence contracts: `CoreInstances/ApiServer/alembic/versions/*.py`
- **Service mesh / mTLS:** All east-west connections (API/workers → PostgreSQL, Redis, MinIO) use mutual TLS authenticated by a project-internal CA. The shared helper `CoreInstances/ApiServer/src/shared/tls.py` provides `build_ssl_context()` (for asyncpg/urllib3) and `redis_tls_kwargs()` (for redis-py), both gated on `TLS_ENABLED=true`. See [docs/TLS.md](TLS.md) for certificate setup and full reference.

## API URL Routing — `/api/auth/*` vs `/api/api/<router>/*`

The external URL surface is asymmetric for historical reasons. **Do not "fix" this without coordinated frontend + backend changes.**

- **Caddy** (reverse proxy on `:443`) routes any external request matching `/api/*` to the API container, **stripping the leading `/api`**. So external `/api/foo` → API server receives `/foo`.
- **Inside the API**, routers are mounted in `CoreInstances/ApiServer/src/main.py`:
  - `auth_router` is mounted **bare** (`app.include_router(auth_router)`) and the router itself declares `prefix="/auth"`. So the API server handles `/auth/login` internally → external URL is `/api/auth/login`. **One `/api` external.**
  - All other routers (`admin_router`, `notifications_router`, `employees_router`, `extractions_router`, etc.) are mounted **with** `prefix="/api"`. So the API server handles `/api/notifications/*` internally → external URL is `/api/api/notifications/*`. **Two `/api` external.**

**Verification:** `https://localhost/api/notifications/unread-count` returns `404`; `https://localhost/api/api/notifications/unread-count` returns `401` (route exists, auth required).

**Frontend literals** in `CoreInstances/FrontendWebServer/src/api/index.ts` use `/api/notifications/...`, `/api/employees/...`, `/api/extractions/...` — these are correct for the current asymmetric mounting and should NOT be changed in isolation. The `apiFetch` helper in `api/client.ts` prepends `API_URL` (default `/api`), producing the correct double-prefix.

**To consolidate this** (recommended cleanup), change ALL routers in `main.py` to one consistent pattern (either all bare with `/api` prefixes declared on the routers themselves, or all mounted with `prefix="/api"`), then update the matching frontend literals in lockstep. Treat as an isolated cleanup PR — do not bundle with feature work.

## Notes

- This architecture intentionally omits non-scoped services and folders.
- Root-level infrastructure files are referenced only where they wire the scoped components.
