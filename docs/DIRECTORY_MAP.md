# Directory Map (Scoped)

This map is intentionally constrained to the approved documentation scope.

## Rendered Tree (Scoped)

```text
.
├── CoreInstances/
│   ├── README.md
│   ├── docs/
│   ├── ApiServer/
│   │   ├── README.md
│   │   ├── docs/
│   │   ├── src/
│   │   ├── alembic/
│   │   ├── templates/
│   │   └── tests/
│   └── FrontendWebServer/
│       ├── README.md
│       ├── docs/
│       ├── src/
│       ├── public/
│       └── package.json
├── BackgroundProcessingInstances/
│   ├── README.md
│   ├── docs/
│   ├── EmailIntakeWorker/
│   │   ├── README.md
│   │   ├── docs/
│   │   ├── src/
│   │   └── requirements.txt
│   ├── ExtractionWorker/
│   │   ├── README.md
│   │   ├── docs/
│   │   ├── src/
│   │   ├── tests/
│   │   └── requirements.txt
│   └── OcrEngine/
│       ├── README.md
│       ├── docs/
│       ├── src/
│       └── requirements.txt
└── docs/
```

## Path Purpose Table

| Path | Purpose |
| --- | --- |
| `CoreInstances/ApiServer` | FastAPI backend, auth, schemas, migrations, storage/queue orchestration |
| `CoreInstances/FrontendWebServer` | React frontend UI and API client integration |
| `BackgroundProcessingInstances/EmailIntakeWorker` | Email ingestion and extraction task creation |
| `BackgroundProcessingInstances/ExtractionWorker` | Extraction orchestration and OCR handoff |
| `BackgroundProcessingInstances/OcrEngine` | OCR queue processing and result publishing |
| `docs/` | Root scoped docs pack for these components |

## Key Interfaces

- HTTP API: `CoreInstances/ApiServer/src/routes/`
- Queue interfaces:
  - `extraction_tasks`
  - `ocr_tasks`
  - `ocr_results:<request_id>`
- Worker entrypoints:
  - `BackgroundProcessingInstances/EmailIntakeWorker/src/worker.py`
  - `BackgroundProcessingInstances/ExtractionWorker/src/worker.py`
  - `BackgroundProcessingInstances/OcrEngine/src/worker.py`

## Scope Guardrail

This file intentionally excludes non-scoped folders and services.
