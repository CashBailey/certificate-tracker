# D11 — Review Detail Rendering Flow

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

ID: D11
TITLE: Frontend Flow — Review Detail Rendering
SUBTITLE: Data load, evidence mapping, and review action
CANVAS: 2600x1625
LAYOUT: Linear flow with final branch

NODES:
- [Service] ReviewDetailPage
- [Service] getExtraction(id)
- [Service] build document URL\n(getDocumentContentUrl)
- [Service] map field evidence/bboxes\nto highlights
- [Service] DocumentViewer render +\nFieldEditor corrections
- [Service] approveExtraction
- [Service] rejectExtraction

EDGES:
1) ReviewDetailPage -> getExtraction(id)
2) getExtraction(id) -> build document URL\n(getDocumentContentUrl)
3) build document URL\n(getDocumentContentUrl) -> map field evidence/bboxes\nto highlights
4) map field evidence/bboxes\nto highlights -> DocumentViewer render +\nFieldEditor corrections
5) DocumentViewer render +\nFieldEditor corrections -> approveExtraction
6) DocumentViewer render +\nFieldEditor corrections -> rejectExtraction
```

## Generated Output

![D11 diagram](D11_review_detail_rendering_flow.png)
