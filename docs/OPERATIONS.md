# Operations Guide (Scoped)

This runbook is limited to:

- `CoreInstances/ApiServer`
- `CoreInstances/FrontendWebServer`
- `BackgroundProcessingInstances/EmailIntakeWorker`
- `BackgroundProcessingInstances/ExtractionWorker`
- `BackgroundProcessingInstances/OcrEngine`
- `BackgroundProcessingInstances/SchedulerNotificationWorker`

## Prerequisites

- Docker + Docker Compose
- `make`
- `openssl` ≥ 1.1.1 (for TLS certificate generation)
- `.env` configured from `.env.example`

## Setup

```bash
make setup

# Generate TLS certificates (one-time; required before first docker compose up)
bash docker/tls/generate_certs.sh
```

Before first startup, set required secrets in `.env`:

- `MINIO_ROOT_PASSWORD`
- `PGADMIN_PASSWORD` (required by compose even if you do not start the `dev-tools` profile)
- `SECRET_KEY`

## Start Scoped Stack

Use Compose services required for the in-scope components:

```bash
docker compose --profile security --profile email-intake up -d postgres redis minio clamav api frontend email-intake-worker extraction-worker ocr-engine scheduler-worker
```

Optional full-stack startup remains available with `make up`, but this guide focuses only on scoped components.

## Health / Status

```bash
docker compose ps
make health
```

## Logs

```bash
docker compose logs -f api frontend email-intake-worker extraction-worker ocr-engine scheduler-worker
```

## Test and Lint

From root:

```bash
make test
make test-cov
make lint
make verify-project
```

`make verify-project` is the safe project-wide verification entrypoint. It runs
the frontend build, full API pytest suite, HTTPS gates, worker queue tests, and
the supported browser audit. The password-mutating live auth/mail check is
reported as `SKIP` unless you explicitly run against an isolated development
database with `RUNTIME_AUTH_ALLOW_MUTATION=1 make verify-project`. The summary
is written to `verification/results/project-verification-*.md`.

## Configuration (Scoped)

| Variable | Used By | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | ApiServer, ExtractionWorker, EmailIntakeWorker | Database connectivity |
| `REDIS_URL` | ApiServer, EmailIntakeWorker, ExtractionWorker, OcrEngine | Queue transport |
| `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | ApiServer, EmailIntakeWorker, ExtractionWorker | Object storage access |
| `MINIO_ENCRYPTION_KEY` | MinIO (KMS) | Base64-encoded 32-byte key for server-side object encryption. Default in `.env.example` is a dev placeholder — **must be replaced** in production with `openssl rand -base64 32`. |
| `MINIO_KMS_AUTO_ENCRYPTION` | MinIO | When `on`, all objects written to MinIO are encrypted at rest using the KMS key. Default: `on`. |
| `SECRET_KEY` | ApiServer | Auth/session security configuration |
| `SESSION_MAX_HOURS` | ApiServer | Wall-clock session limit in hours (default: 8; must be 1–72) |
| `VITE_API_URL` | FrontendWebServer | Frontend API base URL |
| `IMAP_*` | EmailIntakeWorker | Email inbox intake configuration |
| `ALLOWED_EMAIL_DOMAIN` | EmailIntakeWorker | Sender-domain validation |
| `EMAIL_POLL_INTERVAL_SECONDS` | EmailIntakeWorker | Polling cadence |
| `CLAMAV_ENABLED` / `CLAMAV_HOST` / `CLAMAV_PORT` / `CLAMAV_FAIL_OPEN` | EmailIntakeWorker | Malware scanning policy (`CLAMAV_FAIL_OPEN=false` default for fail-closed behavior) |
| `TESSERACT_LANG` | OcrEngine | OCR language profile |
| `LLM_*` | ExtractionWorker | Extraction model behavior |
| `TLS_ENABLED` | All services | Enable mutual TLS for all backend connections (`true` by default) |
| `TLS_CA_CERT` | All services | Path to CA cert inside container (`/tls/ca.crt`) |
| `TLS_CLIENT_CERT` | All services | Path to client cert inside container (`/tls/client.crt`) |
| `TLS_CLIENT_KEY` | All services | Path to client key inside container (`/tls/client.key`) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | SchedulerNotificationWorker | SMTP credentials for outbound notification emails |
| `NOTIFICATION_FROM_EMAIL` | SchedulerNotificationWorker | From address used on notification emails (default: `noreply@ci.laredo.tx.us`) |

## Storage Encryption

The MinIO `documents` bucket has SSE-S3 encryption enabled automatically on first
startup by `minio-init`.

**Production key setup:**
The `.env.example` value for `MINIO_ENCRYPTION_KEY` is a placeholder. Before going
to production, replace it with a cryptographically random 32-byte key:

```bash
openssl rand -base64 32
```

Store this key in a secrets manager (not in `.env` in version control).

**Key rotation warning:** Changing `MINIO_ENCRYPTION_KEY` after objects have been
written makes all existing stored documents permanently unreadable. MinIO does not
provide an automatic re-encryption migration. Key rotation requires a deliberate
data migration plan before changing the key.

## Troubleshooting

- API fails on boot due to missing DB URL:
  - Ensure `DATABASE_URL` is set and reachable from `api` container.
- Extraction queue appears idle:
  - Check `redis` health and verify `extraction-worker` logs for queue consumption errors.
- OCR requests stall:
  - Verify `ocr-engine` container is running and receiving `ocr_tasks`.
- Email intake not creating tasks:
  - Verify `IMAP_*` credentials and `ALLOWED_EMAIL_DOMAIN` behavior.
- TLS cert errors on startup (`No such file: /tls/ca.crt`):
  - Run `bash docker/tls/generate_certs.sh` from project root. See [docs/TLS.md](TLS.md).

## Rate Limiting

The API uses [SlowAPI](https://slowapi.readthedocs.io/) for per-IP rate limits on auth endpoints. The limiter is configured with `storage_uri=os.getenv("REDIS_URL", "memory://")` so that limits are global across replicas — without the Redis backend, each Gunicorn worker has its own counter and effective limits multiply by the worker count.

**Current limits** (`auth/router.py`):

| Endpoint | Per-IP limit | Window |
|---|---|---|
| `POST /auth/login` | 60 | 1 minute |
| `POST /auth/refresh` | none | n/a |
| `POST /auth/forgot-password` | 5 | 1 hour |
| `POST /auth/reset-password` | 5 | 1 minute |

`/auth/refresh` is intentionally not rate-limited. It is cookie-backed session
maintenance rather than a credential-entry endpoint, and throttling it caused
browser-visible 429s during legitimate multi-tab and long-lived sessions.

**Fail-open posture:** if `REDIS_URL` is unset OR Redis is unreachable at request time, SlowAPI silently falls back to in-memory counters (per-process). This is intentional — failing closed would convert any Redis disruption into a total auth outage. **Mitigation:** monitor Redis health and alert on `redis_ping_latency_ms > 200` for 5+ minutes.

**Verifying the Redis backend is active:**

```bash
docker exec laredo-redis redis-cli --tls --cacert /tls/ca.crt --cert /tls/client.crt --key /tls/client.key -p 6380 --scan --pattern 'LIMITS:*' | head
```

Keys appear as traffic flows through `/auth/*` endpoints. Empty result + active traffic = the limiter has fallen back to memory storage; check `printenv REDIS_URL` inside the api container.

## Out of Scope

Any operational details for services outside the listed paths are intentionally excluded here.
