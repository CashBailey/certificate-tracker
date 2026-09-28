# Email Intake Worker Docs

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## What This Directory Is
This directory contains a Python worker that polls an IMAP inbox, resolves sender identity with GAL-aware rules, validates and malware-scans attachments, stores accepted files in MinIO, writes intake/audit rows to the database, and enqueues extraction work in Redis. PostgreSQL is the default in local compose and in code defaults.  
Evidence: `src/__init__.py:1`, `src/worker.py:70`, `src/email_client.py:40`, `src/directory_lookup.py:34`, `../../docker-compose.yml:331`, `src/malware_scanner.py:21`

## Quick Start
### Recommended: Run via Docker Compose (from repository root)
```bash
docker compose up -d email-intake-worker
docker compose logs -f email-intake-worker
```
- The service is defined in root compose and wired with env vars and dependencies.
- The container command runs `python -m src.worker`.
Evidence: `../../docker-compose.yml:324`, `../../docker-compose.yml:359`, `../../docker/workers/email-intake/Dockerfile:37`

For strict malware scanning with an actual ClamAV service:
```bash
docker compose --profile email-intake up -d clamav email-intake-worker
```
Evidence: `../../docker-compose.yml:349`, `../../docker-compose.yml:376`, `../../docker-compose.yml:396`

### Local Python Run (advanced/debug)
```bash
python -m pip install -r requirements.txt
PYTHONPATH=../../CoreInstances/ApiServer/src python -m src.worker
```
- `PYTHONPATH` is needed because this worker imports `shared.*`, which lives under `CoreInstances/ApiServer/src/shared`.
Evidence: `requirements.txt:1`, `src/worker.py:25`, `src/directory_lookup.py:17`, `../../CoreInstances/ApiServer/src/shared/__init__.py`, `tests/test_directory_lookup.py:20`

### Run Included Unit Tests
```bash
python -m pytest -q tests/test_directory_lookup.py
```
Evidence: `tests/test_directory_lookup.py:1`, `tests/test_directory_lookup.py:19`

If unrelated pytest plugins interfere in your local environment, use:
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_directory_lookup.py
```

## Entrypoints (How To Choose)
| Entrypoint | Use When | How To Start | Evidence |
|---|---|---|---|
| `src.worker:main()` | Normal daemon behavior | `python -m src.worker` or compose service | `src/worker.py:731`, `src/worker.py:746`, `../../docker/workers/email-intake/Dockerfile:37` |
| `EmailIntakeWorker.run()` | Programmatic integration/runtime embedding | Construct via `create_worker_from_env()` then await `run()` | `src/worker.py:636`, `src/worker.py:686` |
| `EmailIntakeWorker.poll_once()` | One-shot poll in tests/debug | Call `poll_once()` from custom harness | `src/worker.py:618` |

## Key Conventions
| Convention | Value / Rule | Evidence |
|---|---|---|
| Extraction queue name | `extraction_tasks` | `src/worker.py:67` |
| Accepted attachment MIME types | `application/pdf`, `image/png`, `image/jpeg`, `image/tiff` | `src/worker.py:55` |
| Max attachment size | 20 MB | `src/worker.py:64` |
| Processed IMAP folder | Configurable (`IMAP_PROCESSED_FOLDER`, default `Processed`) | `src/email_client.py:51`, `src/email_client.py:224` |
| Quarantine IMAP folder | Hardcoded `Quarantine` | `src/email_client.py:209` |
| Incoming message identifier | Uses IMAP UID (`message_id=msg.uid`) | `src/email_client.py:163` |
| Attachment-less emails | Skipped before processing | `src/email_client.py:148` |
| Sender policy | Non-city / not-in-GAL / non-person senders are ignored | `src/directory_lookup.py:71`, `src/directory_lookup.py:147`, `src/directory_lookup.py:152`, `src/directory_lookup.py:157` |
| Deduplication | Message-level, message+attachment-level, and employee+file-hash-level checks | `src/worker.py:387`, `src/worker.py:397`, `src/worker.py:127` |
| Malware scan failure behavior | Default fail-closed (`CLAMAV_FAIL_OPEN=false`); startup fails fast if scanner is required but unreachable | `src/malware_scanner.py:50`, `src/malware_scanner.py:166` |

## Where To Look Next
- Architecture: [`./ARCHITECTURE.md`](./ARCHITECTURE.md)
- Directory structure: [`./DIRECTORY_MAP.md`](./DIRECTORY_MAP.md)
- Operations and runbook: [`./OPERATIONS.md`](./OPERATIONS.md)

## Assumptions And Unknowns
- Assumption: external infrastructure (PostgreSQL, Redis, MinIO, IMAP, optional ClamAV) is reachable via env-configured endpoints.  
  Evidence: `src/directory_lookup.py:34`, `src/email_client.py:224`, `src/worker.py:686`, `src/malware_scanner.py:142`
- Known mismatch to watch: code default `ALLOWED_EMAIL_DOMAIN=laredotx.gov`, compose default `ci.laredo.tx.us`.  
  Evidence: `src/directory_lookup.py:188`, `../../docker-compose.yml:345`
- Known mismatch to watch: code default `IMAP_USE_SSL=true`, compose default `false`.  
  Evidence: `src/email_client.py:231`, `../../docker-compose.yml:342`
- Unknown: directory-local lint/format command is not defined in this directory scope. Evidence: local file inventory, `requirements.txt`, `../../Makefile:206`.
- Verification details for commands in this environment are recorded in [`./OPERATIONS.md`](./OPERATIONS.md) ("Verification Snapshot").
