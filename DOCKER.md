# Docker Setup Guide - City of Laredo Certificate Management System

This guide will help you set up and run the entire application using Docker.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Initial Setup](#initial-setup)
- [Building and Running](#building-and-running)
- [Accessing Services](#accessing-services)
- [Development Workflow](#development-workflow)
- [Common Commands](#common-commands)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### 1. Install Docker Desktop

**Windows:**

1. Download Docker Desktop from [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
2. Run the installer
3. Restart your computer when prompted
4. Open Docker Desktop and wait for it to start (Docker icon in system tray will be green)

**Mac:**

1. Download Docker Desktop for Mac
2. Drag Docker.app to Applications folder
3. Open Docker from Applications
4. Follow the setup wizard

**Linux:**

1. Follow instructions at [https://docs.docker.com/engine/install/](https://docs.docker.com/engine/install/)

### 2. Enable WSL2 Integration (Windows Only)

If you're using WSL2 (Windows Subsystem for Linux):

1. Open Docker Desktop
2. Go to **Settings** → **Resources** → **WSL Integration**
3. Enable integration with your WSL2 distro (e.g., Ubuntu)
4. Click **Apply & Restart**

### 3. Verify Installation

Open your terminal (or WSL2) and run:

```bash
docker --version
docker compose version
```

You should see version numbers (e.g., Docker version 24.0.7).

### 4. Verify OpenSSL

The stack uses mutual TLS for all internal service connections. Certificate generation requires `openssl`:

```bash
openssl version
# Expected: OpenSSL 1.1.1 or newer (pre-installed on macOS and most Linux distros)
# Windows: available via Git Bash, WSL2, or https://slproweb.com/products/Win32OpenSSL.html
```

### 4. Create Docker Hub Account (Optional but Recommended)

1. Go to [https://hub.docker.com](https://hub.docker.com)
2. Sign up for a free account
3. In your terminal, login:

   ```bash
   docker login
   ```

   Enter your Docker Hub username and password.

---

## Initial Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd CityOfLaredoProject
```

### 2. Create Environment File

Copy the example environment file and customize it:

```bash
cp .env.example .env
```

**Important:** Edit `.env` and change the default passwords:

```bash
# Open in your text editor
nano .env
# or
vim .env
# or
code .env  # if using VS Code
```

Change at minimum:

- `POSTGRES_PASSWORD` - Database password
- `MINIO_ROOT_PASSWORD` - Object storage password
- `PGADMIN_PASSWORD` - pgAdmin password (required by compose parsing)
- `SECRET_KEY` - API secret key

### 3. Generate TLS Certificates

All internal service connections (API/workers → PostgreSQL, Redis, MinIO) use mutual TLS. Run this **once** before the first `docker compose up`:

```bash
bash docker/tls/generate_certs.sh
```

This creates a self-signed Certificate Authority and per-service client/server certificates under `docker/tls/certs/` (git-ignored). The script takes a few seconds and produces output like:

```text
Generating CA key and certificate...
  CA cert: docker/tls/ca.crt
Generating server cert for postgres...
Generating server cert for redis...
Generating server cert for minio...
Generating client cert for api-client...
...
All certificates generated successfully.
```

**To disable mTLS for local debugging** (not recommended):

```bash
# In .env, set:
TLS_ENABLED=false
```

**To rotate certificates** (e.g. after expiry):

```bash
rm -rf docker/tls/certs docker/tls/ca.crt docker/tls/ca.key
bash docker/tls/generate_certs.sh
docker compose restart
```

See [docs/TLS.md](docs/TLS.md) for the full mTLS reference.

### 4. Verify Files

Make sure you have these key files:

```bash
ls -la
```

You should see:

- `docker-compose.yml` - Container orchestration
- `.env` - Environment variables
- `Makefile` - Helper commands
- `docker/` - Dockerfiles and infrastructure config
- `docker/tls/certs/` - Generated TLS certificates (after step 3)

---

## Building and Running

### Method 1: Using Makefile (Recommended)

The Makefile provides convenient shortcuts:

```bash
# First time setup - copies .env and builds images
make setup

# Start all containers
make up

# View logs
make logs
```

### Method 2: Using Docker Compose Directly

```bash
# Ensure the shared external network exists
docker network create laredo-network 2>/dev/null || true

# Build all images (first time or after code changes)
docker compose build

# Start all containers in background
docker compose up -d

# View logs
docker compose logs -f
```

---

## Building Process Explained

### What Happens When You Build?

1. **Downloads base images** (Python, Node.js, PostgreSQL, Redis, MinIO)
2. **Installs dependencies** for each service
3. **Copies application code** into containers
4. **Creates container images** ready to run

**First build takes 5-10 minutes** (downloads ~3GB of images). Subsequent builds are much faster due to caching.

### Build Progress

You'll see output like:

```text
[+] Building 234.5s (45/45) FINISHED
 => [api 1/5] FROM docker.io/library/python:3.12-slim
 => [api 2/5] RUN apt-get update && apt-get install...
 => [api 3/5] COPY requirements.txt
 => [api 4/5] RUN pip install -r requirements.txt
 => [api 5/5] COPY src/
```

This is normal - Docker is installing all dependencies.

---

## Accessing Services

Once containers are running (`docker compose ps` shows "Up" status):

| Service | URL | Credentials |
| --- | --- | --- |
| **Application** | [https://localhost](https://localhost) | Accept self-signed cert warning |
| **API** | [https://localhost/api/](https://localhost/api/) | N/A |
| **API Documentation** | [https://api.localhost/docs](https://api.localhost/docs) | Interactive Swagger UI |
| **pgAdmin** | [https://pgadmin.localhost](https://pgadmin.localhost) | from `.env` credentials |
| **MinIO Console** | [https://minio.localhost](https://minio.localhost) | User: `minioadmin`; Pass: from `.env` `MINIO_ROOT_PASSWORD` |
| **PostgreSQL** | Internal only (no host port) | Use `make shell-db` |
| **Redis** | Internal only (no host port) | Use `make shell-redis` |

### Verify Services Are Running

```bash
# Check container status
docker compose ps

# Test via Caddy (HTTPS -- accept self-signed cert with -k)
curl -k https://localhost/api/health

# Test API health (direct, dev only)
curl http://127.0.0.1:8000/health

# Test frontend (direct, dev only -- should return HTML)
curl http://127.0.0.1:3000
```

---

## Development Workflow

### Hot Reloading (Code Changes Auto-Apply)

Your code folders are mounted into containers, so changes are reflected immediately:

#### Backend (FastAPI)

1. Edit files in `CoreInstances/ApiServer/src/`
2. Save the file
3. API container automatically restarts (takes ~2 seconds)
4. Refresh [https://api.localhost/docs](https://api.localhost/docs) to see changes

#### Frontend (React)

1. Edit files in `CoreInstances/FrontendWebServer/src/`
2. Save the file
3. Browser automatically reloads via Vite HMR
4. Changes appear instantly

#### Workers

1. Edit files in `BackgroundProcessingInstances/*/src/`
2. Save the file
3. Worker container automatically restarts

### Direct Container Access (Debugging Only)

Host ports have been removed from all services. To access a service directly for debugging, use `docker compose exec`:

```bash
# API shell
make shell-api

# Test an API endpoint from inside the container
docker compose exec api curl http://localhost:8000/health

# Frontend shell
make shell-frontend
```

If you need temporary direct host access for a specific debugging session, create a `docker-compose.override.yml` (git-ignored) with the ports you need. **Do not commit this file.**

### When to Rebuild

You **DON'T** need to rebuild for:

- ✓ Code changes in `src/` folders
- ✓ Changes to existing files

You **DO** need to rebuild when you:

- ✗ Add new Python packages to `requirements.txt`
- ✗ Add new npm packages to `package.json`
- ✗ Change Dockerfiles
- ✗ Change system dependencies

**Rebuild command:**

```bash
make rebuild
# or
docker compose down && docker compose build && docker compose up -d
```

---

## Common Commands

### Starting and Stopping

```bash
# Start all services
make up
# or: docker compose up -d

# Start with logs visible
make up-logs
# or: docker compose up

# Start only specific services
docker compose up -d postgres redis api

# Stop all services
make down
# or: docker compose down

# Stop and remove all data (WARNING: deletes database!)
make down-v
# or: docker compose down -v

# Restart services
make restart
# or: docker compose restart
```

### Viewing Logs

```bash
# All services
make logs
# or: docker compose logs -f

# Specific service
make logs-api
# or: docker compose logs -f api

# Last 100 lines
docker compose logs --tail=100 api

# Since specific time
docker compose logs --since 10m api
```

### Accessing Containers

```bash
# Open bash shell in API container
make shell-api
# or: docker compose exec api /bin/bash

# Open shell in frontend container
make shell-frontend
# or: docker compose exec frontend /bin/sh

# Open PostgreSQL CLI
make shell-db
# or: docker compose exec postgres psql -U laredo -d laredo_certificates

# Open Redis CLI (TLS-aware)
make shell-redis
# or: docker compose exec redis redis-cli --tls \
#       --cert /tls/client.crt --key /tls/client.key --cacert /tls/ca.crt -p 6380

# Run one-off command
docker compose exec api python -c "print('Hello from container')"
```

### Database Operations

```bash
# Run database migrations
make db-migrate
# or: docker compose exec api alembic upgrade head

# Create new migration
make db-migration
# or: docker compose exec api alembic revision --autogenerate -m "description"

# Reset database (WARNING: deletes all data!)
make db-reset
```

### Viewing Container Status

```bash
# List running containers
docker compose ps

# Show resource usage
docker stats

# Show container details
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```

---

## Troubleshooting

### Problem: "Cannot connect to Docker daemon"

**Solution:**

1. Make sure Docker Desktop is running (check system tray icon)
2. On Windows with WSL2, ensure WSL integration is enabled in Docker Desktop settings

### Problem: "Port already in use"

```text
Error: bind: address already in use
```

**Solution:**

```bash
# Find what's using the port (example: port 8000)
lsof -i :8000
# or on Windows
netstat -ano | findstr :8000

# Kill the process or change the port in .env
# Edit .env and change:
API_PORT=8001
```

### Problem: "No space left on device"

**Solution:**

```bash
# Clean up unused Docker resources
make clean
# or
docker system prune -a

# Remove unused volumes
docker volume prune
```

### Problem: Build fails with "unauthorized" error

**Solution:**

```bash
# Login to Docker Hub
docker login

# If behind corporate proxy, configure Docker proxy settings
```

### Problem: Container keeps restarting

```bash
# Check logs to see error
docker compose logs api

# Common issues:
# - Database not ready yet (wait 30 seconds and check again)
# - Environment variable missing (check .env file)
# - Port conflict (change port in .env)
```

### Problem: "Permission denied" errors in WSL2

**Solution:**

```bash
# Fix file permissions
sudo chown -R $USER:$USER .

# Add your user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### Problem: Changes not appearing

**For Backend:**

```bash
# Restart API container
docker compose restart api

# Check logs for errors
docker compose logs api
```

**For Frontend:**

```bash
# Clear node_modules and reinstall
docker compose down
docker volume rm laredo-frontend-cache
docker compose up -d --build frontend
```

### Problem: TLS / Certificate Errors

| Symptom | Fix |
|---------|-----|
| `No such file or directory: '/tls/ca.crt'` | Run `bash docker/tls/generate_certs.sh` |
| Postgres container exits immediately after `SSL SYSCALL error` | Re-run `generate_certs.sh`; the entrypoint wrapper fixes key ownership |
| `redis.exceptions.ConnectionError` on port 6379 | Plain-text port is disabled; check `REDIS_URL=rediss://redis:6380/0` in `.env` |
| MinIO returns HTTP 307 redirect loop | Client must use HTTPS; verify `MINIO_SECURE=true` in `.env` |
| `ssl.SSLCertVerificationError` in worker logs | Cert path mismatch; verify `TLS_CA_CERT=/tls/ca.crt` and that certs were generated |

```bash
# Quick TLS verification
docker exec laredo-postgres psql -U laredo -c "SELECT ssl FROM pg_stat_ssl LIMIT 3;"
docker exec laredo-redis redis-cli --tls \
  --cert /tls/client.crt --key /tls/client.key --cacert /tls/ca.crt -p 6380 ping
```

### Problem: Database connection failed

**Solution:**

```bash
# Check if PostgreSQL is healthy
docker compose ps postgres

# Should show: "Up X seconds (healthy)"
# If not healthy, check logs:
docker compose logs postgres

# Verify database exists
docker compose exec postgres psql -U laredo -l
```

---

## Understanding the Container Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│                      Docker Environment                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Browser ──HTTPS:443──▶ ┌──────────────┐                         │
│  Browser ──HTTP:80────▶ │    Caddy     │ (TLS termination)       │
│                         │  Port 80/443 │                         │
│                         └──────┬───────┘                         │
│                          /api/*│     │ /*                         │
│                    ┌───────────┘     └───────────┐               │
│                    ▼                             ▼               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   Frontend   │  │     API      │  │   Workers    │           │
│  │   (React)    │─▶│  (FastAPI)  │◀─│  (Python)    │           │
│  │ 127.0.0.1:   │  │ 127.0.0.1:  │  │              │           │
│  │   3000       │  │   8000      │  │              │           │
│  └──────────────┘  └──────┬───────┘  └──────┬───────┘           │
│                           │                  │                  │
│                           ▼                  ▼                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  PostgreSQL  │  │    Redis     │  │    MinIO     │           │
│  │  Port 5432   │  │  Port 6380   │  │  Port 9000   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
         ▲                                         ▲
         │                                         │
    Your Code                                 Persistent
    (mounted as                               Data Volumes
     volumes)
```

**Containers (9 total):**

1. `laredo-caddy` - TLS termination reverse proxy (HTTPS entry point)
2. `laredo-postgres` - Database
3. `laredo-redis` - Cache & task queue
4. `laredo-minio` - File storage (S3-compatible)
5. `laredo-api` - FastAPI backend
6. `laredo-frontend` - React UI
7. `laredo-extraction-worker` - PDF processing
8. `laredo-ocr-engine` - Tesseract OCR
9. `laredo-scheduler-worker` - Scheduled tasks & notifications

---

## Environment Variables Reference

Key variables in `.env`:

```bash
# Database
POSTGRES_USER=laredo
POSTGRES_PASSWORD=change_me_in_production
POSTGRES_DB=laredo_certificates

# Object Storage
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=change_me_in_production
MINIO_BIND_HOST=127.0.0.1

# API
SECRET_KEY=change_me_in_production
DEBUG=true  # Set to false in production
LOG_LEVEL=DEBUG  # Use INFO or WARNING in production

# Ports (change if conflicts)
API_PORT=8000
FRONTEND_PORT=3000
POSTGRES_PORT=5432
REDIS_PORT=6380

# Malware scanning (email intake)
CLAMAV_ENABLED=true
CLAMAV_FAIL_OPEN=false

# Optional tooling
PGADMIN_PASSWORD=change_me_in_production
PGADMIN_BIND_HOST=127.0.0.1

# mTLS (container-internal paths; generated by docker/tls/generate_certs.sh)
TLS_ENABLED=true
TLS_CA_CERT=/tls/ca.crt
TLS_CLIENT_CERT=/tls/client.crt
TLS_CLIENT_KEY=/tls/client.key
```

---

## Production Deployment Notes

**⚠️ This setup is for DEVELOPMENT only.**

For production:

1. **Use production Docker Compose:**

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

2. **Change passwords** in `.env`

3. **Disable debug mode:**

   ```bash
   DEBUG=false
   LOG_LEVEL=INFO
   ```

4. **Use orchestration** (Kubernetes, Docker Swarm, or AWS ECS)

5. **Configure TLS** -- Caddy is included as the TLS termination proxy. Set
   `PUBLIC_HOSTNAME` and `TLS_CERT`/`TLS_KEY` in `.env` for production certs

6. **Use managed services** for:

   - PostgreSQL (AWS RDS, Azure Database)
   - Redis (AWS ElastiCache, Azure Cache)
   - Object Storage (AWS S3, Azure Blob)

---

## Getting Help

### Check Container Logs

```bash
# All services
docker compose logs -f

# Specific service with timestamps
docker compose logs -f --timestamps api
```

### Restart Everything Fresh

```bash
# Nuclear option - removes everything
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

### Verify Health

```bash
# Check if containers are running
docker compose ps

# Check API health
curl -k https://localhost/api/health

# Check if database is accessible
docker compose exec postgres pg_isready -U laredo
```

---

## Quick Reference Cheat Sheet

```bash
# Start everything
make up

# Stop everything
make down

# View logs
make logs

# Rebuild after dependency changes
make rebuild

# Open API shell
make shell-api

# Open database shell
make shell-db

# Run tests
make test

# Clean up everything
make clean
```

---

## Team Collaboration Tips

1. **Never commit `.env`** - it contains secrets
2. **Always commit `.env.example`** - update it when adding new variables
3. **Document port changes** - tell team if you change default ports
4. **Share Makefile updates** - commit helpful commands to Makefile
5. **Test in clean environment** - occasionally run `make clean && make setup` to verify setup works

---

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI in Docker](https://fastapi.tiangolo.com/deployment/docker/)
- [Vite with Docker](https://vitejs.dev/guide/env-and-mode.html)

---

**Questions?** Contact the dev team lead or check the project wiki.
