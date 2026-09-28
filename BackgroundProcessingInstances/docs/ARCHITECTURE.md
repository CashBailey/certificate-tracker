# Background Worker Architecture (Scoped)

Scope:

- `EmailIntakeWorker`
- `ExtractionWorker`
- `OcrEngine`

## Worker Interaction Diagram

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

## Responsibilities

| Worker | Core behavior |
| --- | --- |
| `EmailIntakeWorker` | Intake from IMAP, sender/domain checks, attachment validation, extraction enqueue |
| `ExtractionWorker` | Pull extraction jobs, orchestrate template/generic extraction, OCR delegation |
| `OcrEngine` | Process OCR jobs and return OCR output payloads |

## Shared Dependencies

- Redis: queue transport and OCR request/response coordination.
- PostgreSQL: persistence for extracted/request state.
- MinIO: document object storage.

## Queue Contracts

- `extraction_tasks`: produced by API/email intake, consumed by extraction.
- `ocr_tasks`: produced by extraction, consumed by OCR engine.
- `ocr_results:<request_id>`: produced by OCR engine, consumed by extraction.

## Notes

This document intentionally omits background services outside this scope.
