# Project Verification

This project is no longer verified by the browser audit alone.

The browser catalog in `browser_test_README.md` describes broad product
expectations, but a large subset of those expectations are not genuinely
browser-executable. They require inbox access, DB time control, worker/runtime
evidence, security/header probes, or backend-only assertions. Keeping those
inside the browser audit produced noisy `BLOCKED` results without increasing
confidence.

The verification strategy is now layered.

## Primary Entry Point

Run the whole verification stack from the repo root:

```bash
make verify-project
```

That target runs:

1. `npm --prefix CoreInstances/FrontendWebServer run build`
2. `docker compose exec -T api pytest -q`
3. Live auth/mail checks when explicitly enabled with
   `RUNTIME_AUTH_ALLOW_MUTATION=1` against an isolated development database;
   otherwise this step is recorded as `SKIP`
4. `make validate-https`
5. `make test-worker-queues-docker`
6. `npm --prefix e2e run audit`

The summary is written to `verification/results/project-verification-*.md`.
An unrun mutating check is never reported as passing.

## Browser Audit Scope

The automated browser audit is restricted to the supported set in
`e2e/browser-audit-scope.mjs`.

It should only claim IDs that can be executed inside a real browser session
without relying on:

- direct DB mutation
- inbox/message retrieval outside the page under test
- worker internals
- proxy/header probing outside the browser surface
- external assistive technology
- OS-level password-manager or print-preview behavior

Artifacts:

- `e2e/results/browser-audit-strict-*.md`
- `e2e/results/browser-audit-strict-*.json`

## Replaced Non-Browser Coverage

The following families were intentionally removed from the browser-only audit
and replaced with stronger checks in the project-wide verification run.

| Replaced family | Replacement verification | Primary evidence |
| --- | --- | --- |
| `T-AUTH-040..046`, `T-AUTH-051`, `T-AUTH-052` | `bash scripts/run_runtime_auth_checks.sh` | live forgot/reset mail flow, token reuse rejection, expired token rejection, setup email delivery, login with rotated password |
| `T-AUTH-008`, `T-AUTH-030..035` | `docker compose exec -T api pytest -q` | `tests/unit/test_auth_rate_limits.py`, `tests/unit/test_auth_service.py` |
| `T-RBAC-002`, `T-RBAC-016..017`, `T-RBAC-020..023`, `T-RBAC-030..032` | `docker compose exec -T api pytest -q` plus runtime auth checks | `tests/unit/test_admin_boundary.py`, `tests/unit/test_authorizer.py`, live `/api/api/*` probes |
| `T-RPT-001..004`, `T-RPT-010..016`, `T-RPT-020..022`, `T-REQ-009`, `T-DASH-002..006` | `docker compose exec -T api pytest -q` | `tests/unit/test_repository_list_all_requirements_cap.py`, `tests/unit/test_requirements_report_export_filters.py`, `tests/unit/test_csv_safe_cell.py`, `tests/performance/test_performance.py` |
| `T-AUD-010..019`, `T-AUD-030..031`, `T-AUD-040..041` | `docker compose exec -T api pytest -q` | `tests/unit/test_audit_routes.py`, `tests/unit/test_scheduler_audit.py`, `tests/integration/test_email_intake.py`, `tests/security/test_security.py` |
| `T-NOT-004..007`, `T-SCH-001..003` | `docker compose exec -T api pytest -q` | `tests/unit/test_notifications.py`, `tests/unit/test_notification_routes.py`, `tests/unit/test_notification_read.py`, `tests/integration/test_notification_perms.py`, `tests/unit/test_scheduler_audit.py` |
| `T-SEC-014..017`, `T-SEC-021`, `T-SEC-030..031`, `T-SEC-040..041` | `docker compose exec -T api pytest -q` plus `make validate-https` | `tests/security/test_security.py`, `tests/unit/test_file_validation.py`, live proxy/header gate |
| extraction/queue reliability checks | `make test-worker-queues-docker` | Extraction and OCR retry/dead-letter queue tests in Docker |

## Manual-Only Residual Checks

These remain outside the automated project verification run because the
required tool is external to the repo or the behavior is controlled by the OS
or browser shell:

- screen-reader walkthroughs such as NVDA / VoiceOver (`T-A11Y-002`)
- reduced-motion verification against OS settings (`T-A11Y-008`)
- toast live-region announcements with assistive tech (`T-A11Y-007`)
- browser password-manager prompts and autofill shell behavior (`T-UI-023`, `T-UI-025`)
- print-preview fidelity (`T-UI-007`)
- theme/contrast checks that require a true alternate theme if one is added later (`T-UI-005`, `T-UI-006`)

Those are still valid product expectations. They are simply not owned by the
automated verification runner.
