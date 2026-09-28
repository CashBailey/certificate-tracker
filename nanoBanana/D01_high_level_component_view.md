# D01 — High-Level Component View

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

ID: D01
TITLE: City of Laredo Scoped Platform — High-Level Component View
SUBTITLE: Frontend, API, ingestion, extraction, OCR, and core data services
CANVAS: 3200x2000
LAYOUT: 4 horizontal lanes (UI, Core Services, Workers, Data/Queues)

NODES:
- [External] Browser\n(FrontendWebServer)
- [Service] ApiServer\n(FastAPI)
- [Service] EmailIntakeWorker
- [Service] ExtractionWorker\n(extraction_tasks)
- [Service] OcrEngine\n(ocr_tasks / ocr_results:<request_id>)
- [Data] PostgreSQL\n(state)
- [Data] MinIO\n(document objects)
- [Data] Redis\n(queues)
- [External] IMAP inbox\npolling

EDGES:
1) Browser\n(FrontendWebServer) -> ApiServer\n(FastAPI) | HTTPS/API
2) ApiServer\n(FastAPI) -> Redis\n(queues) | enqueue extraction_tasks
3) Redis\n(queues) -> ExtractionWorker\n(extraction_tasks) | consume extraction_tasks
4) ExtractionWorker\n(extraction_tasks) -> OcrEngine\n(ocr_tasks / ocr_results:<request_id>) | send ocr_tasks
5) OcrEngine\n(ocr_tasks / ocr_results:<request_id>) -> ExtractionWorker\n(extraction_tasks) | return ocr_results:<request_id>
6) ApiServer\n(FastAPI) -> PostgreSQL\n(state) | read/write
7) ApiServer\n(FastAPI) -> MinIO\n(document objects) | store/retrieve docs
8) IMAP inbox\npolling -> EmailIntakeWorker | inbox intake
9) EmailIntakeWorker -> PostgreSQL\n(state) | metadata writes
10) EmailIntakeWorker -> MinIO\n(document objects) | attachment storage
11) EmailIntakeWorker -> Redis\n(queues) | enqueue extraction_tasks
```

## Generated Output

![D01 diagram](D01_high_level_component_view.png)
