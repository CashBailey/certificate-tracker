#!/usr/bin/env bash
# rotate-worker-passwords.sh
#
# Reads the worker DB passwords from .env, runs ALTER ROLE for each
# worker user in PostgreSQL, then restarts the worker containers so
# they reconnect with the new credentials.
#
# Usage: ./scripts/rotate-worker-passwords.sh
#   Run from the project root (where docker-compose.yml lives).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env file not found at $ENV_FILE" >&2
  exit 1
fi

# Source .env (only the variables we need)
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

# Validate that passwords are set and not placeholder
for var in EXTRACTION_WORKER_DB_PASSWORD SCHEDULER_WORKER_DB_PASSWORD EMAIL_INTAKE_WORKER_DB_PASSWORD; do
  val="${!var:-}"
  if [[ -z "$val" || "$val" == "PLACEHOLDER_SET_VIA_ENV" ]]; then
    echo "ERROR: $var is unset or still a placeholder in .env" >&2
    exit 1
  fi
done

echo "==> Rotating worker database passwords..."

# Use the superuser (laredo) to ALTER ROLE passwords.
# PGPASSWORD comes from docker-compose environment for the postgres service.
run_sql() {
  local sql="$1"
  docker compose exec -T \
    -e PGPASSWORD=laredo_dev_password \
    postgres \
    psql -U laredo -d laredo_certificates -c "$sql"
}

# Escape single quotes in passwords for SQL safety
escape_sql() {
  printf '%s' "$1" | sed "s/'/''/g"
}

EXT_PW=$(escape_sql "$EXTRACTION_WORKER_DB_PASSWORD")
SCH_PW=$(escape_sql "$SCHEDULER_WORKER_DB_PASSWORD")
EMAIL_PW=$(escape_sql "$EMAIL_INTAKE_WORKER_DB_PASSWORD")

run_sql "ALTER ROLE laredo_extraction_worker WITH PASSWORD '${EXT_PW}';"
echo "    [OK] laredo_extraction_worker password updated"

run_sql "ALTER ROLE laredo_scheduler_worker WITH PASSWORD '${SCH_PW}';"
echo "    [OK] laredo_scheduler_worker password updated"

run_sql "ALTER ROLE laredo_email_intake_worker WITH PASSWORD '${EMAIL_PW}';"
echo "    [OK] laredo_email_intake_worker password updated"

echo "==> Restarting worker containers..."
docker compose restart extraction-worker scheduler-worker ocr-engine
# NOTE: email-intake-worker runs in a separate compose profile ("email").
# If it is running, restart it separately:
#   docker compose --profile email restart email-intake-worker

echo "==> Waiting 5 seconds for workers to reconnect..."
sleep 5

echo "==> Done. Check worker logs with:"
echo "    docker compose logs --tail=10 extraction-worker scheduler-worker ocr-engine"
