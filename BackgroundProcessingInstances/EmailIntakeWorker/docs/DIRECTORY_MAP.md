# Directory Map

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Rendered Tree
```text
.
├── README.md
├── docs
│   ├── ARCHITECTURE.md
│   ├── DIRECTORY_MAP.md
│   ├── OPERATIONS.md
│   └── README.md
├── requirements.txt
├── src
│   ├── __init__.py
│   ├── directory_lookup.py
│   ├── email_client.py
│   ├── gal_provider.py
│   ├── malware_scanner.py
│   └── worker.py
└── tests
    ├── __init__.py
    └── test_directory_lookup.py
```
Notes:
- Noise omitted: `__pycache__/`, `.pytest_cache/`.
Evidence: paths listed in the rendered tree above

## Top-Level Anchors
| Anchor | Status | Evidence |
|---|---|---|
| `README.md` | Present | `README.md` |
| `docs/` | Present | `docs/README.md` |
| `requirements.txt` | Present | `requirements.txt` |
| `src/` | Present | `src/worker.py` |
| `tests/` | Present | `tests/test_directory_lookup.py` |
| Root-level worker orchestration references | Present outside this directory | `../../docker-compose.yml`, `../../docker/workers/email-intake/Dockerfile` |

## Path Purpose Table
| Path | Purpose | Key Files Inside | Notes |
|---|---|---|---|
| `requirements.txt` | Python dependency manifest | `requirements.txt` | Includes IMAP, SQLAlchemy, Redis, MinIO, python-magic, dotenv dependencies. Evidence: `requirements.txt:1` |
| `src/` | Runtime implementation | `worker.py`, `email_client.py`, `directory_lookup.py`, `gal_provider.py`, `malware_scanner.py` | Primary module entrypoint is `src.worker`. Evidence: `src/worker.py:731` |
| `tests/` | Unit tests | `test_directory_lookup.py` | Focused on GAL-aware directory lookup behavior. Evidence: `tests/test_directory_lookup.py:1` |
| `docs/` | Directory-local developer docs | `README.md`, `OPERATIONS.md`, `ARCHITECTURE.md` | Human-facing runbook and architecture references. |

## Interface / Contract Files
| Path | Contract Surface | Evidence |
|---|---|---|
| `src/gal_provider.py` | `GALProvider` protocol (`is_person`, `get_person_info`, `is_in_gal`) and `PersonInfo` model | `src/gal_provider.py:28`, `src/gal_provider.py:19` |
| `src/email_client.py` | `IncomingEmail` and `EmailAttachment` transport data objects | `src/email_client.py:20`, `src/email_client.py:29` |
| `src/worker.py` | Redis extraction payload shape (`document_id`, `queued_at`, `source`) | `src/worker.py:322` |
| `src/worker.py` | Allowed MIME types and max attachment size contract | `src/worker.py:55`, `src/worker.py:64` |
| `src/directory_lookup.py` | Sender decision tree (ignore/resolve/auto-create) | `src/directory_lookup.py:67`, `src/directory_lookup.py:133` |

## Hotspots
- `src/worker.py`: central orchestration (poll loop, dedupe, storage, queueing, audit updates, IMAP status transitions).  
  Evidence: `src/worker.py:460`, `src/worker.py:618`, `src/worker.py:636`
- `src/directory_lookup.py`: policy-heavy sender resolution and auto-create logic.  
  Evidence: `src/directory_lookup.py:71`, `src/directory_lookup.py:166`
- `src/email_client.py`: operationally sensitive IMAP state transitions (`Processed`/`Quarantine`).  
  Evidence: `src/email_client.py:175`, `src/email_client.py:197`
