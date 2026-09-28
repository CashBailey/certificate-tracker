# Scoped Documentation (Core + Selected Workers)

This documentation set is intentionally limited to the following repository areas:

- `CoreInstances/`
- `CoreInstances/ApiServer/`
- `CoreInstances/FrontendWebServer/`
- `BackgroundProcessingInstances/`
- `BackgroundProcessingInstances/EmailIntakeWorker/`
- `BackgroundProcessingInstances/ExtractionWorker/`
- `BackgroundProcessingInstances/OcrEngine/`

Out-of-scope folders and services are intentionally excluded from this docs pack.

## Primary References

- Structure map: [`./DIRECTORY_MAP.md`](./DIRECTORY_MAP.md)
- Runtime architecture: [`./ARCHITECTURE.md`](./ARCHITECTURE.md)
- Setup and operations: [`./OPERATIONS.md`](./OPERATIONS.md)

## System Summary (Scoped)

Within this scope, the system covers:

- `CoreInstances/FrontendWebServer`: browser UI for upload/review flows.
- `CoreInstances/ApiServer`: HTTP API, auth, persistence orchestration, queue enqueue.
- `BackgroundProcessingInstances/EmailIntakeWorker`: IMAP ingestion and document intake.
- `BackgroundProcessingInstances/ExtractionWorker`: extraction orchestration and OCR delegation.
- `BackgroundProcessingInstances/OcrEngine`: OCR task execution and result publishing.

## Key Shared Runtime Dependencies

- `postgres` for relational state
- `redis` for task queues and coordination
- `minio` for document object storage

These dependencies are referenced only as needed by the scoped components above.
