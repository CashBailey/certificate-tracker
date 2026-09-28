# Open Issues

Last reviewed: 2026-07-12

This file tracks the remaining product gaps worth pursuing after verification and manual UI review.

Related evidence:
- `verification/results/manual-na-clearance-2026-04-21.md` (path is informational; file is not part of the wiki scope)

## Active UI Issues

### 1. Requirement assignment creation UI

Status: Resolved (2026-07-12)

Coordinators can now create a requirement assignment from the Requirements page
("+ Assign Requirement"). The modal has debounced employee search, certificate-type
and due-date pickers, and surfaces the API's duplicate-guard message. The API now
rejects a second *open* requirement for the same employee + certificate type with
HTTP 409 (satisfied/waived history does not block a new cycle). Verified by
`e2e/verify-requirement-actions.mjs` and `tests/unit/test_requirements_create_duplicate.py`.

### 2. Waive action in the requirements UI

Status: Resolved (2026-07-12)

Coordinators see a "Waive" action on open requirement rows. The modal captures a
waiver reason (min 10 chars, enforced) and an optional expiration; the row flips to
Waived after the action. Verified by `e2e/verify-requirement-actions.mjs`.

### 3. Unwaive action in the requirements UI

Status: Resolved (2026-07-12)

Waived requirement rows show an "Unwaive" action that restores the requirement to
its active status. Verified by `e2e/verify-requirement-actions.mjs`.

## Needs Product Decision

### Requirement due-date repair

Status: Blocked on an authoritative business-data source.

Migration `027_backfill_requirement_due_dates.py` overwrote satisfied requirement
deadlines with certificate expiration calculations. In the current development
database, all 3,344 comparable satisfied rows match that formula. The original
deadlines were not retained, so an automatic rewrite would invent compliance
dates. Future review processing now preserves the requirement deadline and
derives certificate expiration only on the verified certificate record.

Decision needed:
- Identify the system of record for historical requirement deadlines, import a
  reviewed repair mapping, and audit every corrected row.
- Do not infer deadlines from certificate issue/expiration data.

### Deterministic email delivery after SMTP acceptance

Status: Architectural limitation.

Notification rows and generation keys are deterministic, but SMTP has no
transaction shared with PostgreSQL. A worker crash after SMTP accepts a digest
and before the delivery flag commits can resend it. Resolving this requires an
email provider with idempotency support or a persisted delivery-attempt/outbox
contract; marking rows delivered before SMTP would instead lose messages.

### Inbound sender authentication

Status: Blocked on production mail-gateway policy/evidence.

The intake worker can validate the parsed sender, but it cannot establish SPF,
DKIM, DMARC, or trusted transport headers by itself. Production deployment must
document and test the MTA rule that rejects or quarantines spoofed City sender
addresses before they reach the monitored mailbox.

### 4. Multi-file upload support

Status: Undecided

Current state:
- The upload UI currently uses a single-file input.
- The browser-side form does not support queueing multiple files at once.

Decision needed:
- If single-file upload is the intended behavior, leave as-is and remove any multi-file expectation from future browser audits.
- If multi-file upload is desired, this becomes an active UI enhancement.

## Not Currently Treated As Bugs

These were reviewed and are not being tracked as active issues under the current scope.

### Employee department editing

Reason:
- Department editing is not a current concern for the project.

### Bulk CSV requirement import

Reason:
- Bulk import is considered a migration/startup concern rather than a normal day-to-day UI workflow.

### Post-creation template editing/versioning

Reason:
- Templates can be edited during creation.
- Post-creation versioning or edit-after-save is not currently being treated as a required product feature.

---

## Deferred decisions (2026-04-22)

These items require product, security, or architect input before action. Each has grep-level evidence of zero in-code callers but their shape suggests "paused feature" rather than "abandoned effort."

### 5. Retention / legal-hold subsystem (R1–R6)

Status: Undecided — needs product input.

Current state:
- Six methods in `CoreInstances/ApiServer/src/shared/repository.py`, ~250 LOC:
  - `:1655` `soft_delete_document`
  - `:1716` `set_document_legal_hold`
  - `:1739` `set_verified_record_legal_hold`
  - `:1762` `list_documents_for_retention_purge`
  - `:1798` `create_deletion_tombstone`
  - `:1831` `hard_delete_document`
- Zero callers anywhere in the monorepo (only internal cross-call: `hard_delete_document` → `create_deletion_tombstone` at `repository.py:1879`).
- None of these methods are declared in `RepositoryProtocol` at `src/shared/protocols.py`.
- Backed by DB columns added in `alembic/versions/008_add_retention_fields.py` — columns exist, no reader/writer.

Decision needed:
- If retention/legal-hold is a planned feature: wire it up (routes + Protocol + admin UI) as a future initiative.
- If abandoned: prune code + Protocol + new Alembic migration to drop the migration-008 columns + any ORM fields + related fixtures as one coordinated change.
- Coupled with item 6 (split repo) — the retention methods may have been planned to live in `DocumentRepository` if the split had finished.

### 6. Split repository package (A1)

Status: Undecided — needs architect input.

Current state:
- Package at `CoreInstances/ApiServer/src/shared/repositories/`:
  - `base.py` — `BaseRepository`
  - `document.py` — `DocumentRepository`
  - `employee.py` — `EmployeeRepository`
  - `extraction.py` — `ExtractionRepository`
  - `__init__.py` — re-exports
- `src/deps.py:81` always returns the monolithic `SqlRepository`; no consumer imports the split classes.
- Appears to be an in-progress refactor to domain-specific repositories.

Decision needed:
- If the refactor is still planned: leave the package; finishing work goes into a dedicated branch.
- If abandoned: delete the 4 files + `__init__.py`. No test impact (no tests currently import them).
- Coupled with item 5 — if retention is planned, it probably wants to live in `DocumentRepository`.

### 7. Dead-letter queues: design gap (E7 / OCR-DLQ)

Status: Resolved (2026-07-12).

Current state:
- `BackgroundProcessingInstances/ExtractionWorker/src/worker.py:43,657,696` enqueue failed jobs to `extraction_tasks:dead_letter`.
- OCR worker similarly writes to `ocr_tasks:dead_letter`.
- `scripts/replay_dlq.py` now lists and replays Extraction/OCR dead letters, and
  `make dlq-list` / `make dlq-replay` make the recovery path discoverable.
- DLQ payload inspection is bounded/redacted; OCR failures no longer retain the
  full base64 document image.

Remaining operational work: connect queue-depth alerts to the production
monitoring system. The repository-local recovery workflow is complete.

### 8. Frontend prod Docker path (I9)

Status: Undecided — needs deployment-architect input.

Current state:
- `docker/frontend/Dockerfile` (multi-stage nginx prod build, 38 lines) and `docker/frontend/nginx.conf` exist.
- Not referenced by `docker-compose.yml` (uses `Dockerfile.dev`), `Makefile`, `.github/workflows/`, or any script.
- Docs reference a `docker-compose.prod.yml` that does not exist in the repo.
- **Asymmetry note:** `docker/api/Dockerfile` (prod) IS used by CI at `.github/workflows/ci.yml:179` — the frontend prod Dockerfile mirrors this but was never wired up.

Decision needed:
- If prod deployment is planned: add `docker-compose.prod.yml` using the existing prod Dockerfile.
- If not planned: delete `docker/frontend/Dockerfile` + `docker/frontend/nginx.conf` and update docs that reference them.
- The asymmetry with the working `docker/api/Dockerfile` prod path suggests partial in-progress work.

### 9. ClamAV coverage on api upload path

Status: Undecided — needs security review.

Current state:
- Only `email-intake-worker` scans for malware (via `malware_scanner.py`).
- Direct file uploads via the api (e.g. `POST /api/documents`) are not scanned before persisting to MinIO.
- This is a security-posture question, not an engineering-cleanup item.

Decision needed:
- If scanning is required symmetrically: implement ClamAV integration in the api upload route (feature work).
- If email-intake as the single scanning boundary is intentional: document the design + threat-model rationale in `docs/` and close this as accepted risk.
- Security review should own this decision, not engineering cleanup.

### Decision recorded (no action needed)

**F9 `/reports` → `/compliance` redirect** (`App.tsx:111`) — **KEEP**. The single-line redirect preserves external bookmarks and training-material links. The user-facing 404 risk outweighs saving one line. Closed as kept-intentional.

**A8 `slowapi._rate_limit_exceeded_handler` import** (`main.py:15`) — **KEEP** per existing `# noqa: F401 (kept for backward-compat)` annotation. Closed as kept-intentional.

**tokenStorage back-compat stubs** (`api/client.ts:52,57`) — **KEEP** per `// Backward-compat stub` annotations. Closed as kept-intentional.

**Scheduler private fallback constants** (`_DEFAULT_REQUIREMENT_REMINDER_DAYS`, `_DEFAULT_CERTIFICATE_REMINDER_DAYS`) — **KEEP** per `docs/ARCHITECTURE.md:70,96` design documentation.
