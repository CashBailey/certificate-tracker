# BackgroundProcessingInstances Directory Map (Scoped)

## Tree (Scoped)

```text
BackgroundProcessingInstances/
├── README.md
├── docs/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── OPERATIONS.md
│   └── DIRECTORY_MAP.md
├── EmailIntakeWorker/
│   ├── README.md
│   ├── docs/
│   ├── src/
│   └── requirements.txt
├── ExtractionWorker/
│   ├── README.md
│   ├── docs/
│   ├── src/
│   ├── tests/
│   └── requirements.txt
└── OcrEngine/
    ├── README.md
    ├── docs/
    ├── src/
    └── requirements.txt
```

## Path Purpose Table

| Path | Purpose |
| --- | --- |
| `EmailIntakeWorker/src/` | Email polling, validation, attachment intake, extraction task creation |
| `ExtractionWorker/src/` | Extraction orchestration, template pipeline, OCR handoff |
| `OcrEngine/src/` | OCR queue processing and OCR result publication |
| `docs/` | Scoped docs for these workers only |

## Queue Hotspots

- `EmailIntakeWorker/src/worker.py`: publishes `extraction_tasks`.
- `ExtractionWorker/src/worker.py`: consumes `extraction_tasks`, publishes/awaits OCR tasks/results.
- `OcrEngine/src/worker.py`: consumes `ocr_tasks`, publishes `ocr_results:<request_id>`.

## Scope Guardrail

Any non-listed worker is intentionally excluded.
