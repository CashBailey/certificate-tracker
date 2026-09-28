# ExtractionWorker Documentation

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## What This Directory Is
This directory contains the Python extraction worker implementation for certificate documents. It includes a long-running worker loop, the extraction pipeline (normalization, template identification, OCR-assisted extraction, fallback generic extraction, confidence/review gating), and unit tests for key behaviors such as pipeline branching, visual template matching, zone extraction, and name-mismatch handling. Evidence: `src/worker.py:1`, `src/pipeline.py:1`, `tests/test_pipeline_branching.py:1`, `tests/test_visual_template_matching.py:1`, `tests/test_zone_extraction.py:1`, `tests/test_name_mismatch_handling.py:1`.

## Quick Start (Evidence-Backed)

### 1) Install dependencies
- Local Python dependency install command (used by worker image build):

```bash
pip install -r requirements.txt
```

- Dependency list is present in `requirements.txt`. Evidence: `requirements.txt:1`.
- Install command is defined in worker image build. Evidence: `../../docker/workers/extraction/Dockerfile:26`, `../../docker/workers/extraction/Dockerfile:27`.

### 2) Run the worker
```bash
python -m src.worker
```
Evidence: `src/__init__.py:7`, `src/worker.py:415`, `src/worker.py:428`.

Notes:
- Worker runtime imports external `shared.*` modules (outside this directory), and full-stack compose mounts those modules at `/app/shared`.
- Evidence: `src/worker.py:135`, `../../docker-compose.yml:243`.
- Local non-container `PYTHONPATH` policy for these imports is `Unknown` (not explicitly documented in this directory).

### 3) Run tests
Verified repository-level test command:

```bash
# from repository root
make test
```

Evidence: `../../Makefile:200`, `../../Makefile:201`, `../../README.md:230`.

Notes:
- The suite uses `pytest` (including async markers). Evidence: `tests/test_pipeline_branching.py:23`, `tests/test_pipeline_branching.py:206`, `tests/test_zone_extraction.py:132`.
- A directory-local canonical test command is `Unknown` (not explicitly documented in this directory).

### 4) Full-stack context (outside this directory)
If running this worker as part of the full repository stack, repository-level commands are documented in `../../README.md`:

```bash
make setup
make up
make logs-workers
```

Evidence: `../../README.md:62`, `../../README.md:246`, `../../README.md:257`.

## Entrypoints (How To Choose)

| Entrypoint | Use When | Evidence |
|---|---|---|
| `python -m src.worker` | Running the queue-driven worker process in normal operations. | `src/__init__.py:7`, `src/worker.py:356`, `src/worker.py:428` |
| `make test` (repository root) | Running the test suite using the documented project workflow. | `../../Makefile:200`, `../../Makefile:201`, `../../README.md:230` |

## Where To Look Next
- Structure map: [`./DIRECTORY_MAP.md`](./DIRECTORY_MAP.md)
- Operations and runbook: [`./OPERATIONS.md`](./OPERATIONS.md)
- Architecture and data flow: [`./ARCHITECTURE.md`](./ARCHITECTURE.md)

## Assumptions And Unknowns
- Assumption: runtime Python baseline for this worker is container Python `3.12`, with nearest repository-level explicit floor `>=3.11`. Evidence: `../../docker/workers/extraction/Dockerfile:4`, `../../CoreInstances/ApiServer/pyproject.toml:5`.
- Unknown: local-host policy without Docker (including canonical `PYTHONPATH` setup) is not explicitly codified in this directory. Evidence: local file inventory, `../../Makefile:200`, `../../Makefile:206`.
- Assumption: repository-level workflows in `../../Makefile` are the canonical install/test/lint path (`make test`, `make lint`, etc.). Evidence: `../../Makefile:200`, `../../Makefile:206`.
- Assumption: template assets consumed by this worker are sourced from `CoreInstances/ApiServer/templates` through `TEMPLATES_DIR`, with currently observed files `demo_cert.json` and `lms_certificate.json`. Evidence: `../../CoreInstances/ApiServer/templates/demo_cert.json:1`, `../../CoreInstances/ApiServer/templates/lms_certificate.json:1`, `src/worker.py:394`, `src/pipeline.py:60`.
- Assumption: full-stack Docker wiring mounts templates into `/app/templates` for extraction runtime. Evidence: `../../docker-compose.yml:214`, `../../docker-compose.yml:244`.
- Assumption: runtime credentials and deployment wiring are external to this directory via `shared.*` imports and external services. Evidence: `src/worker.py:135`, `tests/conftest.py:12`.
- Assumption: canonical data contracts (`ExtractionRun`, template schema models, repository/storage abstractions) are sourced via external `shared.*` modules, not defined in this directory. Evidence: `src/pipeline.py:21`, `src/worker.py:135`, `src/worker.py:136`.
