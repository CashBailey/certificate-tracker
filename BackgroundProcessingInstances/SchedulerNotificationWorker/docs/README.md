# SchedulerNotificationWorker Docs

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## What This Directory Is
`SchedulerNotificationWorker` is a Python background worker that continuously runs scheduled jobs to create notification events and deliver pending notification emails. The scheduler runtime is implemented in `src/scheduler.py`, and the notification cadence/escalation rules are implemented in `src/notifications.py`. Evidence: `README.md`, `src/scheduler.py`, `src/notifications.py`.

## Quick Start
### Entry Points (How To Choose)
| Entrypoint | When to use | Evidence |
|---|---|---|
| Docker Compose service (`scheduler-worker`) | Recommended for normal development because Compose provides DB/Redis wiring and mounts `shared` code needed by this worker. | `../../docker-compose.yml`, `../../docker/workers/scheduler/Dockerfile` |
| Local Python module (`python -m src.scheduler`) | Use for direct process debugging when dependencies are installed and `PYTHONPATH` includes the shared package source directory. | `src/scheduler.py`, `src/notifications.py`, `requirements.txt`, `../../CoreInstances/ApiServer/src/shared` |

### Option A: Recommended (Docker Compose from repo root)
```bash
cd ../..
make up
make logs-workers
```
Evidence: `../../Makefile`.

### Option B: Local Python process (advanced)
```bash
python -m pip install -r requirements.txt
export DATABASE_URL='postgresql://<user>:<pass>@<host>:<port>/<db>'
export REDIS_URL='redis://localhost:6380/0'
export LOG_LEVEL='INFO'
export PYTHONPATH='../../CoreInstances/ApiServer/src'
python -m src.scheduler
```
Evidence: `requirements.txt`, `src/scheduler.py`, `src/notifications.py`, `../../CoreInstances/ApiServer/src/shared`, `../../docker/workers/scheduler/Dockerfile`.

## Where To Look Next
- Structure and hotspots: [`./DIRECTORY_MAP.md`](./DIRECTORY_MAP.md)
- Day-2 runbook: [`./OPERATIONS.md`](./OPERATIONS.md)
- Internals and flow: [`./ARCHITECTURE.md`](./ARCHITECTURE.md)

## Key Conventions
- Logging convention: structured JSON logs with redaction processor enabled before rendering. Evidence: `src/scheduler.py`.
- Idempotency convention: notifications are inserted through `insert_notification_if_absent(...)` using deterministic dedupe keys. Evidence: `src/notifications.py`.
- Dedupe key convention: base format is `<notification_type>:<entity_id>:<process_date>` with optional interval/role suffixes (for reminder windows and manager/coordinator fan-out). Evidence: `src/notifications.py`.
- Scheduling convention: two recurring jobs only in this worker process (daily generation at 06:00, queue processing every 5 minutes). Evidence: `src/scheduler.py`.
- Dependency convention: business/domain and SMTP integrations are consumed from `shared.*` modules outside this folder. Evidence: `src/scheduler.py`, `src/notifications.py`.

## Assumptions And Unknowns
- Assumption: run operational commands such as `make up` and `make logs-workers` from repository root (`../..`). Evidence: `../../Makefile`.
- Assumption: local non-Docker execution requires import-path setup for `shared` (`PYTHONPATH=../../CoreInstances/ApiServer/src`). Evidence: `src/scheduler.py`, `src/notifications.py`, `../../CoreInstances/ApiServer/src/shared`.
- Unknown: standalone worker-local test/lint harness expectations are not defined in this directory; discovered validation workflows are inherited from root-level tooling. Evidence: local file inventory, `../../Makefile`, `../../.github/workflows/ci.yml`.
