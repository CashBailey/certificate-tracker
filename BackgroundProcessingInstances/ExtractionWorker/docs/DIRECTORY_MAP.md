# Directory Map

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Rendered Tree (Depth-Limited)

```text
.
├── README.md
├── requirements.txt
├── docs/
│   ├── README.md
│   ├── DIRECTORY_MAP.md
│   ├── OPERATIONS.md
│   └── ARCHITECTURE.md
├── src/
│   ├── __init__.py
│   ├── worker.py
│   ├── pipeline.py
│   ├── normalize.py
│   ├── identify.py
│   ├── zone_extract.py
│   ├── generic_extract.py
│   ├── llm_client.py
│   ├── ocr_client.py
│   ├── pdf_text.py
│   ├── pdf_raster.py
│   ├── preprocess.py
│   ├── confidence.py
│   ├── name_matcher.py
│   ├── course_name_corrector.py
│   └── gpu_detect.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_pipeline_branching.py
    ├── test_visual_template_matching.py
    ├── test_zone_extraction.py
    ├── test_gal_name_replacement.py
    └── test_name_mismatch_handling.py
```

Evidence: `find . -maxdepth 3 -type f` inventory from this directory, plus `ls -la src`, `ls -la tests`.

## Top-Level Anchors

- `README.md`: short purpose summary for this directory. Evidence: `README.md:1`.
- `requirements.txt`: dependency manifest for this Python worker. Evidence: `requirements.txt:1`.
- `src/`: production worker/pipeline code. Evidence: `src/worker.py:1`, `src/pipeline.py:1`.
- `tests/`: behavior-focused unit tests. Evidence: `tests/test_pipeline_branching.py:1`.
- `docs/`: generated developer-facing documentation for this directory. Evidence: `docs/README.md`.

## Path Table

| Path | Purpose | Key Files Inside | Notes (Entrypoint / Config / Data) |
|---|---|---|---|
| `README.md` | Existing short directory readme | `README.md` | States purpose at high level. Evidence: `README.md:1`. |
| `requirements.txt` | Python dependency manifest | `requirements.txt` | Confirms Python ecosystem and external libs (Redis, SQLAlchemy, MinIO, pypdf, pdf2image, OpenCV, httpx). Evidence: `requirements.txt:5`. |
| `src/` | Worker and extraction implementation | `worker.py`, `pipeline.py`, `normalize.py`, `identify.py`, `zone_extract.py`, `generic_extract.py`, `llm_client.py` | Primary runtime entrypoint is `src.worker.main()`. Evidence: `src/worker.py:415`, `src/worker.py:428`. |
| `src/worker.py` | Long-running queue worker orchestration | `ExtractionWorker`, `async_main`, `main` | Polls Redis queue `extraction_tasks`; persists results via `shared.repository`; handles name mismatch channel logic. Evidence: `src/worker.py:363`, `src/worker.py:135`, `src/worker.py:220`. |
| `src/pipeline.py` | Core extraction path orchestration | `ExtractionPipeline` | Implements Path A (template/zone) and Path B (fallback generic). Evidence: `src/pipeline.py:7`, `src/pipeline.py:105`, `src/pipeline.py:133`. |
| `src/ocr_client.py` | Redis protocol client for OCR worker | `RedisOcrClient` | Publishes to `ocr_tasks`, reads `ocr_results:{request_id}`. Evidence: `src/ocr_client.py:21`, `src/ocr_client.py:66`, `src/ocr_client.py:69`. |
| `src/llm_client.py` | LLM cleanup/correction client | `_call_ollama`, consensus logic | Uses `OLLAMA_URL` and consensus env vars; has graceful fallback on unavailable LLM. Evidence: `src/llm_client.py:26`, `src/llm_client.py:30`, `src/llm_client.py:158`. |
| `src/identify.py` | Hash-only template matching | `TemplateIdentifier` | Uses perceptual hash Hamming distance only; fallback flag returned for generic path. Evidence: `src/identify.py:4`, `src/identify.py:67`, `src/identify.py:168`. |
| `src/zone_extract.py` | Template-zone extraction | `ZoneExtractor` | Extracts per zone and routes handwriting OCR if configured. Evidence: `src/zone_extract.py:44`, `src/zone_extract.py:137`. |
| `src/generic_extract.py` | Regex fallback extraction and review assist | `GenericExtractor` | Extracts canonical fields from full text, builds candidate list for review assist. Evidence: `src/generic_extract.py:2`, `src/generic_extract.py:210`, `src/generic_extract.py:317`. |
| `tests/` | Unit tests | `test_pipeline_branching.py`, `test_visual_template_matching.py`, `test_zone_extraction.py`, `test_gal_name_replacement.py`, `test_name_mismatch_handling.py` | Uses `pytest`; async tests present; repository-level execution is via `make test`. Evidence: `tests/test_pipeline_branching.py:23`, `tests/test_pipeline_branching.py:206`, `../../Makefile:200`. |
| `tests/conftest.py` | Test import path bootstrapping | `conftest.py` | Injects both `CoreInstances/ApiServer/src` and this worker `src` into `sys.path`. Evidence: `tests/conftest.py:12`. |

## Entrypoints and Execution Workflows

| Entrypoint | Purpose | Selection Guidance | Evidence |
|---|---|---|---|
| `src/worker.py::main()` | Long-running worker process | Choose for queue-driven runtime processing. | `src/worker.py:415`, `src/worker.py:428` |
| `make test` (repository root) | Test execution workflow | Choose this for standard suite execution documented by the project. | `../../Makefile:200`, `../../Makefile:201`, `../../README.md:230` |

## Interface / Contract Artifacts

- Internal contracts rely on `shared.models` and `shared.template_registry` imported from outside this directory. Evidence: `src/pipeline.py:21`, `src/pipeline.py:31`, `src/worker.py:135`.
- Template contract source files are stored outside this directory at `CoreInstances/ApiServer/templates/*.json` and parsed/validated by `JsonTemplateRegistry`.
- Evidence: `../../CoreInstances/ApiServer/templates/demo_cert.json:1`, `../../CoreInstances/ApiServer/templates/lms_certificate.json:1`, `../../CoreInstances/ApiServer/src/shared/template_registry.py:58`, `../../CoreInstances/ApiServer/src/shared/template_registry.py:112`, `../../CoreInstances/ApiServer/src/shared/template_registry.py:179`.
- Local OpenAPI/schema/migration artifacts in this directory: none found in file inventory.

## Hotspots

- `src/worker.py`: queue consumption, DB/storage integration, rejection/review transitions.
- `src/pipeline.py`: path branching and extraction result assembly.
- `src/llm_client.py`: external model behavior, consensus tuning, fallback handling.
- `src/identify.py`: hash-match threshold behavior.
- `tests/test_pipeline_branching.py`: guards branch behavior regressions.

Evidence: `src/worker.py:356`, `src/pipeline.py:105`, `src/llm_client.py:26`, `src/identify.py:67`, `tests/test_pipeline_branching.py:2`.
