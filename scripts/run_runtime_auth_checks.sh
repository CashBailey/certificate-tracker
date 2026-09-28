#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ADMIN_EMAIL="${ADMIN_EMAIL:-admin@ci.laredo.tx.us}"
ADMIN_PASSWORD="AdminResetCoverage-$(date +%s)!Aa1"
UNKNOWN_EMAIL="nobody-runtime-check-$(date +%s)@ci.laredo.tx.us"

fail() {
  printf 'FAIL %s\n' "$1" >&2
  exit 1
}

pass() {
  printf 'PASS %s\n' "$1"
}

json_message_count() {
  python3 - <<'PY' "$1"
import json
import sys

raw = sys.argv[1]
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print(0)
    raise SystemExit(0)

if isinstance(data, list):
    print(len(data))
elif isinstance(data, dict) and data.get("message", "").startswith("User "):
    print(0)
else:
    print(0)
PY
}

json_extract_reset_link() {
  python3 - <<'PY' "$1"
import json
import re
import sys

data = json.loads(sys.argv[1])
if not isinstance(data, list) or not data:
    print("")
    raise SystemExit(0)

mime = data[-1].get("mimeMessage", "")
match = re.search(r"https://localhost/reset-password#token=([a-f0-9]+)", mime, re.I)
print(match.group(0) if match else "")
PY
}

extract_fragment_token() {
  python3 - <<'PY' "$1"
import sys
import urllib.parse

parsed = urllib.parse.urlparse(sys.argv[1])
print(urllib.parse.parse_qs(parsed.fragment).get("token", [""])[0])
PY
}

json_access_token() {
  python3 - <<'PY' "$1"
import json
import sys

with open(sys.argv[1], "r", encoding="utf8") as handle:
    data = json.load(handle)
print(data.get("access_token", ""))
PY
}

sha256_hex() {
  python3 - <<'PY' "$1"
import hashlib
import sys

print(hashlib.sha256(sys.argv[1].encode()).hexdigest())
PY
}

target_employee_row() {
  docker exec -i -e PGPASSWORD=laredo_dev_password laredo-postgres \
    psql -U laredo -d laredo_certificates -t -P footer=off -A -F $'\t' <<'SQL'
SELECT id, email
FROM certificates.employees
WHERE email <> 'admin@ci.laredo.tx.us'
  AND is_active = TRUE
ORDER BY id
LIMIT 1;
SQL
}

[[ "${RUNTIME_AUTH_ALLOW_MUTATION:-}" == "1" ]] || fail \
  "runtime auth checks reset a development admin password; rerun with RUNTIME_AUTH_ALLOW_MUTATION=1 against an isolated development database"

for container in laredo-api laredo-postgres laredo-redis laredo-greenmail; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == "true" ]] || fail \
    "required container ${container} is not running; start the development stack with docker compose --profile dev-tools up -d"
done

curl -sf -X POST http://127.0.0.1:8080/api/service/reset >/dev/null || fail \
  "Greenmail reset API is unavailable on 127.0.0.1:8080"

docker exec laredo-redis sh -lc '
redis-cli --tls --cert /tls/client.crt --key /tls/client.key --cacert /tls/ca.crt -p 6380 --scan \
| grep -E "^(LIMITS:LIMITER|login_failures:)" \
| xargs -r redis-cli --tls --cert /tls/client.crt --key /tls/client.key --cacert /tls/ca.crt -p 6380 del >/dev/null
'

admin_forgot_body="$(mktemp)"
unknown_forgot_body="$(mktemp)"
admin_forgot_code="$(
  curl -sk -o "$admin_forgot_body" -w '%{http_code}' \
    -X POST https://localhost/api/auth/forgot-password \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${ADMIN_EMAIL}\"}"
)"
unknown_forgot_code="$(
  curl -sk -o "$unknown_forgot_body" -w '%{http_code}' \
    -X POST https://localhost/api/auth/forgot-password \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${UNKNOWN_EMAIL}\"}"
)"

[[ "$admin_forgot_code" == "202" ]] || fail "forgot-password for admin returned ${admin_forgot_code}"
[[ "$unknown_forgot_code" == "202" ]] || fail "forgot-password for unknown email returned ${unknown_forgot_code}"
pass "forgot-password returns 202 for known and unknown emails"

admin_messages="$(curl -s "http://127.0.0.1:8080/api/user/${ADMIN_EMAIL}/messages")"
unknown_messages="$(curl -s "http://127.0.0.1:8080/api/user/${UNKNOWN_EMAIL}/messages")"
admin_message_count="$(json_message_count "$admin_messages")"
unknown_message_count="$(json_message_count "$unknown_messages")"
[[ "$admin_message_count" -ge 1 ]] || fail "Greenmail did not receive an admin reset email"
[[ "$unknown_message_count" == "0" ]] || fail "Greenmail unexpectedly created mail for unknown user"
pass "Greenmail delivered admin mail and did not create an unknown-user mailbox"

admin_reset_link="$(json_extract_reset_link "$admin_messages")"
[[ -n "$admin_reset_link" ]] || fail "could not extract admin reset link from Greenmail"
admin_reset_token="$(extract_fragment_token "$admin_reset_link")"
[[ -n "$admin_reset_token" ]] || fail "could not extract reset token from admin reset link"

reset_body="$(mktemp)"
reset_code="$(
  curl -sk -o "$reset_body" -w '%{http_code}' \
    -X POST https://localhost/api/auth/reset-password \
    -H 'Content-Type: application/json' \
    -d "{\"token\":\"${admin_reset_token}\",\"new_password\":\"${ADMIN_PASSWORD}\"}"
)"
[[ "$reset_code" == "200" ]] || fail "reset-password returned ${reset_code}"
pass "admin reset token completes successfully"

reuse_body="$(mktemp)"
reuse_code="$(
  curl -sk -o "$reuse_body" -w '%{http_code}' \
    -X POST https://localhost/api/auth/reset-password \
    -H 'Content-Type: application/json' \
    -d "{\"token\":\"${admin_reset_token}\",\"new_password\":\"AnotherStrongPass123!\"}"
)"
[[ "$reuse_code" == "400" ]] || fail "reused reset token returned ${reuse_code}"
pass "used reset token is rejected"

second_forgot_body="$(mktemp)"
second_forgot_code="$(
  curl -sk -o "$second_forgot_body" -w '%{http_code}' \
    -X POST https://localhost/api/auth/forgot-password \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${ADMIN_EMAIL}\"}"
)"
[[ "$second_forgot_code" == "202" ]] || fail "second forgot-password returned ${second_forgot_code}"

second_messages="$(curl -s "http://127.0.0.1:8080/api/user/${ADMIN_EMAIL}/messages")"
second_reset_link="$(json_extract_reset_link "$second_messages")"
[[ -n "$second_reset_link" ]] || fail "could not extract second reset link from Greenmail"
second_reset_token="$(extract_fragment_token "$second_reset_link")"
[[ -n "$second_reset_token" ]] || fail "could not extract second reset token"
second_reset_hash="$(sha256_hex "$second_reset_token")"

docker exec -i -e PGPASSWORD=laredo_dev_password laredo-postgres \
  psql -U laredo -d laredo_certificates <<SQL >/dev/null
UPDATE certificates.password_reset_tokens
SET expires_at = NOW() - INTERVAL '5 minutes'
WHERE token_hash = '${second_reset_hash}';
SQL

expired_body="$(mktemp)"
expired_code="$(
  curl -sk -o "$expired_body" -w '%{http_code}' \
    -X POST https://localhost/api/auth/reset-password \
    -H 'Content-Type: application/json' \
    -d "{\"token\":\"${second_reset_token}\",\"new_password\":\"ExpiredShouldFail123!\"}"
)"
[[ "$expired_code" == "400" ]] || fail "expired reset token returned ${expired_code}"
pass "expired reset token is rejected"

login_body="$(mktemp)"
login_headers="$(mktemp)"
login_code="$(
  curl -sk -D "$login_headers" -o "$login_body" -w '%{http_code}' \
    -X POST https://localhost/api/auth/login \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}"
)"
[[ "$login_code" == "200" ]] || fail "admin login with new password returned ${login_code}"

access_token="$(json_access_token "$login_body")"
[[ -n "$access_token" ]] || fail "login response did not include an access token"
pass "admin can log in with the runtime-reset password"

target_row="$(target_employee_row)"
target_employee_id="$(printf '%s' "$target_row" | awk -F '\t' 'NF {print $1; exit}')"
target_employee_email="$(printf '%s' "$target_row" | awk -F '\t' 'NF {print $2; exit}')"
[[ -n "$target_employee_id" && -n "$target_employee_email" ]] || fail "could not find an active non-admin employee for setup email checks"

setup_code="$(
  curl -sk -o /dev/null -w '%{http_code}' \
    -X POST "https://localhost/api/api/employees/${target_employee_id}/send-setup-email" \
    -H "Authorization: Bearer ${access_token}"
)"
[[ "$setup_code" == "202" ]] || fail "send-setup-email returned ${setup_code}"

setup_messages="$(curl -s "http://127.0.0.1:8080/api/user/${target_employee_email}/messages")"
setup_message_count="$(json_message_count "$setup_messages")"
[[ "$setup_message_count" -ge 1 ]] || fail "setup email was not delivered to ${target_employee_email}"
pass "admin-triggered setup email is delivered through Greenmail"

unauth_employees_code="$(curl -sk -o /dev/null -w '%{http_code}' "https://localhost/api/api/employees?limit=1")"
admin_audit_code="$(
  curl -sk -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${access_token}" \
    "https://localhost/api/api/audit-logs?limit=1"
)"
admin_requirements_code="$(
  curl -sk -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${access_token}" \
    "https://localhost/api/api/requirements/paged?page=1&page_size=5"
)"
admin_reports_code="$(
  curl -sk -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${access_token}" \
    "https://localhost/api/api/reports/requirements?format=csv"
)"

[[ "$unauth_employees_code" == "401" ]] || fail "unauthenticated employees probe returned ${unauth_employees_code}"
[[ "$admin_audit_code" == "200" ]] || fail "admin audit probe returned ${admin_audit_code}"
[[ "$admin_requirements_code" == "403" ]] || fail "admin requirements probe returned ${admin_requirements_code}"
[[ "$admin_reports_code" == "403" ]] || fail "admin reports probe returned ${admin_reports_code}"
pass "runtime RBAC probes match the mounted API behavior"

printf 'SUMMARY forgot_admin=202 forgot_unknown=202 reset_success=200 reset_reuse=400 reset_expired=400 login_admin=200 unauth_employees=401 admin_audit=200 admin_requirements=403 admin_reports=403\n'
