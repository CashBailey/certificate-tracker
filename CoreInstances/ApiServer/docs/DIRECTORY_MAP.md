# Directory Map

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Rendered Tree (Trimmed)

```text
.
├── README.md
├── pyproject.toml
├── requirements.txt
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── ...
│       └── 019_split_notification_read_from_delivered.py
├── src/
│   ├── main.py
│   ├── deps.py
│   ├── authorizer.py
│   ├── review.py
│   ├── auth/
│   │   ├── config.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── security.py
│   │   └── service.py
│   ├── routes/
│   │   ├── admin.py
│   │   ├── audit_logs.py
│   │   ├── certificate_types.py
│   │   ├── documents.py
│   │   ├── employees.py
│   │   ├── extractions.py
│   │   ├── notifications.py
│   │   ├── reports.py
│   │   ├── requirements.py
│   │   ├── schemas.py
│   │   ├── templates.py
│   │   └── verified_records.py
│   └── shared/
│       ├── models.py
│       ├── orm_models.py
│       ├── protocols.py
│       ├── repository.py
│       ├── repositories/
│       ├── storage.py
│       └── template_registry.py
├── templates/
│   ├── demo_cert.json
│   └── lms_certificate.json
├── tests/
│   ├── conftest.py
│   ├── api/
│   ├── integration/
│   ├── ocr/
│   ├── ocr_fixtures/
│   ├── performance/
│   ├── resilience/
│   ├── security/
│   └── unit/
└── docs/
    ├── README.md
    ├── DIRECTORY_MAP.md
    ├── OPERATIONS.md
    └── ARCHITECTURE.md
```

(Evidence: filesystem inventory from current directory)

## External Anchors Required To Run/Build This Directory

| Path | Why It Matters | Evidence |
|---|---|---|
| `../../Makefile` | Canonical dev/start/test/lint/db command entrypoints (`make up`, `make db-migrate`, etc.) | `../../Makefile` |
| `../../docker-compose.yml` | Development service orchestration; defines `api` service wiring and dependencies | `../../docker-compose.yml` |
| `../../docker-compose.prod.yml` | Production orchestration references prebuilt `api` image | `../../docker-compose.prod.yml` |
| `../../docker/api/Dockerfile.dev` | Dev API container startup command (`uvicorn` with reload) | `../../docker/api/Dockerfile.dev` |
| `../../docker/api/Dockerfile` | Production-image build recipe command (`gunicorn`) | `../../docker/api/Dockerfile` |
| `../../README.md` | Root-level quick start and service URLs for local stack | `../../README.md` |
| `../../DOCKER.md` | Detailed Docker workflow and operational command references | `../../DOCKER.md` |
| `../../.github/workflows/ci.yml` | CI lint/test/build-check workflow for this directory | `../../.github/workflows/ci.yml` |

## Contract Surfaces

| Path | Contract Type | Notes |
|---|---|---|
| `src/routes/schemas.py` | API DTO contracts | Pydantic request/response contracts for main route groups |
| `src/auth/schemas.py` | Auth DTO contracts | Login/token/user/password payload contracts |
| `src/shared/protocols.py` | Internal interfaces | Repository/storage/clock protocols and domain exceptions |
| `src/shared/models.py` | Domain contracts | Shared enums and entity dataclasses |
| `src/shared/orm_models.py` | Persistence contracts | SQLAlchemy mapping and DB constraints |
| `alembic/versions/` | Migration contracts | Incremental schema evolution history |
| `templates/demo_cert.json` | Template contract data | Registry-consumed template definition |
| `templates/lms_certificate.json` | Template contract data | Registry-consumed template definition |

## Path/Purpose Table

| Path | Purpose | Key Files Inside | Notes (entrypoint/config/data) |
|---|---|---|---|
| `src/main.py` | API app bootstrap | `src/main.py` | Registers routers and health/root endpoints |
| `src/deps.py` | Dependency and auth wiring | `src/deps.py` | DB/Redis/storage clients and auth dependency guards |
| `src/auth/` | Authentication | `router.py`, `service.py`, `security.py`, `config.py` | JWT, refresh-cookie, password flow |
| `src/routes/` | HTTP endpoint implementation | `documents.py`, `requirements.py`, `extractions.py`, `reports.py`, etc. | Workflow behavior at API boundary |
| `src/shared/` | Shared domain/infrastructure code | `models.py`, `protocols.py`, `repository.py`, `storage.py`, `template_registry.py` | Core business/data abstractions |
| `src/shared/repositories/` | Split repository modules | `employee.py`, `document.py`, `extraction.py` | Alternative to monolithic `SqlRepository` |
| `alembic/` | Migration runtime configuration | `env.py`, `script.py.mako`, `alembic.ini` | Alembic online/offline execution |
| `alembic/versions/` | Schema migration timeline | revision files `001`..`019` | DB change history |
| `templates/` | Extraction template data | `demo_cert.json`, `lms_certificate.json` | Read/write via templates API + registry |
| `tests/` | Test suites | `unit/`, `integration/`, `ocr/`, `security/`, `resilience/`, `performance/` | Mixed integration and simulation-style tests |
| `docs/` | Directory-local developer docs | generated docs set | This documentation package |

## Hotspots

- `src/routes/documents.py`: upload + validation + storage + queue handoff.
- `src/routes/requirements.py`: CSV bulk import, duplicate handling, waiver lifecycle.
- `src/review.py`: approval/rejection with optimistic locking and idempotent record creation.
- `src/shared/repository.py`: large persistence surface spanning multiple bounded contexts.
- `alembic/versions/`: required touchpoint for schema-affecting features.

(Evidence: `src/routes/documents.py`, `src/routes/requirements.py`, `src/review.py`, `src/shared/repository.py`, `alembic/versions/`)
