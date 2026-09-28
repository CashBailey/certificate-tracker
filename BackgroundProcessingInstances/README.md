# BackgroundProcessingInstances

Scoped worker documentation for:

- `EmailIntakeWorker`
- `ExtractionWorker`
- `OcrEngine`

Workers not listed above are intentionally out of scope for this documentation set.

## Worker Overview

- `EmailIntakeWorker`: polls IMAP, validates intake, stores documents/metadata, enqueues extraction tasks.
- `ExtractionWorker`: consumes extraction queue, performs extraction pipeline, requests OCR when needed.
- `OcrEngine`: consumes OCR queue and publishes OCR results.

## Local Documentation

- `docs/README.md`
- `docs/ARCHITECTURE.md`
- `docs/OPERATIONS.md`
- `docs/DIRECTORY_MAP.md`
