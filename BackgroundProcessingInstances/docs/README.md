# Background Processing Docs (Scoped)

This docs set covers only:

- `BackgroundProcessingInstances/EmailIntakeWorker`
- `BackgroundProcessingInstances/ExtractionWorker`
- `BackgroundProcessingInstances/OcrEngine`

Workers outside this list are intentionally excluded.

## Runtime Responsibilities

| Responsibility | Owner |
| --- | --- |
| Poll inbox and ingest attachments | `EmailIntakeWorker/src/worker.py` |
| Enqueue extraction requests | `EmailIntakeWorker/src/worker.py`, `CoreInstances/ApiServer/src/routes/documents.py` |
| Execute extraction pipeline | `ExtractionWorker/src/worker.py`, `ExtractionWorker/src/pipeline.py` |
| Request OCR and merge OCR output | `ExtractionWorker/src/ocr_client.py`, `ExtractionWorker/src/worker.py` |
| Perform OCR task execution | `OcrEngine/src/worker.py` |

## Quick Entrypoints

- Email intake: `python -m EmailIntakeWorker.src.worker`
- Extraction: `python -m ExtractionWorker.src.worker`
- OCR: `python -m OcrEngine.src.worker`

## Related Docs

- `./DIRECTORY_MAP.md`
- `./ARCHITECTURE.md`
- `./OPERATIONS.md`
