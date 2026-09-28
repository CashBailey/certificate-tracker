# Architecture

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## High-Level Overview
This directory implements a long-running background worker that orchestrates notification generation and delivery. The worker process starts an `AsyncIOScheduler`, registers recurring jobs, and loops indefinitely. Evidence: `src/scheduler.py`.

Business logic for who gets notified, when notifications are produced, and how idempotency is enforced is centralized in `NotificationGenerator` (`src/notifications.py`). The worker depends on `shared` modules outside this directory for repository I/O, model contracts, and email sending. Evidence: `src/notifications.py`, `src/scheduler.py`.

## Component Diagram (ASCII)
```text
                 +----------------------------------+
                 | src/scheduler.py                 |
                 | - env/bootstrap                  |
                 | - SchedulerWorker                |
                 +----------------+-----------------+
                                  |
                       +----------v-----------+
                       | AsyncIOScheduler     |
                       | 06:00 daily + 5-min  |
                       +----------+-----------+
                                  |
         +------------------------+------------------------+
         |                                                 |
+--------v----------------+                    +-----------v------------------+
| generate_notifications  |                    | process_notification_queue   |
| _daily()                |                    | ()                           |
+-----------+-------------+                    +---------------+--------------+
            |                                                  |
            v                                                  v
 +----------+-------------------+                    +---------+------------------+
 | src/notifications.py         |                    | shared.email_sender        |
 | NotificationGenerator        |                    | send_email(...)            |
 +----------+-------------------+                    +-------------+---------------+
            |                                                         |
            v                                                         v
  +---------+---------------------+                         +---------+------------------+
  | shared.repository / models    |<----------------------->| SMTP_* env + from address |
  +-------------------------------+                         +----------------------------+
            |
            v
     +------+------+
     | PostgreSQL  |
     +-------------+

Startup also verifies Redis connectivity via REDIS_URL.
```
Evidence: `src/scheduler.py`, `src/notifications.py`.

## Module Responsibilities
| Module | Responsibility | Evidence |
|---|---|---|
| `src/scheduler.py` | Process bootstrap, logging setup/redaction wiring, env var reads, Redis connectivity check, APScheduler job registration, queue processing loop, graceful shutdown. | `src/scheduler.py` |
| `src/notifications.py` | Notification cadence rules (configurable via `alert_configuration` table), recipient resolution (employee + Coordinator), dedupe key generation, cursor-based backfill, notification message construction. | `src/notifications.py` |
| `src/__init__.py` | Package marker and module-level description only. | `src/__init__.py` |

## Data Flow
1. Startup:
   - Reads `DATABASE_URL`, `REDIS_URL`, and `LOG_LEVEL`.
   - Initializes secure logging + redaction.
   - Verifies Redis with `PING`.
   - Initializes SQLAlchemy async session factory.
2. Scheduler registration:
   - Daily generation job (`generate_notifications_daily`) — send time is read from the `alert_configuration` table (`global_send_hour`, `global_send_minute`), falling back to 06:00 if no config exists.
   - Queue processing job every 5 minutes (`process_notification_queue`).
3. Daily generation path:
   - Loads `daily_notifications` cursor.
   - Backfills missed dates and processes each date.
   - Reads reminder day offsets from `alert_configuration` (falls back to `_DEFAULT_REQUIREMENT_REMINDER_DAYS` / `_DEFAULT_CERTIFICATE_REMINDER_DAYS`).
   - Applies requirement and certificate cadence windows based on configured offsets.
   - Checks `daily_overdue_enabled` flag before generating daily overdue notifications.
   - Builds dedupe keys and writes notifications with `insert_notification_if_absent(...)`.
   - Updates cursor to the current processed date.
4. Queue processing path:
   - Reads up to 50 undelivered notifications.
   - Resolves recipient email from repository.
   - Sends via shared sender.
   - Marks delivered notifications and commits transaction.
Evidence: `src/scheduler.py`, `src/notifications.py`.

## Configuration Model
- File-based config: none found in this directory (no local YAML/TOML/INI config files).
- Environment config:
  - `DATABASE_URL` required.
  - `REDIS_URL` optional with default.
  - `LOG_LEVEL` optional with default.
  - SMTP config vars are provided via compose (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `NOTIFICATION_FROM_EMAIL`) and consumed through shared email sender path.
- CLI flags: none implemented in this directory (startup path has no argument parser).
- Container wiring:
  - Dockerfile sets `PYTHONPATH=/app` and runs `python -m src.scheduler`.
  - Compose mounts worker `src` and `shared` for dev runtime.
Evidence: `src/scheduler.py`, `../../docker-compose.yml`, `../../docker/workers/scheduler/Dockerfile`, local file inventory.

## Extension Points
- Adjust default cadence windows by changing private constants (`_DEFAULT_REQUIREMENT_REMINDER_DAYS`, `_DEFAULT_CERTIFICATE_REMINDER_DAYS`). These are fallbacks — runtime values are read from the `alert_configuration` table via the Coordinator-facing Configuration UI. Evidence: `src/notifications.py`.
- Customize run-specific reminder windows by passing constructor overrides into `NotificationGenerator(...)`. Evidence: `src/notifications.py`.
- Add/modify scheduled jobs by editing `scheduler.add_job(...)` registrations. Evidence: `src/scheduler.py`.
- Extend message templates by editing `_build_*_message*` helpers. Evidence: `src/notifications.py`.
