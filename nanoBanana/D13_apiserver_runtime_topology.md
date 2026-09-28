# D13 — ApiServer Deployment/Runtime Topology

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

ID: D13
TITLE: ApiServer — Deployment/Runtime Topology
SUBTITLE: API boundary, dependencies, and extraction queue handoff
CANVAS: 2800x1750
LAYOUT: Centered hub-and-spoke + bottom annotation panel

NODES:
- [External] Client/UI
- [Service] ApiServer FastAPI\n(`src.main:app`)
- [Service] Auth + API Routers
- [Data] SQLAlchemy async repository\n-> PostgreSQL
- [Data] Storage adapter\n-> MinIO
- [Data] Queue handoff\n(`extraction_tasks`) -> Redis
- [Annotation] Compose service wiring:\napi depends_on postgres + redis + minio (healthy)

EDGES:
1) Client/UI -> ApiServer FastAPI\n(`src.main:app`)
2) ApiServer FastAPI\n(`src.main:app`) -> Auth + API Routers
3) ApiServer FastAPI\n(`src.main:app`) -> SQLAlchemy async repository\n-> PostgreSQL
4) ApiServer FastAPI\n(`src.main:app`) -> Storage adapter\n-> MinIO
5) ApiServer FastAPI\n(`src.main:app`) -> Queue handoff\n(`extraction_tasks`) -> Redis
6) Compose service wiring:\napi depends_on postgres + redis + minio (healthy) -> ApiServer FastAPI\n(`src.main:app`) | dashed annotation link
```

## Generated Output

![D13 diagram](D13_apiserver_runtime_topology.png)
