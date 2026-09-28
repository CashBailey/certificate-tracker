# Architecture

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.

## High-Level Overview
This directory implements an asynchronous extraction worker that consumes document jobs from Redis, loads document bytes via shared repository/storage adapters, runs extraction through a two-path pipeline, and writes extraction outcomes back to persistence with review-state transitions. Evidence: `src/worker.py:356`, `src/worker.py:135`, `src/worker.py:177`, `src/worker.py:298`.

The pipeline branches based on hash-only visual template matching: Path A performs per-zone extraction and zone-level LLM correction for template-matched documents; Path B runs full-page OCR and generic regex/LLM extraction when no template matches. Evidence: `src/pipeline.py:7`, `src/pipeline.py:95`, `src/pipeline.py:105`, `src/pipeline.py:133`.

## Entrypoints and Selection

| Entrypoint | Layer | Choose When | Evidence |
|---|---|---|---|
| `src/worker.py::main()` | Process/runtime | Operating as a background worker polling Redis queue(s). | `src/worker.py:356`, `src/worker.py:415`, `src/worker.py:428` |
| Compose service `extraction-worker` | Deployment/runtime | Running this worker in full-stack containerized mode. | `../../docker-compose.yml:214`, `../../docker-compose.yml:217` |

## Component Diagram

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

Evidence: `src/worker.py:363`, `src/worker.py:135`, `src/worker.py:136`, `src/pipeline.py:105`, `src/pipeline.py:133`, `src/identify.py:67`, `src/zone_extract.py:44`, `src/generic_extract.py:210`.

## Module Responsibilities

| Module / Folder | Responsibility | Evidence |
|---|---|---|
| `src/worker.py` | Process lifecycle, queue polling, DB/storage wiring, state transition logic, name mismatch handling. | `src/worker.py:79`, `src/worker.py:356`, `src/worker.py:220` |
| `src/pipeline.py` | End-to-end extraction orchestration and branch selection. | `src/pipeline.py:40`, `src/pipeline.py:105`, `src/pipeline.py:133` |
| `src/normalize.py` | PDF/image normalization, scanned/digital classification, OCR token merge. | `src/normalize.py:49`, `src/normalize.py:118`, `src/normalize.py:206` |
| `src/identify.py` | pHash/Hamming-distance template selection and fallback signal. | `src/identify.py:67`, `src/identify.py:168` |
| `src/zone_extract.py` | Zone token selection, zone OCR routing, parse/validate/confidence for zone results. | `src/zone_extract.py:44`, `src/zone_extract.py:129`, `src/zone_extract.py:179` |
| `src/generic_extract.py` | Regex-driven canonical field extraction + review candidate generation. | `src/generic_extract.py:116`, `src/generic_extract.py:210`, `src/generic_extract.py:317` |
| `src/ocr_client.py` | Redis-based OCR request/response protocol. | `src/ocr_client.py:21`, `src/ocr_client.py:66`, `src/ocr_client.py:69` |
| `src/llm_client.py` | Ollama call layer, response parsing, consensus mode controls. | `src/llm_client.py:26`, `src/llm_client.py:133`, `src/llm_client.py:207` |
| `src/confidence.py` | Confidence math and review threshold decisions. | `src/confidence.py:22`, `src/confidence.py:73`, `src/confidence.py:117` |
| `src/name_matcher.py` | Name normalization, fuzzy matching, GAL replacement metadata, mismatch reasoning. | `src/name_matcher.py:23`, `src/name_matcher.py:137`, `src/name_matcher.py:249` |
| `src/course_name_corrector.py` | Canonical certificate-type normalization against known names. | `src/course_name_corrector.py:15`, `src/course_name_corrector.py:122` |
| `tests/` | Behavioral guardrails for pipeline paths, template matching, zone behavior, and name mismatch workflows. | `tests/test_pipeline_branching.py:2`, `tests/test_visual_template_matching.py:2`, `tests/test_zone_extraction.py:2`, `tests/test_name_mismatch_handling.py:2` |

## Data Flow (Inputs -> Processing -> Outputs)

1. Input job arrives on Redis list `extraction_tasks`; worker deserializes task JSON containing `document_id`.
  Evidence: `src/worker.py:363`, `src/worker.py:367`, `src/worker.py:126`.
2. Worker loads document and employee context from repository and file bytes from storage.
  Evidence: `src/worker.py:143`, `src/worker.py:149`, `src/worker.py:175`.
3. Pipeline normalizes bytes, selects extraction path (template vs fallback), and extracts fields.
  Evidence: `src/pipeline.py:89`, `src/pipeline.py:97`, `src/pipeline.py:162`.
4. OCR interactions occur through Redis OCR protocol where needed.
  Evidence: `src/pipeline.py:140`, `src/ocr_client.py:66`, `src/ocr_client.py:69`.
5. Post-processing applies course-name correction, computes review flags, and serializes extraction fields.
  Evidence: `src/pipeline.py:171`, `src/pipeline.py:179`, `src/pipeline.py:201`.
6. Worker applies GAL name authority metadata and intake-channel mismatch policy, then persists extraction results/state transitions.
  Evidence: `src/worker.py:184`, `src/worker.py:216`, `src/worker.py:262`, `src/worker.py:299`.
7. Optional image-to-PDF conversion is performed for image uploads before final commit.
  Evidence: `src/worker.py:312`, `src/worker.py:323`, `src/worker.py:336`.

## Configuration Model (Files / Env / Flags)

- File-based dependency configuration:
  - `requirements.txt` lists Python package dependencies.
  - Evidence: `requirements.txt:1`.
- Environment-based runtime configuration:
  - Worker connectivity/config: `REDIS_URL`, `DATABASE_URL`, `TEMPLATES_DIR`.
  - Storage credentials/config consumed by `shared.storage`: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, optional `MINIO_SECURE`.
  - LLM runtime controls: `OLLAMA_URL`, `LLM_*` settings.
  - GPU override: `GPU_VRAM_MB`.
  - Evidence: `src/worker.py:389`, `src/worker.py:390`, `src/worker.py:394`, `src/worker.py:136`, `../../CoreInstances/ApiServer/src/shared/storage.py:35`, `../../CoreInstances/ApiServer/src/shared/storage.py:39`, `../../CoreInstances/ApiServer/src/shared/storage.py:43`, `../../CoreInstances/ApiServer/src/shared/storage.py:46`, `src/llm_client.py:26`, `src/llm_client.py:30`, `src/gpu_detect.py:82`.
- Repository-level compose wiring (outside this directory) mounts:
  - worker source at `/app/src`,
  - shared models/utilities at `/app/shared`,
  - templates at `/app/templates`.
  - Evidence: `../../docker-compose.yml:242`, `../../docker-compose.yml:243`, `../../docker-compose.yml:244`.
- Worker entrypoint has no command-line flag parser; runtime configuration is environment-driven in `async_main()` (`REDIS_URL`, `DATABASE_URL`, `TEMPLATES_DIR`).
  - Evidence: `src/worker.py:387`, `src/worker.py:389`, `src/worker.py:390`, `src/worker.py:394`.

## Interfaces and Contract Boundaries

- Internal model and repository/storage contracts are imported from external `shared.*` modules, not defined locally.
  - Evidence: `src/pipeline.py:21`, `src/pipeline.py:31`, `src/worker.py:135`, `src/worker.py:136`.
- Redis queue/key contract is explicit in this directory:
  - `extraction_tasks` for job intake.
  - `ocr_tasks` + `ocr_results:{request_id}` for OCR RPC.
  - Evidence: `src/worker.py:363`, `src/ocr_client.py:66`, `src/ocr_client.py:69`.
- Template contract source files live outside this directory in `CoreInstances/ApiServer/templates/*.json`, with structure enforced by `JsonTemplateRegistry` parse/validation rules.
  - Evidence: `../../CoreInstances/ApiServer/templates/demo_cert.json:1`, `../../CoreInstances/ApiServer/templates/lms_certificate.json:1`, `../../CoreInstances/ApiServer/src/shared/template_registry.py:58`, `../../CoreInstances/ApiServer/src/shared/template_registry.py:112`, `../../CoreInstances/ApiServer/src/shared/template_registry.py:179`.

## Extension Points

- Add or adjust extraction templates:
  - Provide template data in `TEMPLATES_DIR` consumed by `JsonTemplateRegistry`.
  - Evidence: `src/pipeline.py:60`, `src/pipeline.py:65`.
- Customize OCR behavior:
  - Inject alternative OCR clients into `ExtractionPipeline` / `ZoneExtractor` and/or add handwriting OCR client.
  - Evidence: `src/pipeline.py:50`, `src/pipeline.py:69`, `src/zone_extract.py:32`.
- Extend generic extraction patterns:
  - Supply custom `patterns` to `GenericExtractor`.
  - Evidence: `src/generic_extract.py:201`.
- Tune LLM behavior:
  - Adjust `LLM_*` env vars and parallel consensus overrides.
  - Evidence: `src/llm_client.py:26`, `src/llm_client.py:30`, `src/llm_client.py:40`.
- Evolve review policy:
  - Update confidence/review thresholds logic in `confidence.py`.
  - Evidence: `src/confidence.py:62`, `src/confidence.py:73`.
