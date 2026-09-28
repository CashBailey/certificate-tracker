# SchedulerNotificationWorker

Purpose

- Runs daily and scheduled jobs
- Generates NotificationEvent records

Expected contents

- Scheduler code
- Job definitions and schedules
- Deployment notes

## Directory Overview

- Entrypoints:
  - Recommended (repo root): `make up` then `make logs-workers`
  - Direct local run: `PYTHONPATH=../../CoreInstances/ApiServer/src python -m src.scheduler`
- Documentation:
  - `docs/README.md`
  - `docs/DIRECTORY_MAP.md`
  - `docs/OPERATIONS.md`
  - `docs/ARCHITECTURE.md`
