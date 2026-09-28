# Architecture

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.

## High-Level Overview
This directory implements a long-running email intake worker. The runtime loop connects to IMAP, polls unread emails with attachments, applies sender-policy checks (domain + GAL membership/person checks), validates and scans attachments, stores accepted files, records database state/audits, and queues extraction work.
Evidence: `src/worker.py:636`, `src/email_client.py:122`, `src/directory_lookup.py:133`, `src/worker.py:171`, `src/worker.py:213`, `src/worker.py:332`, `src/worker.py:432`, `src/worker.py:322`

The worker is environment-driven. Dependency clients are constructed in `create_worker_from_env()`, and containerized execution is defined in root compose + Dockerfile.
Evidence: `src/worker.py:686`, `../../docker-compose.yml:324`, `../../docker/workers/email-intake/Dockerfile:37`

## Component Diagram

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

Evidence: `src/email_client.py:40`, `src/worker.py:460`, `src/worker.py:322`, `src/worker.py:264`, `src/worker.py:332`, `src/worker.py:432`, `src/directory_lookup.py:67`, `src/gal_provider.py:39`

## Module Responsibilities
| Module | Responsibility | Evidence |
|---|---|---|
| `src/worker.py` | Orchestration loop, attachment pipeline, dedupe, persistence, queueing, lifecycle signals | `src/worker.py:460`, `src/worker.py:618`, `src/worker.py:636`, `src/worker.py:731` |
| `src/email_client.py` | IMAP I/O abstraction (connect, fetch unread, move processed, quarantine) | `src/email_client.py:74`, `src/email_client.py:122`, `src/email_client.py:175`, `src/email_client.py:197` |
| `src/directory_lookup.py` | Sender domain/GAL decision tree and employee lookup/auto-create | `src/directory_lookup.py:71`, `src/directory_lookup.py:101`, `src/directory_lookup.py:111`, `src/directory_lookup.py:133` |
| `src/gal_provider.py` | GAL query protocol + DB implementation | `src/gal_provider.py:28`, `src/gal_provider.py:39` |
| `src/malware_scanner.py` | ClamAV TCP INSTREAM scanning with fail-open/closed behavior | `src/malware_scanner.py:21`, `src/malware_scanner.py:54`, `src/malware_scanner.py:106` |
| `tests/test_directory_lookup.py` | Unit tests for directory lookup decision branches | `tests/test_directory_lookup.py:72`, `tests/test_directory_lookup.py:81`, `tests/test_directory_lookup.py:90`, `tests/test_directory_lookup.py:105`, `tests/test_directory_lookup.py:125` |

## Data Flow
1. Start worker (`main()`), build dependencies from env.
2. Connect IMAP; loop polling unread messages with attachments.
3. For each email, precompute attachment hashes and perform idempotency checks.
4. Resolve employee from sender via directory + GAL policy; ignore/quarantine when required.
5. Validate each attachment (size, MIME type, optional malware scan).
6. Persist accepted attachments to MinIO and DB; initialize extraction run rows.
7. Queue new document IDs to Redis extraction queue.
8. Write audit events and move emails to `Processed` or `Quarantine`.
Evidence: `src/worker.py:731`, `src/worker.py:686`, `src/worker.py:642`, `src/worker.py:473`, `src/worker.py:480`, `src/worker.py:486`, `src/worker.py:549`, `src/worker.py:558`, `src/worker.py:291`, `src/worker.py:322`, `src/worker.py:599`, `src/email_client.py:175`, `src/email_client.py:197`

## Persistent I/O Surfaces
| Surface | Direction | Format/Shape | Evidence |
|---|---|---|---|
| IMAP unread messages | Input | Unseen messages, attachment-driven processing | `src/email_client.py:140`, `src/email_client.py:148` |
| MinIO objects | Output | Key pattern `email-intake/<YYYYMMDD>/<uuid>.<ext>` | `src/worker.py:107` |
| Redis queue | Output | List key `extraction_tasks`, JSON payload with `document_id`, `queued_at`, `source` | `src/worker.py:67`, `src/worker.py:324` |
| Postgres tables via ORM | Output | Email intake, document, extraction run, audit records | `src/worker.py:32`, `src/worker.py:353`, `src/worker.py:276`, `src/worker.py:292`, `src/worker.py:449` |
| IMAP folders | Output side-effect | Moves to configured processed folder or `Quarantine` | `src/email_client.py:175`, `src/email_client.py:197`, `src/email_client.py:209` |

## Configuration Model
- Source of truth: environment variables (`os.environ.get` with defaults).
- Worker factories:
  - `create_worker_from_env()` wires IMAP, directory lookup, MinIO, Redis, and optional ClamAV scanner.
  - Sub-factories in `email_client.py`, `directory_lookup.py`, `malware_scanner.py`.
Evidence: `src/worker.py:686`, `src/email_client.py:224`, `src/directory_lookup.py:181`, `src/malware_scanner.py:142`

- Container configuration:
  - Dev compose defines `email-intake-worker` env, volume mounts, and dependencies.
  - Dockerfile copies `shared` and worker source into `/app`, then runs `python -m src.worker`.
Evidence: `../../docker-compose.yml:324`, `../../docker-compose.yml:356`, `../../docker-compose.yml:359`, `../../docker/workers/email-intake/Dockerfile:28`, `../../docker/workers/email-intake/Dockerfile:31`, `../../docker/workers/email-intake/Dockerfile:37`

## Reliability and Safety Characteristics
- Idempotency and dedupe:
  - Full-message dedupe by `message_id`.
  - Per-attachment dedupe by `(message_id, attachment_hash)` for retry safety.
  - Existing-document dedupe by `(employee_id, file_hash)`.
Evidence: `src/worker.py:387`, `src/worker.py:397`, `src/worker.py:127`

- Input constraints:
  - MIME allowlist + 20MB maximum attachment size.
  - Optional ClamAV scanning before storage.
Evidence: `src/worker.py:55`, `src/worker.py:64`, `src/worker.py:171`, `src/malware_scanner.py:142`

- Logging/security:
  - Secure logging configured via shared logging utility.
  - Sensitive env values should be managed outside source (compose env + `.env` usage at root).
Evidence: `src/worker.py:48`, `../../docker-compose.yml:354`

## Extension Points
- Add a new directory source:
  - Implement `GALProvider` and inject into `DirectoryLookup`.
  - Evidence: `src/gal_provider.py:28`, `src/directory_lookup.py:79`

- Change attachment policy:
  - Adjust `_validate_attachment()` for file types/limits/scanning policy.
  - Evidence: `src/worker.py:171`

- Change queue protocol:
  - Extend `_queue_extraction_task()` payload or queue name.
  - Evidence: `src/worker.py:67`, `src/worker.py:322`

- Add tests for pipeline paths:
  - Follow async style and dependency mocking pattern used in `tests/test_directory_lookup.py`.
  - Evidence: `tests/test_directory_lookup.py:58`, `tests/test_directory_lookup.py:72`
