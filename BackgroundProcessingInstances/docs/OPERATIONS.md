# Background Worker Operations (Scoped)

Scope:

- `EmailIntakeWorker`
- `ExtractionWorker`
- `OcrEngine`

## Prerequisites

- Python dependencies from each worker `requirements.txt` (for local runs), or
- Docker Compose services for containerized runs.

## Container Run (Recommended)

From repository root, run only scoped worker services plus dependencies:

```bash
docker compose up -d postgres redis minio email-intake-worker extraction-worker ocr-engine
```

Tail logs:

```bash
docker compose logs -f email-intake-worker extraction-worker ocr-engine
```

## Local Module Run (Optional)

From repository root:

```bash
python -m pip install -r BackgroundProcessingInstances/EmailIntakeWorker/requirements.txt
python -m pip install -r BackgroundProcessingInstances/ExtractionWorker/requirements.txt
python -m pip install -r BackgroundProcessingInstances/OcrEngine/requirements.txt
```

Start workers:

```bash
PYTHONPATH="CoreInstances/ApiServer/src" python -m BackgroundProcessingInstances.EmailIntakeWorker.src.worker
PYTHONPATH="CoreInstances/ApiServer/src" python -m BackgroundProcessingInstances.ExtractionWorker.src.worker
PYTHONPATH="CoreInstances/ApiServer/src" python -m BackgroundProcessingInstances.OcrEngine.src.worker
```

## Environment Variables

| Variable | Worker(s) | Purpose |
| --- | --- | --- |
| `REDIS_URL` | all three | Queue connectivity |
| `DATABASE_URL` | EmailIntake, Extraction | DB access for intake/extraction state |
| `MINIO_*` | EmailIntake, Extraction | Object storage reads/writes |
| `IMAP_*` | EmailIntake | Inbox connectivity |
| `ALLOWED_EMAIL_DOMAIN` | EmailIntake | Sender validation |
| `EMAIL_POLL_INTERVAL_SECONDS` | EmailIntake | Intake poll cadence |
| `TESSERACT_LANG` | OcrEngine | OCR language configuration |
| `LLM_*` | Extraction | Extraction model/consensus behavior |

## Common Failures

- No extraction jobs processed:
  - Confirm `REDIS_URL` connectivity and extraction worker logs.
- OCR roundtrip timeout:
  - Confirm `ocr-engine` is healthy and consuming `ocr_tasks`.
- Email intake idle:
  - Confirm `IMAP_*` credentials and sender domain filtering.

## Out of Scope

Any worker outside these three is intentionally excluded.
