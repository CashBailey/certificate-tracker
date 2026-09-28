# Directory Map

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Tree (Noise Trimmed)
`__pycache__/` was omitted.
```text
.
├── README.md
├── requirements.txt
├── docs
│   ├── ARCHITECTURE.md
│   ├── DIRECTORY_MAP.md
│   ├── OPERATIONS.md
│   └── README.md
└── src
    ├── __init__.py
    ├── easyocr_service.py
    ├── ensemble_ocr.py
    ├── ocr_service.py
    └── worker.py
```
Evidence: `README.md:1`, `requirements.txt:1`, `src/__init__.py:1`, `src/easyocr_service.py:1`, `src/ensemble_ocr.py:1`, `src/ocr_service.py:1`, `src/worker.py:1`.

## Top-Level Anchors
- `README.md`: directory-level purpose and quick start.
- `requirements.txt`: Python dependency manifest for this worker.
- `src/`: runtime implementation.
- `docs/`: developer documentation for this directory.
Evidence: `README.md:1`, `requirements.txt:1`, `src/worker.py:1`, `docs/README.md:1`.

## Path Catalog
| Path | Purpose | Key files | Notes |
|---|---|---|---|
| `src/worker.py` | Long-running OCR worker process | `OcrWorker`, `main` | Polls `ocr_tasks`, writes `ocr_results:{request_id}` with TTL 300s. Evidence: `src/worker.py:183`, `src/worker.py:162`, `src/worker.py:165`. |
| `src/ocr_service.py` | Tesseract OCR + request/result serializers | `TesseractOcrService`, `serialize_ocr_request`, `serialize_ocr_result` | Defines JSON wire shape for OCR requests/results. Evidence: `src/ocr_service.py:150`, `src/ocr_service.py:207`. |
| `src/easyocr_service.py` | EasyOCR implementation | `EasyOcrService` | Optional GPU-enabled OCR path. Evidence: `src/easyocr_service.py:23`, `src/easyocr_service.py:34`. |
| `src/ensemble_ocr.py` | Multi-engine selector | `EnsembleOcrEngine` | Chooses result by average confidence. Evidence: `src/ensemble_ocr.py:50`, `src/ensemble_ocr.py:53`. |
| `requirements.txt` | Dependency list | package entries | Standard bounded Tesseract runtime; EasyOCR/Torch are deliberately excluded. |
| `README.md` | Local overview | quickstart links | Directory-focused pointers. Evidence: `README.md:13`. |

## Interface/Contract Files
- Request/response contracts in this directory:
  - `src/ocr_service.py::serialize_ocr_request`
  - `src/ocr_service.py::deserialize_ocr_request`
  - `src/ocr_service.py::serialize_ocr_result`
  - `src/ocr_service.py::deserialize_ocr_result`
  Evidence: `src/ocr_service.py:150`, `src/ocr_service.py:180`, `src/ocr_service.py:207`, `src/ocr_service.py:232`.

## Runtime-Linked External Files
These files are outside this directory but directly affect how it runs.

| Path | Why it matters |
|---|---|
| `../../docker/workers/ocr/Dockerfile` | Pins Python 3.12 image, installs Tesseract packages, copies `shared` and `src`, and starts `python -m src.worker`. Evidence: `../../docker/workers/ocr/Dockerfile:4`, `../../docker/workers/ocr/Dockerfile:13`, `../../docker/workers/ocr/Dockerfile:36`, `../../docker/workers/ocr/Dockerfile:46`. |
| `../../docker-compose.yml` | Defines `ocr-engine` service env and volume wiring, including shared model mount. Evidence: `../../docker-compose.yml:261`, `../../docker-compose.yml:268`, `../../docker-compose.yml:272`, `../../docker-compose.yml:279`. |
| `../../docker-compose.prod.yml` | Production compose expects prebuilt `laredo-certs/ocr-engine:latest` image. Evidence: `../../docker-compose.prod.yml:218`, `../../docker-compose.prod.yml:219`. |
| `../../CoreInstances/ApiServer/src/shared/models.py` | Source of `PageImage`/`TextSpan` imported by this worker. Evidence: `src/ocr_service.py:14`, `../../CoreInstances/ApiServer/src/shared/models.py:413`, `../../CoreInstances/ApiServer/src/shared/models.py:422`. |
| `../ExtractionWorker/src/ocr_client.py` | Producer/consumer counterpart that pushes to `ocr_tasks` and polls `ocr_results:{request_id}`. Evidence: `../ExtractionWorker/src/ocr_client.py:66`, `../ExtractionWorker/src/ocr_client.py:69`, `../ExtractionWorker/src/ocr_client.py:79`. |

## Hotspots
- `src/worker.py`: lifecycle, Redis I/O, warmup, fault handling.
- `src/ocr_service.py`: queue payload contract and OCR result format.
- `src/easyocr_service.py` + `src/ensemble_ocr.py`: accuracy/engine-selection behavior.
Evidence: `src/worker.py:176`, `src/ocr_service.py:150`, `src/easyocr_service.py:37`, `src/ensemble_ocr.py:53`.
