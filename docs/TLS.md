# mTLS Service Mesh

All east-west connections inside the Docker Compose stack — from the API server and every background worker to PostgreSQL, Redis, and MinIO — are encrypted and mutually authenticated using TLS certificates signed by a project-internal Certificate Authority (CA).

The browser-facing API HTTP server itself stays plain HTTP (port 8000); TLS is applied to **internal service-to-service traffic only**.

**Known exception:** Ollama has no native TLS support and runs on the isolated internal Docker network without encryption. This is documented in the High-Level Design Specification (MESH-06).

---

## Certificate Structure

```
docker/tls/
├── generate_certs.sh            ← Run once to produce everything below
├── .gitignore                   ← Ignores ca.key and certs/ (never commit keys)
├── ca.crt                       ← CA cert — mounted read-only into every container
├── ca.key                       ← CA private key — stays on host, NEVER mounted
└── certs/
    ├── postgres/                ← server.crt  server.key  ca.crt
    ├── redis/                   ← server.crt  server.key  ca.crt  client.crt  client.key
    ├── minio/                   ← public.crt  private.key  ca.crt
    ├── api-client/              ← client.crt  client.key  ca.crt
    ├── extraction-worker-client/
    ├── ocr-worker-client/
    ├── scheduler-worker-client/
    └── email-intake-worker-client/
```

Each service container gets its own client certificate. The `redis/` directory additionally holds a copy of the `api-client` cert so the Redis container can present a valid client cert during its own healthcheck.

---

## Quick Start

```bash
# 1. Generate all certificates (one-time setup)
bash docker/tls/generate_certs.sh

# 2. Start the stack
docker compose up --build
```

The `docker/tls/certs/` directory is git-ignored. It lives only on the machine that runs the stack. If you delete it (e.g. to rotate certificates), re-run step 1 and then restart all containers.

---

## Certificate Details

| Type | Key Size | Validity | Details |
|------|----------|----------|---------|
| CA | RSA 4096-bit | 10 years | Self-signed; `CN=Laredo Internal CA` |
| Server certs | RSA 2048-bit | 1 year | Signed by CA; include DNS SANs (`postgres,localhost` etc.) |
| Client certs | RSA 2048-bit | 1 year | Signed by CA; `CN=<service-name>` |

Server certificates carry Subject Alternative Names (SANs) so that clients verifying the hostname find a match for both the Docker service name and `localhost`. Client certificates identify each service by Common Name (e.g. `CN=extraction-worker`).

---

## How It Works per Service

### PostgreSQL

PostgreSQL is configured with `-c ssl=on` and a custom `pg_hba.conf` that requires TLS + a valid client certificate for all non-loopback connections:

```
local   all  all  trust                             ← Unix socket (docker healthcheck)
host    all  all  127.0.0.1/32  scram-sha-256       ← IPv4 loopback (pgAdmin)
hostssl all  all  0.0.0.0/0    scram-sha-256  clientcert=verify-ca  ← All TCP (enforced mTLS)
```

A wrapper entrypoint (`docker/postgres/entrypoint.sh`) runs as root before starting Postgres so it can `chown 70:70` the server key — PostgreSQL refuses to start when the key is not owned by its own user.

### Redis

The plain-text port (6379) is **disabled**. Redis listens only on TLS port **6380** with `--tls-auth-clients yes`. Clients must use `rediss://redis:6380/0` (double-s scheme signals TLS to `redis-py`).

### MinIO

MinIO auto-enables HTTPS when `MINIO_CERTS_DIR=/certs` and the directory contains `public.crt` + `private.key`. Port 9000 becomes HTTPS automatically. The `minio-init` setup container uses `--insecure` since it connects before the CA cert is in its trust store.

### API and Workers

Each service mounts its client cert directory at `/tls/` inside the container and gets four environment variables:

| Variable | Default (container path) |
|---|---|
| `TLS_ENABLED` | `true` |
| `TLS_CA_CERT` | `/tls/ca.crt` |
| `TLS_CLIENT_CERT` | `/tls/client.crt` |
| `TLS_CLIENT_KEY` | `/tls/client.key` |

The shared helper `CoreInstances/ApiServer/src/shared/tls.py` reads these vars and provides:

- `build_ssl_context()` → returns an `ssl.SSLContext` for asyncpg (PostgreSQL) and urllib3 (MinIO), or `None` when TLS is disabled
- `redis_tls_kwargs()` → returns a dict of `ssl_*` kwargs for `redis.from_url()`, or `{}` when TLS is disabled

---

## Disabling mTLS

For local debugging without certificates, set in `.env`:

```
TLS_ENABLED=false
```

This causes all TLS helpers to return `None` / `{}`, falling back to plain TCP. You will also need to restore plain-text Redis by changing `REDIS_URL` to `redis://redis:6379/0` and re-enabling port 6379 in the redis command.

> **Note:** With mTLS disabled, service-to-service traffic is unencrypted. Only use this for local debugging, never in staging or production.

---

## Renewing Certificates

Leaf certificates expire after 1 year. To rotate them:

```bash
# 1. Remove existing certs (keeps the directory structure)
rm -rf docker/tls/certs docker/tls/ca.crt docker/tls/ca.key

# 2. Generate fresh certs
bash docker/tls/generate_certs.sh

# 3. Restart all containers so they pick up the new certs
docker compose restart
```

---

## Hostname Verification

Hostname verification (`check_hostname`) is **disabled** in
`CoreInstances/ApiServer/src/shared/tls.py` for all east-west connections
(lines 47 and 73).

**Current design:** The inline comment states that Docker container names are not
FQDNs. However, the Certificate Details table above documents that server certificates
include DNS SANs covering the Docker service names (e.g. `postgres`, `localhost`). If
those SANs are actually present in the generated certificates, hostname verification
could be re-enabled without breakage.

**Before re-enabling `check_hostname`:**
1. Confirm that `docker/tls/generate_certs.sh` includes each service name as a DNS SAN
   in the corresponding server certificate.
2. Test that `build_ssl_context()` with `check_hostname=True` connects cleanly to
   PostgreSQL and MinIO from the API container.
3. Test that `redis_tls_kwargs()` with `ssl_check_hostname=True` connects cleanly to
   Redis from every worker container.
4. Remove the `check_hostname=False` and `ssl_check_hostname=False` lines from
   `shared/tls.py`.

**Compensating control (current state):** Mutual TLS still authenticates each peer
by certificate chain. Every service must present a valid client certificate signed by
the project CA. An unknown process cannot connect even without hostname verification
because it cannot produce a CA-signed certificate.

---

## Verification

After `docker compose up`, confirm mTLS is active:

```bash
# PostgreSQL — ssl column should be 't' for all connections
docker exec laredo-postgres psql -U laredo -c "SELECT ssl, client_addr FROM pg_stat_ssl LIMIT 5;"

# Redis — should return PONG using TLS client cert
docker exec laredo-redis redis-cli --tls \
  --cert /tls/client.crt --key /tls/client.key --cacert /tls/ca.crt \
  -p 6380 ping

# Redis plain port must be refused
docker exec laredo-redis redis-cli -p 6379 ping  # should fail

# MinIO — HTTPS health check (--insecure because self-signed)
curl -sf --insecure https://localhost:9000/minio/health/live && echo "MinIO OK"
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container exits: `No such file: /tls/ca.crt` | Certs not generated | Run `bash docker/tls/generate_certs.sh` |
| Postgres fails to start with `SSL error` | Key file not owned by postgres uid | Check `docker logs laredo-postgres`; re-run generate_certs.sh and restart |
| `redis.exceptions.ConnectionError` on port 6379 | Plain port disabled | Update `REDIS_URL` to `rediss://redis:6380/0` |
| MinIO returns HTTP 307 redirect | Client using HTTP not HTTPS | Set `MINIO_SECURE=true` and verify `MINIO_CERTS_DIR=/certs` is set |
| `ssl.SSLCertVerificationError` | Wrong CA cert path or expired cert | Verify `TLS_CA_CERT=/tls/ca.crt` and re-run generate_certs.sh if expired |
| `certificate verify failed: hostname mismatch` | Cert hostname check on internal name | Shouldn't occur — `check_hostname=False` is set for Docker service names |
