# Email Intake Worker

## Directory Overview
This directory contains a Python email-intake background worker that polls IMAP, applies GAL-aware sender rules, validates/scans attachments, stores documents, writes intake/audit records, and queues extraction tasks.  
Evidence: `src/__init__.py:1`, `src/worker.py:460`, `src/email_client.py:122`, `src/directory_lookup.py:133`

## Quickstart (Docker, from repository root)
```bash
docker compose --profile email-intake up -d email-intake-worker
docker compose logs -f email-intake-worker
```
Evidence: `../../docker-compose.yml:324`, `../../docker-compose.yml:359`

For strict malware scanning with ClamAV running:
```bash
docker compose --profile email-intake up -d clamav email-intake-worker
```
Evidence: `../../docker-compose.yml:376`, `../../docker-compose.yml:396`

## Quickstart (Local Python, from this directory)
```bash
python -m pip install -r requirements.txt
set -a && source ../../.env && set +a
PYTHONPATH=../../CoreInstances/ApiServer/src python -m src.worker
```
Evidence: `requirements.txt:1`, `src/worker.py:731`, `src/worker.py:746`, `src/worker.py:25`

## Tests
```bash
python -m pytest -q tests/test_directory_lookup.py
```
Evidence: `tests/test_directory_lookup.py:1`, `tests/test_directory_lookup.py:19`

If your local Python environment auto-loads unrelated pytest plugins, use:
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_directory_lookup.py
```

## Detailed Documentation
- `docs/README.md`
- `docs/DIRECTORY_MAP.md`
- `docs/OPERATIONS.md`
- `docs/ARCHITECTURE.md`

For command verification status in this environment, see `docs/OPERATIONS.md` ("Verification Snapshot").
