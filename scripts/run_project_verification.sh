#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
RESULTS_DIR="$ROOT_DIR/verification/results"
mkdir -p "$RESULTS_DIR"

SUMMARY_PATH="$RESULTS_DIR/project-verification-${STAMP}.md"
OVERALL_STATUS=0

cat >"$SUMMARY_PATH" <<EOF
# Project Verification

- Run at: ${STAMP}
- Working tree: ${ROOT_DIR}

| Step | Status | Command | Log |
| --- | --- | --- | --- |
EOF

run_step() {
  local slug="$1"
  local label="$2"
  local command="$3"
  local log_path="$RESULTS_DIR/${STAMP}-${slug}.log"
  local status="PASS"

  {
    printf '$ %s\n\n' "$command"
    bash -lc "$command"
  } >"$log_path" 2>&1 || status="FAIL"

  if [[ "$status" != "PASS" ]]; then
    OVERALL_STATUS=1
  fi

  printf '| %s | %s | `%s` | `%s` |\n' \
    "$label" "$status" "$command" "$log_path" >>"$SUMMARY_PATH"
}

skip_step() {
  local slug="$1"
  local label="$2"
  local command="$3"
  local reason="$4"
  local log_path="$RESULTS_DIR/${STAMP}-${slug}.log"

  printf 'SKIP %s\n' "$reason" >"$log_path"
  printf '| %s | SKIP | `%s` | `%s` |\n' \
    "$label" "$command" "$log_path" >>"$SUMMARY_PATH"
}

run_step "frontend-build" "Frontend Build" "docker compose exec -T frontend sh -lc 'cd /app && npm run build'"
run_step "api-pytest" "API Pytest" "docker compose exec -T api pytest -q"
if [[ "${RUNTIME_AUTH_ALLOW_MUTATION:-}" == "1" ]]; then
  run_step "runtime-auth" "Runtime Auth/Mail Checks" "bash scripts/run_runtime_auth_checks.sh"
else
  skip_step \
    "runtime-auth" \
    "Runtime Auth/Mail Checks" \
    "RUNTIME_AUTH_ALLOW_MUTATION=1 bash scripts/run_runtime_auth_checks.sh" \
    "requires an isolated development database because it resets the development admin password"
fi
run_step "https-gate" "HTTPS Gate" "make validate-https"
run_step "worker-queues" "Worker Queue Tests" "make test-worker-queues-docker"
run_step "browser-audit" "Browser Audit" "npm --prefix e2e run audit"

cat >>"$SUMMARY_PATH" <<EOF

## Overall

- Status: $(if [[ "$OVERALL_STATUS" -eq 0 ]]; then echo PASS; else echo FAIL; fi)
- Browser audit artifacts: \`e2e/results/browser-audit-strict-*.md\`, \`e2e/results/browser-audit-strict-*.json\`
- Note: browser-only automation is intentionally limited to the supported scope in \`e2e/browser-audit-scope.mjs\`. Project-wide replacements and manual-only residual checks are documented in \`docs/PROJECT_VERIFICATION.md\`.
EOF

printf 'Wrote %s\n' "$SUMMARY_PATH"
exit "$OVERALL_STATUS"
