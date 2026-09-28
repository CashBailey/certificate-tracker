# Auth Lockout, Rate Limiting & Admin Recovery — Design + Implementation Plan

> **Status:** PR1 + PR2 shipped (commits `a18f96c` + `8c3439f`). PR0/PR3/PR4a/PR4b pending.
> **Last updated:** 2026-04-19

This document is the **durable handoff** for implementing the remaining PRs. It consolidates: (1) the source design, (2) the implementation plan, (3) what's already done, (4) what's left, with file:line pointers and verification commands.

## Overall progress

| PR | Status | Commit | Effort actual / est |
|---|---|---|---|
| PR1 — SlowAPI Redis backend (TLS-aware) + forgot-password 5/hour | ✅ Shipped | `a18f96c` | ~1h / 0.5–1h |
| PR2 — Migration 037 (5 lockout columns + partial index) | ✅ Shipped | `8c3439f` | ~30min / 0.5–1h |
| PR0 — Test fixture infrastructure (freezegun + fakeredis) | ⬜ Pending | — | est 1–2h |
| PR3 — Backend behavior (the meaty one) | ⬜ Pending | — | est 12–18h |
| PR4a — Frontend modal + badge + toast | ⬜ Pending | — | est 3–4h |
| PR4b — Dashboard widget + audit deep-link | ⬜ Pending | — | est 1–2h |
| **Total remaining** | | | **17–26 hours** |

---

## What's already done (do NOT re-do)

### PR1 (commit `a18f96c`)

`CoreInstances/ApiServer/src/auth/router.py`:
- Added `import os` at top
- New `_slowapi_storage_uri()` helper (lines ~24–48) that builds a TLS-aware Redis storage URI for SlowAPI. Required because SlowAPI delegates to the `limits` library which uses its own Redis client (not `shared/tls.py`); plain `rediss://` URLs cause `CERTIFICATE_VERIFY_FAILED` 500s.
- `Limiter(... storage_uri=_slowapi_storage_uri())` instead of in-memory default
- `/auth/forgot-password` decorator changed `5/minute` → `5/hour`
- Updated docstring on `forgot_password` to reflect new window + future per-email throttle

`docs/OPERATIONS.md`:
- New "Rate Limiting" section appended before "Out of Scope"
- Documents the 4 limits, fail-open posture, and verification command (`redis-cli --scan --pattern 'LIMITS:*'`)

**Verification:** 5 forgot-password requests succeed (202), 6th + 7th return 429. Redis key created at `LIMITS:LIMITER/<ip>//auth/forgot-password/5/1/hour`. Confirmed during ship.

### PR2 (commit `8c3439f`)

`CoreInstances/ApiServer/alembic/versions/037_add_account_lockout_columns.py`:
- Added 5 columns to `certificates.employees`:
  - `locked_until` (TIMESTAMPTZ NULL)
  - `lockout_level` (SmallInteger NOT NULL default 0)
  - `failed_login_count` (SmallInteger NOT NULL default 0)
  - `last_failed_login_at` (TIMESTAMPTZ NULL)
  - `last_lockout_at` (TIMESTAMPTZ NULL)
- Partial index `ix_employees_locked_until ... WHERE locked_until IS NOT NULL`
- Round-trip downgrade tested clean

**Current alembic head:** `037 (head)`.

**DB state after PR2:** all 2005 existing employees have `locked_until=NULL`, `lockout_level=0`, `failed_login_count=0`. Login flow unchanged (SQLAlchemy uses explicit columns, ignores unknown fields until PR3 ships ORM updates).

---

## What's left

### PR0 — Test fixture infrastructure (do BEFORE PR3)

**Why:** PR3 has ~74 new tests. Many are time-dependent (lockout durations, escalation curve) and Redis-dependent (atomic INCR, IP-diversity SET). Without `freezegun` + `fakeredis` fixtures, tests are flaky and untestable.

**Files:**
- `CoreInstances/ApiServer/requirements-dev.txt` — verify presence of `freezegun>=1.5.0` and `fakeredis>=2.20.0`; add if missing
- `CoreInstances/ApiServer/tests/conftest.py` — add fixtures:
  - `fake_redis` — `fakeredis.aioredis.FakeRedis()` per-test, monkeypatched into `auth.service` and `routes/admin.py`
  - `frozen_clock` — `freezegun.freeze_time("2026-01-01T12:00:00+00:00")`
  - `mock_smtp` — replaces `send_account_setup_email` and the upcoming `send_account_locked_notification` / `send_account_unlocked_notification`
  - `clean_redis_keys` (autouse) — `fakeredis.flushall()` between tests
- `CoreInstances/ApiServer/tests/security/conftest.py` — `admin_actor`, `coordinator_actor` Employee fixtures
- `CoreInstances/ApiServer/tests/integration/conftest.py` — `with_two_ips(client)` helper

**Verification:** existing `pytest CoreInstances/ApiServer/tests/ -q` still all green; new `tests/unit/test_fixtures_smoke.py` proves fixtures yield the expected types.

### PR3 — Backend behavior (the big one)

**This is ~12–18h of focused work spanning ~10 files.** The full breakdown is below; complete file-by-file specs are in `/tmp/team-impl-JacMQx7v/deliverable.md` §2.6 (will be deleted on /clear; copy any specifics needed from there before then).

**Critical sequencing constraint:** PR2's migration MUST be in DB before PR3 deploys (it is — alembic head is `037`). After ship: container restart = if `alembic current ≠ 037`, every login crashes with `UndefinedColumn`.

**Files modified:**

| File | What |
|---|---|
| `CoreInstances/ApiServer/src/shared/models.py` | Add 5 lockout fields to `Employee` dataclass with Python defaults |
| `CoreInstances/ApiServer/src/shared/orm_models.py` | Add 5 mapped columns to `EmployeeORM` |
| `CoreInstances/ApiServer/src/shared/repository.py` | Update `_employee_orm_to_model()` (~line 228) to include 5 new fields; add `update_lockout_state()`, `clear_lockout_state()`, `get_all_admins()`, `count_locked_employees()`, `list_locked_employees()` |
| `CoreInstances/ApiServer/src/shared/repositories/employee.py` | Update `_to_model()` (~line 155) — **PARALLEL conversion site, MUST be updated**; add `update_lockout_state()`, `clear_lockout_state()` |
| `CoreInstances/ApiServer/src/auth/service.py` | Rewrite `_is_locked_out`, `_check_and_increment_failures`, `_clear_failures`; add `_check_ip_diversity()`; add per-email rate check in `forgot_password()`; emit 3 new audit events; clear lockout state in `reset_password()`; update `authenticate()` to read `locked_until` from DB. **Honor `LOCKOUT_BEHAVIOR_DISABLED` env flag.** |
| `CoreInstances/ApiServer/src/routes/admin.py` | Add `POST /accounts/{id}/unlock` and `POST /accounts/{id}/unlock-and-reset`; per-IP `20/min` (SlowAPI); per-Admin actor `5/hour` (Redis); self-unlock guard; mandatory `note`. Call notification helper gated by `LOCKOUT_USER_NOTIFY_ENABLED`. |
| `CoreInstances/ApiServer/src/routes/employees.py` | Extend `GET /employees` with `?locked=true` filter (`WHERE locked_until > now()`) — needed by PR4b dashboard widget |
| `CoreInstances/FrontendWebServer/src/pages/AuditPage.tsx` | Add 7 new keys to `ACTION_LABELS` |

**Files added:**

| File | Purpose |
|---|---|
| `CoreInstances/ApiServer/src/auth/notifications.py` | `send_account_locked_notification(employee, level, locked_until)` and `send_account_unlocked_notification(employee, admin, ip, action_type)`. Templates include unlocking Admin's name + IP. |
| `scripts/unlock_employee.py` | CLI escape hatch for system-Admin lockout. Runs as `laredo` superuser; prompts for employee_id + note; writes audit row with `actor_type=System` and `details.source: "cli"`. |
| `docs/OPERATIONS.md` (append) | Two new sections: "Emergency: Recovering a Locked-Out System Admin" + "Lockout — Operational Notes" (env flags, Redis key patterns) |
| `tests/unit/test_lockout_service.py` | ~28 cases (IP-diversity, escalation, decay, Admin role exemption, anti-enum, per-email rate, single-IP boundary 5–14) |
| `tests/security/test_admin_unlock.py` | ~16 cases (RBAC + per-Admin rate + user-notification email assertions) |
| `tests/unit/test_cli_unlock_script.py` | 3 CLI tests |
| `tests/integration/test_lockout_e2e.py` | 5 E2E flows |

**Key constants for `auth/service.py`:**
```python
_LOCKOUT_DURATIONS_MINUTES = [0, 15, 30, 60, 240]  # index = lockout_level 1–4
_LOCKOUT_SENTINEL = datetime(9999, 12, 31, tzinfo=timezone.utc)  # level 5
_LOCKOUT_THRESHOLD = 5
_LOCKOUT_ABSOLUTE_CAP = 15  # single-IP forced-lock cap
_ADMIN_LOCKOUT_LEVEL_CAP = 2  # Admin role never escalates past L2
LOCKOUT_BEHAVIOR_DISABLED = os.getenv("LOCKOUT_BEHAVIOR_DISABLED", "false").lower() == "true"
LOCKOUT_USER_NOTIFY_ENABLED = os.getenv("LOCKOUT_USER_NOTIFY_ENABLED", "false").lower() == "true"
```

**Atomic CAS UPDATE clause** (don't simplify):
```sql
UPDATE certificates.employees
SET locked_until = $1, lockout_level = $2, last_lockout_at = $3
WHERE id = $4
  AND lockout_level = $5  -- expected current level (CAS for escalation race)
  AND (locked_until IS NULL OR locked_until < $6)  -- engagement race
```

**IP-diversity guard logic:**
```
If failed_login_count >= 5:
  scard = SCARD login_fail_ips:{employee_id}
  if scard == 1: do NOT lock (per-IP rate limit absorbs)
  if scard >= 2: lock at next level
  if failed_login_count >= 15: lock regardless of IP count (absolute cap)
```

**`AuditPage.tsx` ACTION_LABELS to add:**
```typescript
account_locked: 'Account locked',
account_unlocked: 'Account unlocked by admin',
account_unlocked_and_reset: 'Account unlocked and reset by admin',
forgot_password_requested: 'Password reset requested',
forgot_password_rate_limited: 'Password reset rate limited',
password_reset_token_reused: 'Password reset token reused',
admin_unlock_rate_limited: 'Admin unlock rate limited',
```

**Feature flag deploy strategy:**
- `LOCKOUT_BEHAVIOR_DISABLED` ships default `false` (lockout active). Kill switch — flip to `true` if production lockout storm.
- `LOCKOUT_USER_NOTIFY_ENABLED` ships default `false` for first 48h post-deploy. Flip to `true` only after lockout-rate metrics are sane.

### PR4a — Frontend admin UI

**Files modified:**
- `CoreInstances/FrontendWebServer/src/api/index.ts` — extend `User` interface with `locked_until: string | null`, `lockout_level: number`, `failed_login_count: number`; add `unlockAccount(id, note)` and `unlockAndResetAccount(id, note)`; extend `getEmployees` with `locked: boolean` param
- `CoreInstances/FrontendWebServer/src/pages/EmployeesPage.tsx` — add `locked` to `activeFilter`; LockedBadge in row; per-row Unlock button (Admin-only, self-blocked); wire to UnlockConfirmModal

**Files added:**
- `CoreInstances/FrontendWebServer/src/components/LockedBadge.tsx` — red badge, tooltip per level
- `CoreInstances/FrontendWebServer/src/components/UnlockConfirmModal.tsx` — warning banner + lockout context + required note + "Unlock & Email" button
- `CoreInstances/FrontendWebServer/src/components/ToastProvider.tsx` — minimal toast context

### PR4b — Dashboard widget + audit deep-link

**Files modified:**
- `CoreInstances/FrontendWebServer/src/pages/DashboardPage.tsx` — add `lockedAccounts: number` to stats; fetch via `getEmployees({locked: true, limit: 1}).total`; render "Locked Accounts: N" stat card (Admin-only, error variant when > 0)
- `CoreInstances/FrontendWebServer/src/pages/AuditPage.tsx` — add `useSearchParams`; initialize `drillTarget` from `?target_type=` and `?target_id=` (~5 LOC; supports toast deep-link from PR4a)

---

## Test strategy (full plan in critique → handoff)

**~74 new automated cases across PR3 + PR4a + PR4b.** Coverage targets per file:

| File / module | Target |
|---|---|
| `auth/service.py::_check_and_increment_failures` | 100% branches |
| `auth/service.py::_clear_failures` | 100% branches |
| `auth/service.py::forgot_password` | 100% line, 90% branch |
| `auth/service.py::authenticate` | 95% branch (don't regress) |
| `routes/admin.py::unlock`, `unlock_and_reset` | 100% branches |
| `scripts/unlock_employee.py` | 90% line |
| `LockedBadge.tsx`, `UnlockConfirmModal.tsx` | 100% statement |

**Regression guard** (must stay green unmodified):
- `tests/unit/test_auth_service.py`
- `tests/security/test_security.py`
- `tests/integration/test_e2e_flows.py`
- `pages/__tests__/EmployeesPage.test.tsx` (existing portion)

---

## Industry standards anchored to (for PR-review defense)

- **NIST SP 800-63B Rev 4 §3.2.2** — ≤100 consecutive failed attempts before disabling. We lock at 5 (well below ceiling).
- **OWASP ASVS V2.2.1** — ≤100/hour on a single account.
- **OWASP ASVS V2.2.3** — notify on credential changes.
- **OWASP ASVS v5 V6.4.6** — admin can initiate reset BUT MUST NOT change or choose user's password. Non-negotiable for government systems. Our `/unlock-and-reset` issues a setup-email token; admin never sees the password.
- **Cloudflare WAF** — tiered IP throttle (5/hour at 1-hour window for forgot-password).
- **Auth0 / Microsoft Entra ID** — concrete defaults (5–10 attempts threshold, progressive lockout).

---

## Operational risks (accepted)

- **Redis fail-open** — both lockout counter and SlowAPI fall back gracefully on Redis outage. Failing closed would convert Redis disruption into total auth DoS. **Required compensating control:** monitoring + alerting on `redis_ping_latency_ms` and `redis_up` (must exist before PR3 production).
- **JWT issued seconds before lockout** valid until access-token expiry (15 min default). Intrinsic to stateless JWTs.
- **Distributed botnet** still triggers lockout (intentional — protect credential). Forgot-password remains escape hatch per OWASP.
- **1-Admin deployments** require CLI escape hatch (`scripts/unlock_employee.py`). Long-term recommendation: maintain ≥2 Admin accounts.
- **Texas-specific compliance** (TX Gov't Code Ch. 552, TX Bus. & Com. Code §521) — flagged for legal review separately. Out of scope here.

---

## File pointers — quick reference for PR3 implementer

| Need to find | Path | Line |
|---|---|---|
| Existing lockout helpers | `CoreInstances/ApiServer/src/auth/service.py` | 31–88 |
| `authenticate()` (modify locked_until check) | `CoreInstances/ApiServer/src/auth/service.py` | 109 |
| `forgot_password()` (add per-email throttle) | `CoreInstances/ApiServer/src/auth/service.py` | 389 |
| `reset_password()` (clear lockout state) | `CoreInstances/ApiServer/src/auth/service.py` | ~440 |
| `Employee` dataclass | `CoreInstances/ApiServer/src/shared/models.py` | 127 |
| `EmployeeORM` | `CoreInstances/ApiServer/src/shared/orm_models.py` | 37 |
| `_employee_orm_to_model()` PRIMARY conversion | `CoreInstances/ApiServer/src/shared/repository.py` | ~228 |
| `_to_model()` SECONDARY conversion (BOTH MUST UPDATE) | `CoreInstances/ApiServer/src/shared/repositories/employee.py` | ~155 |
| Existing admin router (new endpoints land here) | `CoreInstances/ApiServer/src/routes/admin.py` | end |
| `AuditPage.tsx` ACTION_LABELS dict | `CoreInstances/FrontendWebServer/src/pages/AuditPage.tsx` | ~13 |
| `EmployeesPage.tsx` filter/row structure | `CoreInstances/FrontendWebServer/src/pages/EmployeesPage.tsx` | — |
| `User` interface in API client | `CoreInstances/FrontendWebServer/src/api/index.ts` | ~11 |
| Migration template (alembic) | `CoreInstances/ApiServer/alembic/versions/037_add_account_lockout_columns.py` | shipped reference |

---

## Verification commands (for the next implementer)

```bash
# Confirm PR1 + PR2 are still in place after rebase / pull
git log --oneline | head -10
docker exec laredo-api alembic -c /app/alembic.ini current  # should show 037 (head)

# Confirm PR1 limiter is Redis-backed
docker exec laredo-api python -c "from src.auth.router import limiter; print(limiter._storage)"

# Confirm PR2 columns exist
docker exec -e PGPASSWORD=laredo_dev_password laredo-postgres psql -U laredo -d laredo_certificates -c "\d certificates.employees" | grep -E "locked_until|lockout_level|failed_login_count|last_failed_login_at|last_lockout_at"

# Confirm forgot-password 6/hour returns 429
for i in 1 2 3 4 5 6; do curl -ksS -o /dev/null -w "%{http_code} " -X POST https://localhost/api/auth/forgot-password -H "Content-Type: application/json" -d '{"email":"janedoe@ci.laredo.tx.us"}'; done; echo

# Confirm PR3 wiring after implementation
pytest CoreInstances/ApiServer/tests/unit/test_lockout_service.py -v
pytest CoreInstances/ApiServer/tests/security/test_admin_unlock.py -v
pytest CoreInstances/ApiServer/tests/integration/test_lockout_e2e.py -v
```

---

## Test users for the next session

The dev DB has Admin / Coordinator / Employee test accounts seeded. To set
or rotate their passwords for a fresh session, run the standard auth
recovery flow against each:

1. `POST /api/auth/forgot-password` (or `POST /api/api/employees/{id}/send-setup-email` from an authenticated Admin/Coordinator).
2. Read the reset link from local greenmail at `http://127.0.0.1:8080/api/user/<email>/messages`.
3. `POST /api/auth/reset-password` with the token + a fresh strong password.

Detailed recipe in MemPalace `code-snippets/greenmail-fetch.md`. Do NOT
commit working credentials to this file — the dev test accounts are
documented by EMAIL only; passwords stay in the operator's local notes
or password manager.

Seeded test emails (from `scripts/seed_demo_data.py`):
- System Admin: `admin@ci.laredo.tx.us` (id 1)
- Test Coordinator: `janedoe@ci.laredo.tx.us` (id 4004 — was inactive, may need DB activation: `UPDATE certificates.employees SET is_active=true WHERE id=4004;`)
- Test Employee: `enrique.delgado@ci.laredo.tx.us` (id 2003) — note: cannot log in by design (INV-06 in auth/service.py:142–144)

---

This document is the source of truth for PR0/PR3/PR4a/PR4b. The ephemeral team-design + team-impl artifacts in `/tmp/team-bCv0HesA/` and `/tmp/team-impl-JacMQx7v/` will be deleted on `/clear`; everything load-bearing has been distilled here.
