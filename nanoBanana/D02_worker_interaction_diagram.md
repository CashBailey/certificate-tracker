# D02 — Worker Interaction Diagram

```text
SYSTEM ROLE:
You are a senior information designer generating one enterprise architecture/flow diagram.

HARD OUTPUT RULES:
- Output exactly ONE diagram image (no collage, no variants, no watermark).
- Style: clean flat vector, professional consulting-deck quality.
- No 3D, no photos, no clipart, no skeuomorphism.
- Background: pure white (#FFFFFF).
- Aspect: 16:10.
- If text overflow risk exists, increase canvas before reducing font size.

CANVAS TIERS:
- Default: 2800x1750
- If overflow persists: 3200x2000
- Never go below 2400x1500
- Never reduce body font below 16 px

TYPOGRAPHY:
- Sans-serif (Inter/Helvetica/Roboto style)
- Title: 48 px semibold
- Subtitle: 26 px regular
- Node title/body: 20/17 px
- Edge labels: 16 px
- Text color primary #111111, secondary #444444

VISUAL TOKENS:
- Border stroke: #1F1F1F (1.6 px)
- Connector stroke: #2A2A2A (1.6 px), orthogonal routing only
- Arrowheads: filled, clear direction
- External actor fill: #F7F7F7
- Service/worker fill: #ECECEC
- Data store/queue fill: #E2E2E2
- Decision fill: #F1F1F1
- Annotation fill: #FAFAFA
- Corner radius: 12 px
- Minimal shadow only if needed for separation

LAYOUT CONSTRAINTS:
- Outer margin: 96 px
- Min node-to-node gap: 56 px
- Min lane gap: 72 px
- Keep labels fully visible; wrap text intentionally using provided line breaks.
- Avoid line crossings. If crossing risk appears, reroute connectors with elbows.

LEGEND (bottom-right, fixed text):
- External
- Service / Worker
- Data / Queue
- Decision (when present)

STRICT CONTENT RULES:
- Use exact node names and exact edge labels from the spec.
- Do not rename, abbreviate, or invent components.
- Do not add extra nodes unless explicitly listed as annotations.
- Keep title and subtitle exact.

FINAL QA (must pass):
1) No overlaps
2) No clipped text
3) No ambiguous arrows
4) Every listed node appears once
5) Every listed edge appears once

ID: D02
TITLE: Background Workers — Interaction Diagram
SUBTITLE: Email intake, extraction, OCR queues, and result handoff
CANVAS: 2800x1750
LAYOUT: Left-to-right process, queue channels centered

NODES:
- [External] IMAP Inbox
- [Service] EmailIntakeWorker
- [Data] Redis queue:\nextraction_tasks
- [Service] ExtractionWorker
- [Data] OCR request queue:\nocr_tasks
- [Data] OCR result key/channel:\nocr_results:<request_id>
- [Service] OcrEngine
- [Data] PostgreSQL / MinIO\npersistence
- [Data] PostgreSQL state\nupdates

EDGES:
1) IMAP Inbox -> EmailIntakeWorker | poll + ingest
2) EmailIntakeWorker -> PostgreSQL / MinIO\npersistence | persist docs + metadata
3) EmailIntakeWorker -> Redis queue:\nextraction_tasks | enqueue
4) Redis queue:\nextraction_tasks -> ExtractionWorker | consume
5) ExtractionWorker -> OCR request queue:\nocr_tasks | enqueue OCR
6) OCR request queue:\nocr_tasks -> OcrEngine | consume
7) OcrEngine -> OCR result key/channel:\nocr_results:<request_id> | publish
8) OCR result key/channel:\nocr_results:<request_id> -> ExtractionWorker | retrieve
9) ExtractionWorker -> PostgreSQL state\nupdates | persist extraction/review state
```

## Generated Output

![D02 diagram](D02_worker_interaction_diagram.png)
