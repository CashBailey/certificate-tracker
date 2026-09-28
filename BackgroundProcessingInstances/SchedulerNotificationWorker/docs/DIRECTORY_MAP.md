# Directory Map

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Rendered Tree (Depth-Limited)
```text
.
├── README.md
├── requirements.txt
├── src
│   ├── __init__.py
│   ├── notifications.py
│   └── scheduler.py
└── docs
    ├── ARCHITECTURE.md
    ├── DIRECTORY_MAP.md
    ├── OPERATIONS.md
    └── README.md
```
Evidence: local file inventory (`find . -maxdepth 4`, `rg --files`).

## Path Reference Table
| Path | Purpose | Key files inside | Notes (entrypoint/config/data) |
|---|---|---|---|
| `README.md` | Brief, high-level description of worker purpose | `README.md` | Mentions scheduled jobs and notification event generation. Evidence: `README.md`. |
| `requirements.txt` | Python dependency declaration | `requirements.txt` | Includes DB (`sqlalchemy`, `asyncpg`), Redis (`redis`), scheduler (`apscheduler`), email (`aiosmtplib`), logging/config utilities. Evidence: `requirements.txt`. |
| `src/` | Worker runtime and notification-generation logic | `src/scheduler.py`, `src/notifications.py`, `src/__init__.py` | Entrypoint is `src/scheduler.py` via `main()` and `if __name__ == "__main__"`. Daily job + queue job scheduling is defined here. Evidence: `src/scheduler.py`. |
| `docs/` | Developer-facing directory-local documentation | `docs/README.md`, `docs/OPERATIONS.md`, `docs/ARCHITECTURE.md`, `docs/DIRECTORY_MAP.md` | Generated for this directory to capture usage and architecture with evidence references. |

## Interfaces / Contracts In This Directory
- No local OpenAPI/JSON Schema/DB migration contract files were found in this directory.
- This worker depends on shared contracts from outside this directory (`shared.models`, `shared.protocols.Repository`, `shared.repository.SqlRepository`). Evidence: `src/notifications.py`, `src/scheduler.py`.

## External Runtime Anchors (Outside This Directory)
These files are outside the current directory but are required to explain how this worker is built/run:

| Path | Why it matters |
|---|---|
| `../../docker/workers/scheduler/Dockerfile` | Defines worker container image, Python version base image, copy layout (`src` + `shared`), and runtime command (`python -m src.scheduler`). |
| `../../docker-compose.yml` | Defines `scheduler-worker` service, env vars, `shared` volume mount, and dependencies (`postgres`, `redis`). |
| `../../docker-compose.prod.yml` | Defines production `scheduler-worker` image and runtime env surface in production compose. |
| `../../Makefile` | Defines top-level operational commands used in development (`make up`, `make logs-workers`, etc.). |
| `../../CoreInstances/ApiServer/src/shared/email_sender.py` | Defines SMTP environment variables/defaults consumed by scheduler mail delivery path (`shared.email_sender.send_email`). |
| `../../scripts/export-project.sh` | Provides documented manual build/export/push flow for `scheduler-worker` image tags. |
| `../../.github/workflows/ci.yml` | Current CI workflow scope (lint/tests/build-check), useful to determine whether scheduler-worker image publishing is automated. |
| `../../CoreInstances/ApiServer/tests/unit/test_notifications.py` | Documents indirect notification logic tests; explicitly notes duplicated pure logic rather than importing scheduler worker module. |

## Hotspots
- `src/notifications.py`: Notification cadence, dedupe strategy, recipient escalation, and message templates are concentrated here. Evidence: `src/notifications.py`.
- `src/scheduler.py`: Runtime bootstrap, environment handling, scheduled jobs, queue processing, and shutdown loop are concentrated here. Evidence: `src/scheduler.py`.
