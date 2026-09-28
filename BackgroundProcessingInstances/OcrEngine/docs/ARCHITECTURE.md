# Architecture

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.

## High-Level Overview
`OcrEngine` is a Redis-backed OCR worker. It receives OCR requests (serialized page image + normalized bounding box), runs OCR on the requested region, and stores serialized spans keyed by request ID for short-lived retrieval. Evidence: `src/worker.py:142`, `src/worker.py:152`, `src/worker.py:161`, `src/worker.py:165`, `src/ocr_service.py:168`, `src/ocr_service.py:218`.

The primary caller is `RedisOcrClient` in `ExtractionWorker`, which enqueues requests to `ocr_tasks`, polls `ocr_results:{request_id}`, and deletes the result key after consuming it. Evidence: `../ExtractionWorker/src/ocr_client.py:66`, `../ExtractionWorker/src/ocr_client.py:69`, `../ExtractionWorker/src/ocr_client.py:79`.

## Component Diagram

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

Evidence: `../ExtractionWorker/src/ocr_client.py:66`, `../ExtractionWorker/src/ocr_client.py:76`, `../ExtractionWorker/src/ocr_client.py:79`, `src/worker.py:183`, `src/worker.py:142`, `src/worker.py:152`, `src/worker.py:161`, `src/worker.py:165`.

## Entrypoints
| Entrypoint | Kind | Use when | Evidence |
|---|---|---|---|
| `python -m src.worker` | Runtime process | Running OCR worker loop | `src/worker.py:202`, `src/worker.py:232` |
| `ocr-engine` compose service | Runtime process (containerized) | Running in project stack with Redis/MinIO/shared wiring | `../../docker-compose.yml:261`, `../../docker-compose.yml:279` |
| `TesseractOcrService` | Library class | Tesseract OCR in-process usage | `src/ocr_service.py:17` |
| `EasyOcrService` | Library class | EasyOCR in-process usage | `src/easyocr_service.py:17` |
| `EnsembleOcrEngine` | Library class | Confidence-based engine selection | `src/ensemble_ocr.py:18`, `src/ensemble_ocr.py:53` |

## Module Responsibilities
| Module | Responsibility | Evidence |
|---|---|---|
| `src/worker.py` | Worker lifecycle, Redis polling, warmup, failure handling, result publishing | `src/worker.py:97`, `src/worker.py:103`, `src/worker.py:176` |
| `src/ocr_service.py` | Tesseract OCR and request/result serialization contract | `src/ocr_service.py:35`, `src/ocr_service.py:150`, `src/ocr_service.py:207` |
| `src/easyocr_service.py` | EasyOCR region/full-page/string extraction | `src/easyocr_service.py:37`, `src/easyocr_service.py:111`, `src/easyocr_service.py:126` |
| `src/ensemble_ocr.py` | Compare engine outputs by average confidence | `src/ensemble_ocr.py:11`, `src/ensemble_ocr.py:50`, `src/ensemble_ocr.py:53` |

## Data Flow
1. ExtractionWorker serializes request data and pushes it to `ocr_tasks`.
2. OcrEngine worker blocks on `ocr_tasks`, deserializes payload, and executes OCR.
3. Worker serializes result spans and stores them in `ocr_results:{request_id}` with TTL 300.
4. ExtractionWorker polls and consumes result key, then deletes it.

Evidence:
- Producer: `../ExtractionWorker/src/ocr_client.py:63`, `../ExtractionWorker/src/ocr_client.py:66`.
- Consumer: `src/worker.py:183`, `src/worker.py:142`, `src/worker.py:152`.
- Result write: `src/worker.py:162`, `src/worker.py:165`.
- Result consume/delete: `../ExtractionWorker/src/ocr_client.py:76`, `../ExtractionWorker/src/ocr_client.py:79`.

## Engine Selection Model

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

Evidence: `src/worker.py:80`, `src/worker.py:86`, `src/worker.py:92`, `src/worker.py:95`, `src/ensemble_ocr.py:50`, `src/ensemble_ocr.py:53`.

## Configuration Model
| Source | Keys | Behavior | Evidence |
|---|---|---|---|
| Worker code defaults | `REDIS_URL`, `TESSERACT_LANG` | Connection target + OCR language defaults | `src/worker.py:207`, `src/worker.py:208` |
| Compose env | `REDIS_URL`, `TESSERACT_LANG`, `OCR_QUEUE`, `LOG_LEVEL`, MinIO vars | Runtime container env wiring | `../../docker-compose.yml:268`, `../../docker-compose.yml:272`, `../../docker-compose.yml:273`, `../../docker-compose.yml:274` |
| Dockerfile | `PYTHONPATH=/app`, shared copy, worker CMD | Import path + startup behavior in container | `../../docker/workers/ocr/Dockerfile:9`, `../../docker/workers/ocr/Dockerfile:36`, `../../docker/workers/ocr/Dockerfile:46` |

Note:
- `OCR_QUEUE` is configured in compose but worker currently hardcodes `"ocr_tasks"` in code.
Evidence: `../../docker-compose.yml:273`, `src/worker.py:183`.

## Interface and Contract Notes
- Request payload is JSON bytes containing `request_id`, image bytes (`image_b64`), image dimensions, DPI, and `bbox_norm`.
- Result payload is JSON bytes containing `request_id` and span list with `text`, `bbox_norm`, and `confidence`.
- Data models used by this worker are `PageImage` and `TextSpan` from shared models.

Evidence:
- Request fields: `src/ocr_service.py:168`, `src/ocr_service.py:175`.
- Result fields: `src/ocr_service.py:218`, `src/ocr_service.py:224`.
- Shared model classes: `../../CoreInstances/ApiServer/src/shared/models.py:413`, `../../CoreInstances/ApiServer/src/shared/models.py:422`.

## Extension Points
- Add OCR engine:
  - Implement `ocr_region`.
  - Compose it into `EnsembleOcrEngine` or switch selection in `OcrWorker.__init__`.
 Evidence: `src/worker.py:152`, `src/ensemble_ocr.py:32`, `src/ensemble_ocr.py:55`, `src/ensemble_ocr.py:62`.

- Change queue key strategy:
  - Update hardcoded queue/result key logic in worker and producer client together.
 Evidence: `src/worker.py:183`, `src/worker.py:162`, `../ExtractionWorker/src/ocr_client.py:66`, `../ExtractionWorker/src/ocr_client.py:69`.
