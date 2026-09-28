# City of Laredo - Certificate Management System

A comprehensive system for managing employee certificate submissions, automated data extraction, review workflows, and compliance tracking for the City of Laredo.

## Features

- **Email Intake** - Employees submit certificates via email; attachments are automatically processed
- **OCR & Extraction** - Intelligent document parsing with template matching and fallback OCR
- **Review Workflow** - Coordinators review extracted data with side-by-side document viewing
- **Compliance Tracking** - Track certificate requirements, due dates, and expirations
- **Configuration Management** - Coordinator-managed certificate types, alert rules, and notification settings
- **Automated Notifications** - Configurable reminder intervals and daily overdue alerts
- **Audit Logging** - Append-only audit trail with dual timestamps, actor tracking, and Admin-only governance views

---

## Architecture

```text
                    ┌─────────────┐
                    │   Caddy     │  (reverse proxy / TLS termination)
                    │   :443      │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────────────────────────┐
│  Frontend   │     │   API        │───▶│           Workers               │
│  (React)    │     │  (FastAPI)  │     │  Extraction | OCR | Scheduler   │
│  :3000      │     │  :8000      │     │  Email Intake                   │
└─────────────┘     └──────┬──────┘     └───────────────┬─────────────────┘
                           │                            │
              ┌────────────┼────────────┼───────────────┘
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Postgres │ │  Redis   │ │  MinIO   │
        │  :5432   │ │  :6380   │ │  :9000   │
        └──────────┘ └──────────┘ └──────────┘
              (all internal connections use mTLS)
```

**Components:**

- **Caddy** - Reverse proxy with automatic TLS termination (CRIT-06)
- **Frontend** - React 18 + TypeScript + Vite web application
- **API** - FastAPI backend with SQLAlchemy ORM
- **Workers** - Background processors for extraction, OCR, notifications, and email intake
- **PostgreSQL** - Primary database with Alembic migrations
- **Redis** - Cache and task queue
- **MinIO** - S3-compatible object storage for documents

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) (includes Docker Compose)
- Git
- `openssl` ≥ 1.1.1 (used by `generate_certs.sh`; pre-installed on macOS and most Linux distros)
- 4GB+ RAM available for Docker

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/CashBailey/certificate-tracker
cd CityOfLaredoProject

# 2. Create and configure .env
cp .env.example .env
# REQUIRED before startup: set MINIO_ROOT_PASSWORD, PGADMIN_PASSWORD, SECRET_KEY

# 3. Validate config and build images
make setup

# 4. Generate TLS certificates (one-time setup)
bash docker/tls/generate_certs.sh

# 5. Start services
make up

# 6. Wait for services to be healthy (~30-60 seconds)
docker compose ps

# 7. Access the application
# Frontend: https://localhost
# API Health: https://api.localhost/health
# API Docs (debug only): https://api.localhost/docs
```

---

## Services & Ports

| Service           | URL                                        | Description              |
| ----------------- | ------------------------------------------ | ------------------------ |
| Frontend          | <https://localhost>                         | React web application    |
| API (via Caddy)   | <https://localhost/api/>                    | FastAPI REST API         |
| API Health        | <https://api.localhost/health>             | Health check             |
| API Docs          | <https://api.localhost/docs>               | Swagger UI (debug only)  |
| pgAdmin           | <https://pgadmin.localhost>                | Database admin UI        |
| MinIO Console     | <https://minio.localhost>                  | Storage admin UI         |
| Greenmail Web     | <http://127.0.0.1:8080>                   | Email admin API (dev)    |
| Roundcube Webmail | <http://127.0.0.1:9090>                   | Email UI for testing     |

**Note:** All services except Roundcube and Greenmail are HTTPS-only via Caddy with self-signed certificates. Accept the browser certificate warning on first visit, or install Caddy's root CA (see below). PostgreSQL, Redis, Ollama, ClamAV, and MinIO S3 API are internal-only with no host port.

---

## Default Credentials

| Service            | Username             | Password                      |
| ------------------ | -------------------- | ----------------------------- |
| **API (Admin)**    | `admin@ci.laredo.tx.us` | Use the password setup flow — no default password is set after migration. Send a setup email via `POST /api/employees/{id}/send-setup-email` to issue a one-time password-reset link. |
| **MinIO Console**  | `minioadmin` (default user) | from `.env` `MINIO_ROOT_PASSWORD` |
| **PostgreSQL**     | laredo               | laredo_dev_password           |
| **pgAdmin**        | `admin@ci.laredo.tx.us` | from `.env` `PGADMIN_PASSWORD` |
| **Greenmail IMAP** | any                  | any                           |

Development defaults only. Set strong `MINIO_ROOT_PASSWORD`, `PGADMIN_PASSWORD`, and `SECRET_KEY` before startup.

---

## Development Workflow

### Hot Reloading

Code changes are automatically detected:

- **Backend** (`CoreInstances/ApiServer/src/`) - Uvicorn auto-reloads (~2 sec)
- **Frontend** (`CoreInstances/FrontendWebServer/src/`) - Vite HMR (instant)
- **Workers** (`BackgroundProcessingInstances/*/src/`) - source is bind-mounted; restart worker containers after code changes

### When to Rebuild

**No rebuild needed:**

- Code changes in `src/` folders
- Template/config file changes

**Rebuild required:**

- Adding packages to `requirements.txt` or `package.json`
- Changing Dockerfiles
- Installing system dependencies

```bash
make rebuild
```

### Database Migrations

```bash
# Run pending migrations
make db-migrate

# Create a new migration
make db-migration

# Reset database (destructive!)
make db-reset
```

---

## Development Tools

Start with additional dev tools (pgAdmin). For optional malware scanning, use the `security` profile.

```bash
# Start with dev tools profile
make up-dev

# Or manually:
docker compose --profile dev-tools up -d

# Optional: include ClamAV security service
docker compose --profile security up -d
```

---

## Verification

Run the full project verification stack from the repo root:

```bash
make verify-project
```

That target runs the frontend build, full API pytest suite, HTTPS gates, worker
queue tests, and the supported browser audit. Live auth/mail checks reset the
development admin password, so they are explicitly reported as `SKIP` unless
you use an isolated development database and run
`RUNTIME_AUTH_ALLOW_MUTATION=1 make verify-project`. The summary is written to
`verification/results/project-verification-*.md`.

Browser-only coverage is intentionally limited to the supported scope in
`e2e/browser-audit-scope.mjs`. The non-browser replacements and the remaining
manual-only checks are documented in `docs/PROJECT_VERIFICATION.md`.

---

## Testing Email Intake

The Email Intake Worker polls an IMAP inbox for certificate submissions. Use Greenmail for local testing.

### 1. Start Email Services

```bash
# Start the base stack
make up

# Start only services required for intake testing (includes security + email-intake profiles)
docker compose --profile security --profile email-intake up -d postgres redis minio greenmail clamav email-intake-worker
```

### 2. Send a Test Email

```bash
python3 << 'EOF'
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

msg = MIMEMultipart()
msg['To'] = 'certs@ci.laredo.tx.us'
msg['From'] = 'employee@ci.laredo.tx.us'
msg['Subject'] = 'Certificate Submission - Test'
msg.attach(MIMEText('Please process my attached certificate.'))

# Optionally attach a PDF file:
# with open('certificate.pdf', 'rb') as f:
#     attachment = MIMEBase('application', 'pdf')
#     attachment.set_payload(f.read())
#     encoders.encode_base64(attachment)
#     attachment.add_header('Content-Disposition', 'attachment', filename='certificate.pdf')
#     msg.attach(attachment)

with smtplib.SMTP('localhost', 3025) as smtp:
    smtp.send_message(msg)
print('Email sent!')
EOF
```

### 3. Monitor the Worker

```bash
docker compose logs -f email-intake-worker
```

The worker will:

1. Poll the IMAP inbox every 60 seconds
2. Validate sender domain against `ALLOWED_EMAIL_DOMAIN`
3. Malware-scan attachments via ClamAV (fail-closed by default)
4. Process attachments and create document records
5. Move processed emails to the "Processed" folder

---

## Running Tests

```bash
# Run all tests
make test

# Run tests with coverage
make test-cov

# Run strict worker queue gate in Docker (authoritative)
make test-worker-queues-docker

# Run strict worker queue checks on host (optional preflight)
make test-worker-queues-host

# Run linter
make lint

# Fix linting issues
make lint-fix
```

---

## Common Tasks

```bash
# Start/Stop
make up              # Start all services
make up-dev          # Start with dev tools (pgadmin)
make down            # Stop all services
make down-v          # Stop and remove volumes (data loss!)
make restart         # Restart all services
make rebuild         # Rebuild and restart

# Logs
make logs            # Follow all logs
make logs-api        # Follow API logs
make logs-frontend   # Follow frontend logs
make logs-workers    # Follow worker logs

# Shell Access
make shell-api       # Bash shell in API container
make shell-frontend  # Shell in frontend container
make shell-db        # PostgreSQL CLI
make shell-redis     # Redis CLI

# Database
make db-migrate      # Run migrations
make db-migration    # Create new migration
make db-reset        # Reset database (destructive!)

# Status
make status          # Show container status
make health          # Check API health
```

---

## Project Structure

```text
CityOfLaredoProject/
├── CoreInstances/
│   ├── ApiServer/                    # FastAPI backend
│   │   ├── src/                      # Application source code
│   │   │   ├── routes/               # API endpoints
│   │   │   ├── auth/                 # Authentication module
│   │   │   └── shared/               # Shared models & utilities
│   │   ├── alembic/                  # Database migrations
│   │   └── requirements.txt          # Python dependencies
│   └── FrontendWebServer/            # React frontend
│       ├── src/                      # React source code
│       │   ├── pages/                # Page components
│       │   ├── components/           # Reusable components
│       │   └── api/                  # API client
│       └── package.json              # Node dependencies
│
├── BackgroundProcessingInstances/
│   ├── ExtractionWorker/             # Document extraction pipeline
│   ├── EmailIntakeWorker/            # IMAP email polling
│   ├── OcrEngine/                    # Tesseract OCR service
│   └── SchedulerNotificationWorker/  # Scheduled notifications
│
├── docker/                           # Dockerfiles and infrastructure config
│   ├── api/                          # API Dockerfiles (prod & dev)
│   ├── frontend/                     # Frontend Dockerfiles + nginx
│   ├── postgres/                     # pg_hba.conf + TLS entrypoint wrapper
│   ├── tls/                          # generate_certs.sh + generated certs (git-ignored)
│   └── workers/                      # Worker Dockerfiles
│
├── docker-compose.yml                # Container orchestration
├── .env.example                      # Environment template
├── Makefile                          # Developer commands
├── DOCKER.md                         # Detailed Docker guide
└── README.md                         # This file
```

---

## Environment Variables

Key variables in `.env`:

```bash
# Database
POSTGRES_USER=laredo
POSTGRES_PASSWORD=laredo_dev_password
POSTGRES_DB=laredo_certificates

# Object Storage
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=<set-a-strong-password>

# API
SECRET_KEY=REPLACE_ME_generate_with_openssl_rand_hex_32

# mTLS (all paths are container-internal after running generate_certs.sh)
TLS_ENABLED=true
TLS_CA_CERT=/tls/ca.crt
TLS_CLIENT_CERT=/tls/client.crt
TLS_CLIENT_KEY=/tls/client.key

# Email (Development)
IMAP_HOST=greenmail
IMAP_PORT=3143
IMAP_USER=certs@ci.laredo.tx.us
IMAP_PASSWORD=any
ALLOWED_EMAIL_DOMAIN=ci.laredo.tx.us
```

See `.env.example` for all available options.

---

## Troubleshooting

For detailed Docker troubleshooting, see [DOCKER.md](DOCKER.md).

### Quick Fixes

**Containers not starting:**

```bash
docker compose ps          # Check status
docker compose logs api    # Check logs for errors
```

**Database connection failed:**

```bash
# Wait for PostgreSQL to be healthy
docker compose ps postgres
# Should show "healthy" status
```

**Port already in use:**

```bash
# Change the port in .env
API_PORT=8001
```

**Certificates missing (container won't start):**

```bash
bash docker/tls/generate_certs.sh
docker compose up -d
```

**Redis connection refused on port 6379:**

Plain-text Redis is disabled. Ensure `REDIS_URL=rediss://redis:6380/0` in your `.env`.

**Reset everything:**

```bash
make clean                 # Remove all containers and volumes
make setup                 # Fresh start
bash docker/tls/generate_certs.sh  # Regenerate certs after clean
```

### Trusting the Caddy Root CA (optional)

Caddy uses an internal CA for `*.localhost` TLS. To eliminate browser certificate warnings:

```bash
# Extract the CA certificate from the Caddy container
docker cp laredo-caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-dev-root.crt

# Linux (Debian/Ubuntu):
sudo cp caddy-dev-root.crt /usr/local/share/ca-certificates/caddy-dev.crt
sudo update-ca-certificates

# macOS:
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain caddy-dev-root.crt

# Then import into your browser or restart it.
```

---

## API Documentation

Interactive API documentation is available at:

- **API Health:** <https://api.localhost/health>
- **Swagger UI (debug only):** <https://api.localhost/docs>
- **ReDoc:** <https://api.localhost/redoc>

### Authentication

1. Login via `POST /auth/login` with email and password
2. Use the returned `access_token` in the `Authorization: Bearer <token>` header
3. Default auth timing (configurable via env):
   - Access token: 15 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`)
   - Refresh token: 7 days (`REFRESH_TOKEN_EXPIRE_DAYS`)
   - Session max: 8 hours (`SESSION_MAX_HOURS`)

---

## Directory Overview

Developer-facing documentation for this directory:

- `docs/README.md` - Root quick start, conventions, and assumptions
- `docs/DIRECTORY_MAP.md` - Structure map and editing hotspots
- `docs/OPERATIONS.md` - Setup/run/test/lint/build/release operations
- `docs/ARCHITECTURE.md` - Components, data flow, and extension points

Browser wiki (single-file HTML):

```bash
make wiki
# then open wiki/index.html in your browser
```

---

## Additional Resources

- [DOCKER.md](DOCKER.md) - Comprehensive Docker setup and troubleshooting
- [HighLevelDesignSpecification.md](HighLevelDesignSpecification.md) - System architecture and design

---

## License

Copyright (c) 2026 Cash Bailey. All rights reserved. See [LICENSE](LICENSE).
