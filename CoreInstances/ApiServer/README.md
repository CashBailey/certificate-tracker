# ApiServer

## Purpose

- Authentication and RBAC enforcement
- File uploads and extraction submission
- Review actions and reporting APIs

Evidence: `src/main.py`, `src/auth/router.py`, `src/routes/documents.py`, `src/routes/extractions.py`, `src/routes/reports.py`

## Directory Overview

- Purpose and quick start: `docs/README.md`
- Directory structure and hotspots: `docs/DIRECTORY_MAP.md`
- Setup/run/test/lint/migration operations: `docs/OPERATIONS.md`
- Component design and data flow: `docs/ARCHITECTURE.md`

## Entrypoints

- API application module: `src/main.py`
- Migration runtime: `alembic/env.py` (configured by `alembic.ini`)
- OCR fixture generator script: `tests/ocr_fixtures/generator/generate_test_certs.py`

## Canonical Run Path

- From repository root (`../../`): `make setup`, `make up`, `make db-migrate`, `make health`
- Command source: `../../Makefile`, `../../README.md`
