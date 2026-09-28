# Browser Test README — City of Laredo Certificate Management System

**Purpose:** Browser-executable end-to-end test catalog exercised **through the browser**, covering the user-visible flows that can be claimed from a browser session alone.

Each test has a stable ID (e.g. `T-AUTH-003`) so the suite is addressable from tickets and automation. Run the **SMOKE** set on every build; run the full matrix before any release.

---

## 0. How to use this document

- **Scope:** UI-driven verification only. The automated browser audit is intentionally limited to the supported set in `e2e/browser-audit-scope.mjs`.
- **Project-wide replacements:** non-browser checks now live in `docs/PROJECT_VERIFICATION.md` and `make verify-project`.
- **Environment:** Tests assume the default local compose stack (Caddy at `https://localhost`, API at `https://localhost/api`, Greenmail at `localhost:3025` SMTP / `localhost:8080` HTTP). Adjust for staging/prod.
- **Status flags:** mark each test `PASS`, `FAIL`, `BLOCKED`, or `N/A` with evidence (screenshot, HAR, DB query output).
- **Ordering:** work top-down. Later tests assume earlier tests passed (e.g., you cannot run Review workflow tests if Upload is broken).
- **Durability:** on any `FAIL`, capture: (a) the request/response in DevTools Network, (b) the audit_logs row written (if any), (c) a screenshot of the UI state.

---

## 1. Pre-flight — environment setup

Before any browser test:

1. **Stack up:** `docker compose up -d` (or the project's `make up` / `just up` equivalent)
2. **Migrations at head:**
   ```bash
   docker exec laredo-api alembic current
   # expected: 037 (head) or later
   ```
3. **Seed data loaded:** confirm at least one Admin, one Coordinator, one Employee, and one Certificate Type exist.
   ```bash
   docker exec -e PGPASSWORD=laredo_dev_password laredo-postgres \
     psql -U laredo -d laredo_certificates -c "SELECT role, COUNT(*) FROM certificates.employees GROUP BY role;"
   ```
4. **Health endpoints green:**
   - `https://localhost/health` → 200
   - `https://localhost/api/health` → 200
5. **Browser state clean:** open a fresh incognito/private window per role to avoid cross-session token leakage.
6. **DevTools open** on every test run — Network tab (Preserve Log ON), Console, and Application → Cookies/Storage.

### 1.1 Test accounts matrix

| Role | Browser access | Intake path | Example test account |
|---|---|---|---|
| Admin | `/`, `/employees`, `/notifications`, `/audit`, `/admin` | Browser | `admin@test.local` |
| Coordinator | `/`, `/requirements`, `/upload`, `/review`, `/compliance`, `/configuration`, `/templates`, `/notifications`, `/employees` | Browser | `coord@test.local` |
| Employee | **none** (INV-06: email-only) | Email to watched inbox | `rachel@test.local` |

If accounts do not exist, an Admin creates Coordinators via `/employees` → Add. Employees are created likewise but never granted login credentials.

### 1.2 Authoritative route map (must match `App.tsx`)

| Path | Public? | Allowed roles |
|---|---|---|
| `/login` | yes | — |
| `/forgot-password` | yes | — |
| `/reset-password` | yes | — |
| `/` (Dashboard) | no | Coordinator, Admin |
| `/requirements` | no | Coordinator |
| `/upload` | no | Coordinator |
| `/review` | no | Coordinator |
| `/review/:id` | no | Coordinator |
| `/compliance` | no | Coordinator |
| `/configuration` | no | Coordinator |
| `/templates`, `/templates/new` | no | Coordinator |
| `/notifications` | no | Coordinator, Admin |
| `/employees` | no | Coordinator, Admin |
| `/reports` → redirects to `/compliance` | no | Coordinator |
| `/audit` | no | Admin |
| `/admin` | no | Admin |
| `/unauthorized` | no | any authenticated |
| `/*` (catch-all) | redirects to `/` | — |

### 1.3 Recommended tooling

- **Manual, high-signal:** Chrome (or Chromium) with DevTools. Primary harness.
- **Automated cross-browser:** Playwright MCP (`mcp__plugin_playwright_playwright__*`) — scripts live in `e2e/` (create if missing).
- **Accessibility:** axe DevTools browser extension, Lighthouse.
- **Performance:** Lighthouse (Performance, Best Practices, Accessibility ≥ 90).
- **Load / fuzz:** optional k6 or Locust against the API; not in this doc.

---

## 2. SMOKE — P0 critical path (must pass before every merge to main)

Minimum set to gate a deploy. Total runtime: ~10 minutes manually.

| ID | Test | Expected |
|---|---|---|
| `T-SMK-001` | Navigate to `https://localhost` with no session | 302/redirect to `/login` |
| `T-SMK-002` | Log in as Admin with correct credentials | Lands on `/`; name visible in header |
| `T-SMK-003` | Log out | Returns to `/login`; access token cleared; `/api/employees` retry returns 401 |
| `T-SMK-004` | Log in as Coordinator | Lands on `/` |
| `T-SMK-005` | Open `/upload`, drag a valid PDF, submit with `employee_id=1` | Success toast; document row appears in DB `certificates.documents` |
| `T-SMK-006` | Visit `/review` as Coordinator | Queue loads; at least one pending extraction visible after the pipeline runs (~30s–3min) |
| `T-SMK-007` | Approve the extraction | Row disappears from queue; audit_logs gets `action=extraction_approved, source_service=api` |
| `T-SMK-008` | Open `/compliance`, click **Export CSV** | File downloads, opens cleanly in spreadsheet; row count > 0 |
| `T-SMK-009` | Open `/audit` as Admin | Page loads; filter dropdowns populated; rows render |
| `T-SMK-010` | Close browser, reopen, hit `/` | Redirects to `/login` (refresh cookie path tested separately) |

A single FAIL here blocks release.

---

## 3. Authentication

### 3.1 Login

| ID | Test | Expected |
|---|---|---|
| `T-AUTH-001` | Login with correct Admin email + password | 200, access token in memory (not localStorage), refresh cookie set `HttpOnly; Secure; SameSite=Strict` (or Lax), redirect to `/` |
| `T-AUTH-002` | Login with correct Coordinator credentials | Same as above; no Admin-only nav items visible |
| `T-AUTH-003` | Login with wrong password | 401; generic "Invalid email or password" error; timing side-channel (use stopwatch — should not leak whether email exists) |
| `T-AUTH-004` | Login with unknown email | Same generic error as T-AUTH-003 |
| `T-AUTH-005` | Login with empty email | Client-side required-field error; no network call fired |
| `T-AUTH-006` | Login with empty password | Client-side required-field error |
| `T-AUTH-007` | Login with malformed email (`foo@`) | Client-side validation error |
| `T-AUTH-008` | 5 consecutive wrong passwords | Rate-limited / locked (per `docs/design/auth-lockout.md` when PR0–PR4b ship; today: rate limit only) |
| `T-AUTH-009` | Paste email with leading/trailing whitespace | Trimmed before submission (or reliably rejected) |
| `T-AUTH-010` | Submit login via **Enter** key | Same result as clicking Submit |
| `T-AUTH-011` | Submit login twice fast (double-click) | Single request in Network tab; no duplicate audit rows |

### 3.2 Logout

| ID | Test | Expected |
|---|---|---|
| `T-AUTH-020` | Click Logout | Access token cleared from memory; refresh cookie cleared (`Set-Cookie: ...; Max-Age=0`); audit row `action=logout, source_service=api` |
| `T-AUTH-021` | After logout, press browser Back button | Redirected to `/login`; no protected page flashes visibly |
| `T-AUTH-022` | Log out in Tab A, refresh Tab B (same session) | Tab B eventually redirects to `/login` on next API call (401 → dispatches `auth:logout`) |

### 3.3 Token lifecycle

| ID | Test | Expected |
|---|---|---|
| `T-AUTH-030` | Idle session ~15 min until access token expires (time out in DevTools by clearing in-memory token), then click any menu | `/api/...` returns 401 → frontend calls `/api/auth/refresh` → retries original with new token; no user-visible error |
| `T-AUTH-031` | Invalidate refresh cookie server-side (bump `token_version`), click any page | 401 on refresh → `auth:logout` event → redirect to `/login`; sensible flash message |
| `T-AUTH-032` | **Download during token refresh window** (regression for `b13fcb1`) | Clear in-memory token (DevTools snippet), then click **Export CSV** / **Export XLSX** / **Export Monthly Report** — each succeeds with a **single blob response** after an invisible refresh. No "Failed to download report". |
| `T-AUTH-033` | **Upload during token refresh window** (same regression) | Clear in-memory token, upload a PDF from `/upload`. Succeeds after silent refresh; audit row written. |
| `T-AUTH-034` | Two concurrent refresh-needing requests | Only **one** `/api/auth/refresh` in Network tab (dedup via `refreshPromise`) |
| `T-AUTH-035` | Refresh endpoint returns 401 (revoked) | Frontend dispatches `auth:logout`; all in-flight requests fail cleanly |

### 3.4 Forgot / reset password

| ID | Test | Expected |
|---|---|---|
| `T-AUTH-040` | Submit `/forgot-password` with registered email | 200 regardless of whether email exists (no user enumeration); Greenmail inbox receives reset email |
| `T-AUTH-041` | Submit `/forgot-password` with unknown email | Same 200 response, no email sent; response timing within noise of T-AUTH-040 |
| `T-AUTH-042` | Click reset link in email | Lands on `/reset-password?token=...` |
| `T-AUTH-043` | Submit reset with weak password | Strength validation error (per NIST V6.4.6 / password policy); form does not submit |
| `T-AUTH-044` | Submit reset with strong new password | Success; old refresh sessions **invalidated** (token_version bumps); login with new password works |
| `T-AUTH-045` | Reuse a reset token twice | Second attempt rejected |
| `T-AUTH-046` | Use expired reset token (> TTL) | Rejected with "Link expired" message |

### 3.5 NIST V6.4.6 — Admin cannot set user's password

| ID | Test | Expected |
|---|---|---|
| `T-AUTH-050` | Admin creates an employee → observe `/employees` "Add" flow | **No password field** exposed in the Admin UI; backend rejects password field on employee creation |
| `T-AUTH-051` | Admin clicks "Send setup email" for an employee | Employee receives setup-link email to Greenmail; link is one-time |
| `T-AUTH-052` | Tamper: send `POST /api/employees` with a `password` key as Admin | 400/422 or silently ignored; password not persisted |

---

## 4. Role-Based Access Control (RBAC) matrix

For every row in §1.2 run **two** tests per role: (a) the allowed role reaches the page, (b) every disallowed authenticated role is redirected to `/unauthorized`.

### 4.1 Admin-only boundary

| ID | Test | Expected |
|---|---|---|
| `T-RBAC-001` | Coordinator browses to `/audit` | Redirect to `/unauthorized` |
| `T-RBAC-002` | Coordinator hits `GET /api/audit-logs` via DevTools | 403 |
| `T-RBAC-003` | Coordinator browses to `/admin` | Redirect to `/unauthorized` |

### 4.2 Coordinator-only boundary

| ID | Test | Expected |
|---|---|---|
| `T-RBAC-010` | Admin browses to `/requirements` | Redirect to `/unauthorized` (per App.tsx, only Coordinator is allowed) |
| `T-RBAC-011` | Admin browses to `/upload` | Redirect to `/unauthorized` |
| `T-RBAC-012` | Admin browses to `/review` | Redirect to `/unauthorized` |
| `T-RBAC-013` | Admin browses to `/compliance` | Redirect to `/unauthorized` |
| `T-RBAC-014` | Admin browses to `/configuration` | Redirect to `/unauthorized` |
| `T-RBAC-015` | Admin browses to `/templates` | Redirect to `/unauthorized` |
| `T-RBAC-016` | Admin calls `POST /api/documents` | 403 |
| `T-RBAC-017` | Admin calls `POST /api/extractions/{id}/approve` | 403 |

### 4.3 Unauthenticated boundary

| ID | Test | Expected |
|---|---|---|
| `T-RBAC-020` | Unauthenticated GET `/api/employees` | 401 |
| `T-RBAC-021` | Unauthenticated GET `/api/audit-logs` | 401 |
| `T-RBAC-022` | Unauthenticated POST `/api/documents` | 401 |
| `T-RBAC-023` | Unauthenticated visit `/review/999` | Redirect to `/login` preserving return-to |

### 4.4 RBAC hardening

| ID | Test | Expected |
|---|---|---|
| `T-RBAC-030` | Tamper JWT: flip `role` claim from `Coordinator` to `Admin` in DevTools → retry | 401 (signature invalid) |
| `T-RBAC-031` | Two tabs open: demote an Admin to Coordinator from another browser, do one more action in old tab | Next write request 401s (token_version bumped) |
| `T-RBAC-032` | Remove `Authorization` header from a request in DevTools | 401 |

---

## 5. Employee management (`/employees`)

| ID | Test | Expected |
|---|---|---|
| `T-EMP-001` | List page renders | Table with name/email/department/role/status columns; pagination visible if > page size |
| `T-EMP-002` | Search by name | List filters live; empty state shows cleanly |
| `T-EMP-003` | Search by email substring | Filters correctly |
| `T-EMP-004` | Filter by Active/Inactive | Counts match DB: `SELECT status, COUNT(*) FROM certificates.employees GROUP BY status;` |
| `T-EMP-005` | Sort by name asc/desc | Stable, alphabetical order |
| `T-EMP-006` | Click employee → detail opens | URL and name match |
| `T-EMP-007` | Create new employee (Admin) | 201; row appears; audit `action=employee_created, source_service=api` |
| `T-EMP-008` | Create with duplicate email | Friendly error, no 500 |
| `T-EMP-009` | Create with invalid email format | Client-side validation stops submit |
| `T-EMP-010` | Create with XSS payload in name: `<img src=x onerror=alert(1)>` | Rendered as text everywhere; no alert; stored raw is fine as long as **output is escaped** |
| `T-EMP-011` | Edit employee — change department | PATCH 200; audit `action=employee_updated`; Before/After in details |
| `T-EMP-012` | Deactivate employee | Status = Inactive; no longer appears in upload/employee dropdowns |
| `T-EMP-013` | Reactivate employee | Reappears |
| `T-EMP-014` | Delete employee with outstanding requirements | Either blocked with friendly error, or cascades with explicit confirmation |
| `T-EMP-015` | Send setup email | Greenmail receives mail to the employee address; link opens `/reset-password` |
| `T-EMP-016` | Create many employees (≥ 50) | Pagination correct; no performance regression |

---

## 6. Requirements (`/requirements`)

| ID | Test | Expected |
|---|---|---|
| `T-REQ-001` | Page renders as Coordinator | List of assignments; filters for status / due-date range |
| `T-REQ-002` | Create new requirement assignment | 201; audit row |
| `T-REQ-003` | Assign same cert type to same employee twice | Friendly duplicate error |
| `T-REQ-004` | Bulk import CSV | 200; imports counted; failures reported row-by-row |
| `T-REQ-005` | Import CSV with bad header | Rejected with actionable error |
| `T-REQ-006` | Waive a requirement | Status → waived; audit `action=requirement_waived` with reason persisted |
| `T-REQ-007` | Unwaive | Reverts; audit row |
| `T-REQ-008` | Filter: Pending / Complete / Overdue | Counts match DB |
| `T-REQ-009` | Sort by due date | Earliest first / latest first both work |
| `T-REQ-010` | Paged endpoint `/requirements/paged` used correctly | DevTools Network shows `page=` / `size=` params |

---

## 7. Certificate Types & Templates

| ID | Test | Expected |
|---|---|---|
| `T-CT-001` | Configuration page lists cert types | At least seeded types present |
| `T-CT-002` | Create new cert type | 201; appears in dropdowns elsewhere |
| `T-CT-003` | Edit cert type | PATCH 200 |
| `T-CT-004` | Delete cert type still in use by a requirement | Blocked with clear error |
| `T-CT-005` | Create template via `/templates/new` | 201; template visible in list |
| `T-CT-006` | Template versioning — edit existing | New version row created; older version still retrievable |
| `T-CT-007` | Load template detail | Fields render; JSON schema correct |

---

## 8. Document upload (`/upload`)

Upload is a high-touch surface — many edge cases shipped fixes; pin them.

### 8.1 Happy path

| ID | Test | Expected |
|---|---|---|
| `T-UPL-001` | Drag-drop a valid PDF with `?employee_id=1` in URL | 201; toast "Uploaded"; document row with correct employee FK |
| `T-UPL-002` | Upload via file-picker button | Same result |
| `T-UPL-003` | Upload with multiple files queued | All succeed or failure per-file shown |

### 8.2 Employee ID guard — regression for `d6f747c`

URL query `employee_id` must reject empty-string, negative, zero, and non-numeric values.

| ID | Test | Expected |
|---|---|---|
| `T-UPL-010` | `/upload?employee_id=` (empty) | Page does **not** auto-fill employee; dropdown shown instead (as if param absent) |
| `T-UPL-011` | `/upload?employee_id=-5` | Treated as absent; dropdown shown |
| `T-UPL-012` | `/upload?employee_id=0` | Treated as absent |
| `T-UPL-013` | `/upload?employee_id=abc` | Treated as absent |
| `T-UPL-014` | `/upload?employee_id=1.5` | Treated as absent (non-integer) — or coerced to 1 by `Number.isFinite`; verify the `parsedEmployeeId > 0` branch holds |
| `T-UPL-015` | `/upload?employee_id=99999999` (non-existent id) | Upload rejected with "Unknown employee" error after user-visible submit |
| `T-UPL-016` | `/upload?employee_id=1&employee_id=2` (duplicate param) | URLSearchParams returns first; treated as 1 |

### 8.3 File validation

| ID | Test | Expected |
|---|---|---|
| `T-UPL-020` | Upload oversized file (> configured max) | Rejected with size error; no partial upload |
| `T-UPL-021` | Upload unsupported MIME (`.exe` renamed to `.pdf`) | Rejected server-side after magic-byte sniff |
| `T-UPL-022` | Upload empty file | Rejected with size=0 error |
| `T-UPL-023` | Upload corrupted PDF | Accepted into intake; OCR worker flags as failed with reason |
| `T-UPL-024` | Upload same file twice | Dedup by checksum OR two distinct rows with same hash (either is valid — pick the product decision and enforce) |
| `T-UPL-025` | Upload while offline | Network error surfaced; no half-saved state |

### 8.4 Upload + auth interaction

| ID | Test | Expected |
|---|---|---|
| `T-UPL-030` | Expired access token → click Submit | Single success response after silent refresh (regression for `b13fcb1`) |
| `T-UPL-031` | Revoked refresh token → click Submit | Fails cleanly; user redirected to login |
| `T-UPL-032` | Cancel upload mid-stream via DevTools | No orphan row in `documents`; no orphan object in MinIO |

---

## 9. Extraction pipeline (E2E)

After an upload, verify the downstream stages complete.

| ID | Test | Expected |
|---|---|---|
| `T-EXT-001` | Upload a clean known-template cert | OCR worker stage logs "OCR complete"; extraction worker runs LLM consensus; extraction row appears with confidence scores |
| `T-EXT-002` | Low-confidence field | Field highlighted in yellow on Review page; confidence value displayed |
| `T-EXT-003` | Multi-model consensus disagreement | Flagged; shows which models disagreed |
| `T-EXT-004` | Upload a non-cert PDF | Extraction completes but marked low-confidence or "not a certificate"; routed to review |
| `T-EXT-005` | Upload an image-only PDF | OCR runs; extraction still succeeds on text |
| `T-EXT-006` | Issuing authority verification | `verified_records` row created when issuer matches known list; verification badge shown on Review |
| `T-EXT-007` | Pipeline takes longer than UI expects | UI shows "processing" state; polling or SSE refresh updates when done (no infinite spinner) |

---

## 10. Review workflow (`/review`, `/review/:id`)

| ID | Test | Expected |
|---|---|---|
| `T-REV-001` | `/review` loads queue | Rows ordered by oldest-first or priority-first (per product); count matches `SELECT COUNT(*) FROM certificates.extractions WHERE status='pending_review'` |
| `T-REV-002` | Click item → `/review/:id` | Side-by-side document viewer + extracted fields |
| `T-REV-003` | Document viewer loads via view-token | Short-lived token URL; 200 response; `Content-Type: application/pdf` |
| `T-REV-004` | Edit an extracted field | Value updates locally; unsaved-changes banner appears |
| `T-REV-005` | Approve extraction | 200; `verified_records` row inserted; extraction status → approved; audit `action=extraction_approved, source_service=api` |
| `T-REV-006` | Approve twice (double-click) | Single write (button disables during request) |
| `T-REV-007` | Reject with reason | 204; reason persisted; audit `action=extraction_rejected` |
| `T-REV-008` | Reject without reason | Either allowed (if reason optional) or client-side error |
| `T-REV-009` | Browse to `/review/<nonexistent>` | 404 page, not a crash |
| `T-REV-010` | Concurrent Coordinators on same item | Second submitter sees 409/"already reviewed" or friendly error |

---

## 11. Compliance dashboard (`/compliance`)

| ID | Test | Expected |
|---|---|---|
| `T-DASH-001` | Dashboard renders as Coordinator | KPI cards: Pending Review, Overdue, Upcoming Expirations |
| `T-DASH-002` | Pending-review count (regression for `dd2bade`) | Count matches DB `SELECT COUNT(*) FROM certificates.extractions WHERE status='pending_review';`. Must **not** silently cap at 10000 even when > 10k pending. Seed 10_100 pending rows and verify the displayed number is the true count |
| `T-DASH-003` | Overdue count | Matches DB |
| `T-DASH-004` | Expiring in 30/60/90 days | Matches DB |
| `T-DASH-005` | Click KPI card | Drills down to filtered list |
| `T-DASH-006` | Dashboard loads < 2s on a warm DB with 1k employees | Perf acceptable |

---

## 12. Reports & exports

`/reports` redirects to `/compliance`. Exports are triggered from there.

### 12.1 CSV / XLSX completeness — regression for `6f94704`

| ID | Test | Expected |
|---|---|---|
| `T-RPT-001` | Export Requirements CSV with 500 rows | File contains exactly 500 data rows (+1 header) |
| `T-RPT-002` | Export Requirements CSV with **10_500 rows** | File contains exactly 10_500 data rows — **no silent 10k truncation**. This is the core regression check for the `_UNBOUNDED_QUERY_CAP` bypass. |
| `T-RPT-003` | Export Requirements XLSX with 10_500 rows | Same row count; file opens in Excel/LibreOffice without warnings |
| `T-RPT-004` | Export Monthly Report XLSX | All month's data present; formulas/totals correct |

### 12.2 CSV formula injection defang — MED-07

| ID | Test | Expected |
|---|---|---|
| `T-RPT-010` | Create employee with name `=cmd\|' /C calc'!A0`, assign a requirement, export CSV | Exported cell begins with a tick / apostrophe or is quoted so spreadsheet does **not** evaluate the formula |
| `T-RPT-011` | Employee name starts with `+` | Defanged |
| `T-RPT-012` | Employee name starts with `-` | Defanged |
| `T-RPT-013` | Employee name starts with `@` | Defanged |
| `T-RPT-014` | Employee name starts with `\t` (tab) | Defanged |
| `T-RPT-015` | Employee name starts with `\r` (carriage return) | Defanged |
| `T-RPT-016` | Employee name includes embedded `=SUM(A1:A10)` mid-string | Safe — only the *first character* is the exploit surface, but verify multi-line fields are quoted |

### 12.3 Export auth

| ID | Test | Expected |
|---|---|---|
| `T-RPT-020` | Unauthenticated direct hit to `/api/reports/requirements?format=csv` | 401 |
| `T-RPT-021` | Admin hits the report endpoint | 403 if Coordinator-only, or 200 if Admin is allowed (confirm against `docs/design/` role spec) |
| `T-RPT-022` | Coordinator clicks Export during token refresh | Single 200 (regression for `b13fcb1`) |

### 12.4 Filters apply to export

| ID | Test | Expected |
|---|---|---|
| `T-RPT-030` | Apply filter on screen (e.g., "Overdue only"), click Export | Exported file respects the filter |
| `T-RPT-031` | No filter | All rows (subject to RBAC) |

---

## 13. Notifications (`/notifications`)

| ID | Test | Expected |
|---|---|---|
| `T-NOT-001` | Page renders | Notifications list; unread badge count in header matches `/api/notifications/unread-count` |
| `T-NOT-002` | Mark one as read | Count decrements; DB `notifications.notifications.read_at` set |
| `T-NOT-003` | Mark all as read | Count → 0; no rows remain unread |
| `T-NOT-004` | Real-time update (if WebSocket/SSE used) | New notification arrives within a few seconds of server emit |
| `T-NOT-005` | Pagination for > 100 notifications | Works; counts stable |
| `T-NOT-006` | Click notification with deep link | Navigates to the referenced entity (e.g., review item) |
| `T-NOT-007` | Expiration warning notification appears at 30/7/0-day thresholds | Scheduler creates the row; UI picks it up |

---

## 14. Audit log (`/audit`, Admin only)

### 14.1 UI correctness

| ID | Test | Expected |
|---|---|---|
| `T-AUD-001` | Page renders | Filter bar (date range, service, action, user), paginated table |
| `T-AUD-002` | Sort by `occurred_at_utc` desc | Newest first |
| `T-AUD-003` | Click row → detail panel | Shows `details` JSON (scrubbed), actor, target, correlation_id |
| `T-AUD-004` | Pagination → page 2 | Stable, no duplicates |

### 14.2 source_service coverage — regression for `f7a387e`

Every recent action must have `source_service` populated. Check the DB after performing each action:

```bash
docker exec -e PGPASSWORD=laredo_dev_password laredo-postgres \
  psql -U laredo -d laredo_certificates -c "
SELECT source_service, action, COUNT(*)
FROM audit.audit_logs
WHERE recorded_at_utc > NOW() - interval '15 minutes'
GROUP BY source_service, action ORDER BY source_service NULLS LAST, action;"
```

| ID | Trigger | Expected `source_service` |
|---|---|---|
| `T-AUD-010` | Coordinator edits an employee | `api` |
| `T-AUD-011` | Coordinator approves an extraction | `api` |
| `T-AUD-012` | Coordinator waives a requirement | `api` |
| `T-AUD-013` | Admin creates an employee | `api` |
| `T-AUD-014` | Login / logout | `api` |
| `T-AUD-015` | Email intake processes an attachment | `email-intake-worker` |
| `T-AUD-016` | Scheduler emits a reminder | `scheduler-worker` |
| `T-AUD-017` | Filter `/audit` by Service → `api` | Only api rows visible |
| `T-AUD-018` | Filter by Service → `email-intake-worker` | Only that service |
| `T-AUD-019` | Filter by Service → `scheduler-worker` | Only that service |

A NULL `source_service` on any **new** row is a regression.

### 14.3 Secret scrubbing

Audit `details` must never contain sensitive keys (`password`, `password_hash`, `token`, `secret`, `api_key`, `cookie`, `authorization`).

| ID | Test | Expected |
|---|---|---|
| `T-AUD-030` | Trigger an action that logs a dict containing `password` | Resulting audit row's `details` does **not** include `password` |
| `T-AUD-031` | Same for each secret key in the scrub list | Each key redacted |

### 14.4 Append-only guarantee

| ID | Test | Expected |
|---|---|---|
| `T-AUD-040` | Attempt `UPDATE audit.audit_logs SET action='x' WHERE id=1;` via psql | Blocked by DB-level trigger/rule or user permission |
| `T-AUD-041` | Attempt `DELETE FROM audit.audit_logs WHERE id=1;` | Blocked |

---

## 15. Email intake (Greenmail)

Requires Greenmail at `localhost:3025` (SMTP) + `localhost:8080` (HTTP API).

| ID | Test | Expected |
|---|---|---|
| `T-EM-001` | Send plain email with PDF attachment from known employee address | Worker ingests; document row created; audit `action=email_intake_processed, source_service=email-intake-worker` |
| `T-EM-002` | Send with multiple attachments | Each processed as its own document |
| `T-EM-003` | Send from unknown sender | Rejected (audit `action=email_intake_rejected` with reason); no document created |
| `T-EM-004` | Send email with no attachments | Audit row `action=email_intake_no_attachment` (or equivalent); no documents |
| `T-EM-005` | Send HTML-only email | Body parsed; no crash |
| `T-EM-006` | Send email with malformed MIME | Gracefully skipped; error logged |
| `T-EM-007` | Send 10 MB+ attachment | Either processed or rejected with size error — not a crash |
| `T-EM-008` | Send encrypted / password-protected PDF | Routed to review with clear flag |
| `T-EM-009` | Duplicate message-id replay | Idempotent — no duplicate rows |
| `T-EM-010` | Intake worker restarts mid-batch | On restart, resumes without double-processing (check audit count exactly matches emails sent) |

---

## 16. Scheduler / notification worker

| ID | Test | Expected |
|---|---|---|
| `T-SCH-001` | Set a requirement's due_date to today − 1 and wait for next scheduler tick | Overdue notification created; audit row `source_service=scheduler-worker` |
| `T-SCH-002` | Scheduler starts after being down for an interval | Missed runs caught up (not skipped silently); audit log shows catch-up |
| `T-SCH-003` | Alert config `/configuration` — change reminder intervals to 30/7/1 days | Next scheduler run respects the new thresholds |

---

## 17. Security tests

### 17.1 Transport & headers

| ID | Test | Expected |
|---|---|---|
| `T-SEC-001` | `http://localhost/` | Redirects to `https://localhost/` OR rejected (per recent HTTPS-only hardening, commits `3a81780`, `452229b`, `11575b3`) |
| `T-SEC-002` | `curl -I https://localhost/` | Headers include `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Content-Security-Policy` |
| `T-SEC-003` | Refresh cookie flags | `HttpOnly`, `Secure`, `SameSite=Lax` or `Strict` |
| `T-SEC-004` | Access token in `localStorage` / `sessionStorage` | **Not present** — must be in-memory only |

### 17.2 Injection

| ID | Test | Expected |
|---|---|---|
| `T-SEC-010` | XSS: name = `<script>alert(1)</script>` — view on every page that renders the name | No alert ever fires; rendered as literal text |
| `T-SEC-011` | XSS: name = `<img src=x onerror=alert(1)>` | Same — safe |
| `T-SEC-012` | XSS: paste `javascript:alert(1)` into a URL input field, click link | Sanitized / non-navigable |
| `T-SEC-013` | SQL injection: search for `' OR 1=1 --` | Treated as literal string; no extra rows leaked |
| `T-SEC-014` | SQL injection in numeric `?id=` | 400/422, never a 500 with SQL error |
| `T-SEC-015` | CSV formula injection — see §12.2 |
| `T-SEC-016` | Path traversal in filename: `../../../etc/passwd` | Rejected server-side |
| `T-SEC-017` | SSRF: upload a file whose OCR text contains `http://169.254.169.254/latest/meta-data/` | System does not fetch that URL; extracted as text only |

### 17.3 CSRF / CORS

| ID | Test | Expected |
|---|---|---|
| `T-SEC-020` | Cross-origin `fetch('https://localhost/api/employees')` from `https://evil.test` | Blocked by CORS (no `Access-Control-Allow-Origin` for that origin) |
| `T-SEC-021` | POST form from cross-origin page → `/api/auth/login` | Rejected (CSRF / CORS) |

### 17.4 Rate limiting

| ID | Test | Expected |
|---|---|---|
| `T-SEC-030` | Fire 50 login attempts in 10s from the same IP | 429 after configured threshold; `Retry-After` header present |
| `T-SEC-031` | Fire 200 `/api/documents` POSTs | Rate limited |
| `T-SEC-032` | Normal interactive browsing | Not rate limited |

### 17.5 Session fixation & hijack

| ID | Test | Expected |
|---|---|---|
| `T-SEC-040` | Copy refresh cookie from Browser A to Browser B (different IP/UA) | Either rejected (bound) or flagged — verify product policy |
| `T-SEC-041` | Reduce system clock to pre-token-iat | Token still validates (tolerance window) or rejected (strict) — verify |

---

## 18. UI / form tests

### 18.1 Layout & visual form

| ID | Test | Expected |
|---|---|---|
| `T-UI-001` | 320×568 (iPhone SE) viewport: every protected page | No horizontal scroll; nav collapses; primary actions reachable |
| `T-UI-002` | 768×1024 tablet | Layout uses tablet breakpoint cleanly |
| `T-UI-003` | 1440×900 laptop | Primary layout; no wasted space > 200px gutters |
| `T-UI-004` | 3840×2160 4K | No stretched images; max-widths respected |
| `T-UI-005` | Light theme | All text meets WCAG AA contrast |
| `T-UI-006` | Dark theme (if supported) | Same |
| `T-UI-007` | Print preview of `/compliance` | Page breaks correctly; no nav chrome |
| `T-UI-008` | Zoom 200% in browser | No overflow truncation; no overlap |

### 18.2 Forms

| ID | Test | Expected |
|---|---|---|
| `T-UI-020` | Required-field error styling | Red border, error text visible, associated via `aria-describedby` |
| `T-UI-021` | Tab order on every form | Logical: top-to-bottom, left-to-right |
| `T-UI-022` | Submit button disabled while request in flight | Prevents double submit |
| `T-UI-023` | Autofill (browser password manager) | Works on login / reset |
| `T-UI-024` | Paste into password field | Allowed (per NIST 2020+ — do not block paste) |
| `T-UI-025` | Browser "Save password" prompt appears on login | Does not capture other secret inputs |
| `T-UI-026` | Long text overflow (name > 200 chars) | Truncates with ellipsis in tables; full value in tooltip |
| `T-UI-027` | Unicode / emoji in name (`🔥 José São Paulo`) | Renders correctly, persists round-trip |
| `T-UI-028` | RTL text (`مرحبا`) | Renders correctly; bidi text not broken |
| `T-UI-029` | Empty-state UI (no extractions / no notifications) | Friendly empty illustration, not a blank page |
| `T-UI-030` | Loading state (skeleton / spinner) | Visible on slow network (throttled to "Slow 3G") |
| `T-UI-031` | Error state (API 500) | Toast or banner with retry affordance |

### 18.3 Navigation

| ID | Test | Expected |
|---|---|---|
| `T-UI-040` | Browser Back from `/review/:id` → returns to `/review` list with filters preserved | True |
| `T-UI-041` | Deep link to `/review/42` (signed-out) | Login → post-login redirect to `/review/42` |
| `T-UI-042` | Refresh on `/compliance` | Stays on page; no redirect to `/` |
| `T-UI-043` | Catch-all `/bogus/path` (signed in) | Redirects to `/` |
| `T-UI-044` | 404 page for a valid URL with invalid id (`/review/99999`) | Dedicated Not Found state, not a crash |

---

## 19. Accessibility (WCAG 2.1 AA)

Run axe DevTools + Lighthouse a11y on **every** page in §1.2. Zero "critical" violations required.

| ID | Test | Expected |
|---|---|---|
| `T-A11Y-001` | Keyboard-only: log in, upload, review, approve | Every action reachable via Tab/Enter/Space; focus visible at all times |
| `T-A11Y-002` | Screen reader (NVDA on Windows / VoiceOver on macOS) — walk the Dashboard | All KPI cards announce label + value |
| `T-A11Y-003` | Color-contrast: body text ≥ 4.5:1, large text ≥ 3:1 | Pass |
| `T-A11Y-004` | Images have `alt` text (or explicit `alt=""` for decorative) | True |
| `T-A11Y-005` | Form inputs have `<label>` or `aria-label` | True |
| `T-A11Y-006` | Headings form a single `h1` per page, then h2, h3 with no skipped levels | True |
| `T-A11Y-007` | Live regions for toast notifications use `role="status"` / `aria-live="polite"` | True |
| `T-A11Y-008` | Prefers-reduced-motion: animations respect OS setting | True |
| `T-A11Y-009` | Focus trap in modals (e.g., Confirm Delete dialog) | Tab cycles within modal; Escape closes |
| `T-A11Y-010` | Skip-to-content link | First Tab exposes "Skip to main content" |
| `T-A11Y-011` | Language declared in `<html lang="en">` | True |

---

## 20. Performance

Lighthouse Performance ≥ 85 on each key page; Core Web Vitals acceptable.

| ID | Test | Expected |
|---|---|---|
| `T-PERF-001` | Time to Interactive on `/login` | < 3s on broadband, < 6s on Slow 3G |
| `T-PERF-002` | `/compliance` with 1k employees | LCP < 2.5s |
| `T-PERF-003` | `/audit` with 50k rows (use DB seed) | Virtualized list; scroll stays at 60fps |
| `T-PERF-004` | `/review` queue with 500 items | Paginated or virtualized; no full-list render |
| `T-PERF-005` | JS bundle size | Main chunk < 500 KB gzipped (track trend, not absolute) |
| `T-PERF-006` | No memory leak on 10 min idle on `/compliance` | Chrome Task Manager shows stable heap |

---

## 21. Browser compatibility matrix

Minimum: latest of Chrome, Firefox, Safari, Edge. Run **SMOKE** on every row; run full matrix on at least Chrome per build.

| Browser | Version | SMOKE | Full |
|---|---|---|---|
| Chrome (desktop) | latest | required | required |
| Chrome (Android) | latest | required | optional |
| Firefox | latest | required | recommended |
| Safari (macOS) | latest | required | recommended |
| Safari (iOS) | latest | required | optional |
| Edge | latest | required | optional |
| Chrome (N-1) | one back | optional | optional |

Known area to double-check per browser: **cookie `SameSite` handling** (Safari's ITP has historically been strictest) and **File API** on mobile (iOS Safari upload path).

---

## 22. Error recovery

| ID | Test | Expected |
|---|---|---|
| `T-ERR-001` | Kill API container mid-navigation | UI shows generic "Service temporarily unavailable"; refresh re-engages after API returns |
| `T-ERR-002` | Postgres down | API returns 503; UI surfaces retry |
| `T-ERR-003` | MinIO down during upload | Upload fails clearly; not a crash |
| `T-ERR-004` | Redis down (sessions/rate limit) | UI degrades gracefully (per fallback policy) |
| `T-ERR-005` | Greenmail unreachable during forgot-password | Still returns 200 to the user (no enumeration); retry queue picks up |
| `T-ERR-006` | Offline (turn off network in DevTools) | UI shows offline banner; queued requests fail explicitly |

---

## 23. Edge cases

| ID | Test | Expected |
|---|---|---|
| `T-EDG-001` | Two tabs, both edit same employee | Second save either 409 or last-write-wins per policy (document which) |
| `T-EDG-002` | Logout in Tab A while Tab B has unsaved form | Tab B save fails with 401; draft not lost locally |
| `T-EDG-003` | System clock jumps forward 1h during a session | Next token refresh still works |
| `T-EDG-004` | Timezones: Coordinator in `America/Chicago`, employee due_date stored UTC | Due date displays in local TZ consistently; DB value unchanged |
| `T-EDG-005` | DST transition day — schedule a notification at 02:30 on spring-forward day | Fires at the expected absolute time (no double-fire / no skip) |
| `T-EDG-006` | Very long employee name (500 chars) | Either rejected or truncated per schema; renders without breaking layout |
| `T-EDG-007` | Null / NaN in extraction confidence | Displayed as "—" not as "NaN" |
| `T-EDG-008` | Browser Back after approve | Goes back to queue; approved item no longer present |
| `T-EDG-009` | Copy-paste a signed document URL to another user | Unauthorized viewer hits 401 on the view-token endpoint |

---

## 24. Regression pinboard (recent shipped fixes)

The fast-reference list of "tests that directly pin a fix". If any of these fail, a recent fix regressed.

| Commit | Fix | Primary test IDs |
|---|---|---|
| `d6f747c` | Upload `employee_id` guard (empty, negative, zero, non-numeric) | `T-UPL-010` through `T-UPL-016` |
| `6f94704` | Reports & dashboard not silently capped at 10k | `T-RPT-002`, `T-RPT-003`, `T-DASH-002` |
| `4411b36` | Test infra unblock (container collection clean) | Run `docker exec laredo-api pytest tests/ -q --ignore=tests/ocr` → expect `704 passed` |
| `dd2bade` | `list_all_extractions` uncap for dashboard | `T-DASH-002` |
| `b13fcb1` | `fetchWithAuthRetry` — downloads / uploads survive token refresh | `T-AUTH-032`, `T-AUTH-033`, `T-RPT-022`, `T-UPL-030` |
| `f7a387e` | Audit `source_service` populated for every emitter | `T-AUD-010` through `T-AUD-019` |
| `3a81780`, `452229b`, `11575b3` | HTTPS-only hardening | `T-SEC-001`, `T-SEC-002` |

---

## 25. Exit criteria

A release is test-green when all of the following hold:

- [ ] SMOKE (§2) is 100% PASS on Chrome latest
- [ ] Every Regression Pinboard (§24) test is PASS
- [ ] RBAC matrix (§4) is 100% PASS — no role escalation, no silent failures
- [ ] Security (§17) has no High or Critical findings open
- [ ] Accessibility (§19) has zero axe-critical violations on public + Coordinator pages
- [ ] Performance (§20) Lighthouse scores ≥ 85 on `/login`, `/`, `/compliance`
- [ ] Audit `source_service` coverage query (in §14.2) shows zero NULL rows for activity in the test window
- [ ] Test results (this file with PASS/FAIL/evidence) committed to the release artifact

---

## 26. Appendix

### 26.1 Test data reset procedure

```bash
# Wipe ephemeral state (does NOT drop the DB)
docker exec laredo-api python -m scripts.reset_test_data   # if available
# or: recreate compose with a clean volume
docker compose down -v && docker compose up -d
docker exec laredo-api alembic upgrade head
docker exec laredo-api python -m scripts.seed_minimal      # if available
```

### 26.2 Useful DB probes during tests

```bash
# Audit coverage for the last 15 min
docker exec -e PGPASSWORD=laredo_dev_password laredo-postgres \
  psql -U laredo -d laredo_certificates -c "
SELECT source_service, action, COUNT(*)
FROM audit.audit_logs
WHERE recorded_at_utc > NOW() - interval '15 minutes'
GROUP BY source_service, action ORDER BY source_service NULLS LAST, action;"

# Pending review count (pin against dashboard)
docker exec -e PGPASSWORD=laredo_dev_password laredo-postgres \
  psql -U laredo -d laredo_certificates -c "
SELECT COUNT(*) FROM certificates.extractions WHERE status='pending_review';"

# Employees by role & status
docker exec -e PGPASSWORD=laredo_dev_password laredo-postgres \
  psql -U laredo -d laredo_certificates -c "
SELECT role, status, COUNT(*) FROM certificates.employees GROUP BY role, status;"
```

### 26.3 Greenmail quick reference

```bash
# List inboxes
curl -s http://localhost:8080/api/user | jq .

# Fetch latest message for rachel@test.local
curl -s "http://localhost:8080/api/message/rachel@test.local" | jq .

# Purge all
curl -X POST http://localhost:8080/api/service/reset
```

### 26.4 Evidence capture checklist per FAIL

- Screenshot (viewport + full page)
- DevTools Network → "Save all as HAR"
- DevTools Console log
- Correlating audit_log rows (query by `correlation_id` if shown in headers)
- Steps to reproduce: exact URL, role, input values
- Browser + version, OS, viewport size

### 26.5 Test-ID prefix legend

| Prefix | Area |
|---|---|
| `T-SMK` | Smoke |
| `T-AUTH` | Authentication |
| `T-RBAC` | Role-based access control |
| `T-EMP` | Employees |
| `T-REQ` | Requirements |
| `T-CT` | Certificate types / templates |
| `T-UPL` | Upload |
| `T-EXT` | Extraction pipeline |
| `T-REV` | Review workflow |
| `T-DASH` | Compliance dashboard |
| `T-RPT` | Reports / exports |
| `T-NOT` | Notifications |
| `T-AUD` | Audit log |
| `T-EM` | Email intake |
| `T-SCH` | Scheduler |
| `T-SEC` | Security |
| `T-UI` | UI / form |
| `T-A11Y` | Accessibility |
| `T-PERF` | Performance |
| `T-ERR` | Error recovery |
| `T-EDG` | Edge cases |

---

_Last updated: 2026-04-20. Owner: Engineering. Extend this document whenever a new feature or bug fix lands — add the pin test(s) to §24 at the same time._
