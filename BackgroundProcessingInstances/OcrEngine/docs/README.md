# OcrEngine Documentation

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## What This Directory Is
`OcrEngine` is a Python OCR worker that consumes OCR requests from Redis queue key `ocr_tasks`, runs bounded Tesseract OCR on image regions, and publishes short-lived results. The standard image intentionally excludes EasyOCR/Torch because that path has no enforceable per-call deadline and adds a multi-gigabyte GPU runtime. A custom image may supply EasyOCR only with `OCR_ENABLE_EASYOCR=true` and an operator-approved resource policy.

## Quick Start
### Option A: Run as part of the full project stack (recommended)
From repository root (`../../` relative to this directory):
```bash
cd ../..
make up
make logs-workers
```
Evidence: `../../README.md:59`, `../../README.md:62`, `../../Makefile:85`, `../../Makefile:118`.

### Option B: Run from this directory as a standalone Python process
```bash
python -m pip install -r requirements.txt
python -m src.worker
```
Evidence: `requirements.txt:1`, `src/worker.py:202`, `src/worker.py:232`.

Important for standalone mode:
- This code imports `shared.models`, which is outside this directory in this repo (`../../CoreInstances/ApiServer/src/shared/models.py`). Ensure `shared` is importable in your runtime environment. Evidence: `src/ocr_service.py:14`, `../../CoreInstances/ApiServer/src/shared/models.py:413`, `../../CoreInstances/ApiServer/src/shared/models.py:422`.

### Test command
From repository root:
```bash
cd ../..
make test
```
Evidence: `../../Makefile:200`, `../../Makefile:201`.

## Entrypoints
| Entrypoint | Type | When to use |
|---|---|---|
| `python -m src.worker` | Process entrypoint | Run queue consumer worker loop. Evidence: `src/worker.py:202`, `src/worker.py:232`. |
| `ocr-engine` service in compose | Containerized process | Run worker in the project stack with Redis/MinIO wiring. Evidence: `../../docker-compose.yml:261`, `../../docker-compose.yml:265`, `../../docker-compose.yml:268`. |
| `TesseractOcrService`, `EasyOcrService`, `EnsembleOcrEngine` | Library classes | Reuse OCR logic from another Python service/module. Evidence: `src/ocr_service.py:17`, `src/easyocr_service.py:17`, `src/ensemble_ocr.py:18`. |

## Where To Look Next
- [`./DIRECTORY_MAP.md`](./DIRECTORY_MAP.md) for directory structure and linked external files.
- [`./OPERATIONS.md`](./OPERATIONS.md) for setup, run modes, env vars, and troubleshooting.
- [`./ARCHITECTURE.md`](./ARCHITECTURE.md) for component/data flow and extension points.

## Assumptions And Unknowns
- Assumption: canonical local operation uses repository-root worker orchestration commands (`make up`, `make logs-workers`) rather than directory-local orchestration files. Evidence: `../../README.md:59`, `../../README.md:62`, `../../Makefile:85`, `../../Makefile:118`.
- Unknown: directory-local test runner/lint configuration is not defined in this directory itself; testing/linting commands are defined at project root (`../../Makefile`). Evidence: `../../Makefile:200`, `../../Makefile:206`.
- EasyOCR performance, GPU availability, and timeout behavior are deployment-specific; the supported standard image uses Tesseract only.
