# Demo Screenshots — City of Laredo Certificate Management System

Captured on 2026-04-26 against the live local stack (`make up` profile + `dev-tools`, `security`, `email-intake`).

Demo email sent at 15:26:08 from `ahmed.abdallah@ci.laredo.tx.us` to `certs@ci.laredo.tx.us` with `Smith_J_CPR_2026.pdf` attached. Document id 13897, extraction id 24402.

All UI screenshots are 1440x900 viewport, captured via headless Chrome through Playwright.

---

## Act 1 — Employee submits

| # | File | What it shows |
| - | ---- | ------------- |
| 1.1 | `backstage_worker_logs.txt` | IMAP poll picks up email, ClamAV scan, MinIO storage at `email-intake/20260426/...pdf`, extraction task queued for document 13897. Includes the consensus extraction trail (3 LLM passes via Ollama + Judge resolution) and the auto-reject decision with full reasoning. |
| 1.2 | `00_roundcube_landing.png` | Roundcube webmail login screen at `http://127.0.0.1:9090`. Used for sending the test email as an employee. |
| 1.3 | `00b_roundcube_certs_inbox_after_intake.png` | `certs@ci.laredo.tx.us` inbox is empty after intake — proves the worker moved the message to the Processed folder per the IMAP move-after-intake design. |
| 1.4 | `00_greenmail_landing.png` | Greenmail OpenAPI explorer at `http://127.0.0.1:8080`. Reference for the local mail-stack admin surface. |

**Narration beat:** "Employee emails the certificate. Within 60 seconds the intake worker IMAP-polls, validates the sender against the GAL, runs ClamAV (fail-closed), persists to MinIO, and queues an extraction job."

---

## Act 2 — Pipeline does its job

| # | File | What it shows |
| - | ---- | ------------- |
| 2.1 | `01_login_page.png` | Branded login screen with City of Laredo + Public Health logos. "Secure access for authorized City of Laredo employees only." |
| 2.2 | `02_coordinator_dashboard.png` | Coordinator landing: Pending Reviews / Overdue / Expiring Soon KPI cards, welcome banner with employee number, Quick Actions, Navigation tiles. |
| 2.3 | `03_review_queue.png` | Review queue, default `Pending` filter — 0 pending right after intake (item already auto-rejected by the time the screenshot ran). |
| 2.4 | `03b_review_queue_with_status_filter.png` | **Flagship**: Review queue with filter chips showing live counts (0 Pending, 4550 Approved, 54 Rejected, All). Brand-new card `#24402` shown as "Today" alongside historical extractions. |
| 2.5 | `03c_review_queue_default.png` | Same queue, default filter, second view. |
| 2.6 | `03d_review_queue_all_clicked.png` | After explicitly clicking the All chip. |

**Narration beat:** "Coordinator opens the review queue. The system surfaces every extraction with its template match, age, and status badge."

---

## Act 3 — Coordinator reviews

| # | File | What it shows |
| - | ---- | ------------- |
| 3.1 | `03e_review_detail_extraction_24402.png` | **Flagship**: Side-by-side viewer. Left: rendered certificate PDF. Right: Extracted Fields panel (Issue Date, Certificate Type, Issuing Authority, Certificate Holder Name) plus "Rejected" status badge. |
| 3.2 | `03f_review_detail_bottom.png` | Same view scrolled — shows the full document in the viewer pane. |
| 3.3 | `03g_review_detail_approved_24400.png` | Same UI rendering an Approved extraction (`#24400`) for contrast — same layout, "Approved" badge. |

**Narration beat:** "The system extracts every field with confidence scores. This one was auto-rejected because the certificate's holder name 'User Name' does not match the employee record 'Ahmed Abdallah' — the name-mismatch defense in action. An Approved record looks identical except for the badge."

---

## Act 4 — Compliance and alerting

| # | File | What it shows |
| - | ---- | ------------- |
| 4.1 | `04_compliance_dashboard.png` | **Flagship**: 82% Overall Compliance, 2153 Total Employees, 12226 Total Requirements. Status Breakdown: 10056 Compliant / 414 Due Soon / 1756 Overdue / 0 Waived. Full By-Certificate-Type table with per-row compliance rates. |
| 4.2 | `04b_reports_redirect_to_compliance.png` | `/reports` URL resolves to the Compliance page — the back-compat redirect documented in OPEN_ISSUES.md is working. |
| 4.3 | `05_requirements_page.png` | Requirements list view. |
| 4.4 | `06_configuration_alert_rules.png` | Configuration page on the Certificate Types tab — admin-managed catalog with Edit / Delete and "+ Add Certificate Type". |
| 4.5 | `06b_configuration_alert_rules_tab.png` | **Flagship**: Configuration page on Alert Rules tab. Reminder Offsets chips (90d down to 1d, each removable), Daily Overdue Reminders toggle, Daily Send Time (06:00 AM Server local time CT), Save / Reset. |
| 4.6 | `07_templates_list.png` | Extraction templates list. |
| 4.7 | `08_upload_page.png` | Manual upload UI (alternative ingestion path to email intake). |
| 4.8 | `09_notifications_coord.png` | Notifications screen as Coordinator. |
| 4.9 | `10_employees_coord.png` | Employees list as Coordinator (2153 employees, paginated). |

**Narration beat:** "Compliance is calculated live across 12k+ requirements. Alert rules are coordinator-managed: any reminder cadence is just a chip, and the daily reminder cycle runs at a configurable time."

---

## Act 5 — Admin governance

| # | File | What it shows |
| - | ---- | ------------- |
| 5.1 | `11_coordinator_blocked_from_admin.png` | **Flagship**: Coordinator hits `/admin`, gets "Access Denied — You do not have permission to view this page." Live RBAC route guard. |
| 5.2 | `12_admin_dashboard.png` | Admin dashboard. |
| 5.3 | `13_admin_audit_log.png` | **Flagship**: Append-only governance audit log. Long page of timestamped entries with actor, action, target. |
| 5.4 | `14_admin_admin_home.png` | `/admin` route as Admin: redirects to `/` (App.tsx renders `<Navigate to="/" replace />`). Byte-identical to 5.2 — that is the intended behavior. |
| 5.5 | `15_admin_notifications.png` | Admin's notifications view. |
| 5.6 | `16_admin_employees.png` | Admin's employees view. |

**Narration beat:** "Admin-only governance. Coordinators get denied at the route. Audit log is append-only — every meaningful action shows up here, including this one once we look at it."

---

## Act 6 — Behind the scenes

These are text artifacts, not images — all small, drop them straight into a slide if you want.

| # | File | What it shows |
| - | ---- | ------------- |
| 6.1 | `backstage_docker_ps.txt` | All 14 services from the local stack with health status. Frontend, API, Caddy, MinIO, Postgres, Redis all show `(healthy)`. Proves the stack is real. |
| 6.2 | `backstage_redis_dlq.txt` | DLQ snapshot via `docker exec laredo-redis redis-cli --tls --cert /tls/client.crt ...`. Both `extraction_tasks:dead_letter` and `ocr_tasks:dead_letter` are empty (LLEN = 0), and live queues drained to 0. Demonstrates the mTLS-on-internal-port-6380 design. |
| 6.3 | `backstage_verification_head.txt` | Top of the most recent `verification/results/project-verification-*.md`. Five gates PASS (Frontend Build, API Pytest, Auth/Mail, HTTPS, Worker Queues), Browser Audit FAIL is intentional limited scope per `e2e/browser-audit-scope.mjs`. |
| 6.4 | `backstage_worker_logs.txt` | Full worker log trail for doc 13897 — IMAP poll, MinIO store, extraction queued, OCR (37 spans), Ollama consensus (3 runs, all valid JSON), Judge resolution, name-mismatch auto-reject. |

**Narration beat:** "Pick two of these four during the demo, otherwise pacing collapses. The DLQ check is the strongest single beat — it proves the failure-recovery design exists even though no replay tool reads from it yet."

---

## Findings during the live capture

**Real bug discovered:** the extraction worker logged
```
{"document_id": 13897, "error": "No module named 'aiosmtplib'",
 "event": "Failed to send name mismatch rejection email", "level": "error"}
```
during the auto-reject path. The name-mismatch decision is correct and persists, but the courtesy notification email back to the employee fails silently. This is in `BackgroundProcessingInstances/ExtractionWorker/` — `aiosmtplib` is missing from `requirements.txt`. Worth fixing before any demo where you actually want the rejection email to land.

**Routes confirmed identical:** `/admin` and `/` render the same content for Admins because App.tsx wires `/admin` to `<Navigate to="/" replace />`. The route still serves a purpose (RBAC denial for non-admins, evidence in `11_coordinator_blocked_from_admin.png`), but there is no separate AdminPage component.

**Demo email sender constraint:** the email intake worker rejects senders that are not in the GAL, even if the domain matches. First two test emails were dropped (`Ignoring email from ... not in GAL or non-city`); the third, sent from a real seeded employee, was accepted. If you demo this live, send from a known seeded employee like `ahmed.abdallah@ci.laredo.tx.us`.

---

## How to re-run

Three Playwright scripts live in `e2e/`:

- `e2e/demo-run.mjs` — main 16-shot walkthrough across coordinator + admin sessions
- `e2e/demo-review-detail.mjs` — review queue + extraction detail captures
- `e2e/demo-approved.mjs` — approved-extraction + reports redirect + alert rules tab
- `e2e/demo-greenmail.mjs` — Greenmail and Roundcube landing
- `e2e/demo-roundcube.mjs` — Roundcube login as `certs@`

Run from the `e2e/` directory: `node demo-run.mjs` (and the others in any order). They all use `channel: 'chrome'` with `--ignore-certificate-errors` to bypass the dev TLS warnings.

The backstage text files are produced by inline `bash` snippets, not a script — see the corresponding bash invocations in the original conversation history if you want to refresh them.
