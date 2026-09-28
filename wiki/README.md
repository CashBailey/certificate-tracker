# Project Wiki (HTML)

This folder contains a browser-navigable wiki generated from repository Markdown files that match the current scoped documentation allowlist.

## Build / Rebuild

From repository root:

```bash
make wiki
```

or:

```bash
python3 scripts/build_wiki.py
```

## Open

Open this file in your browser:

```text
wiki/index.html
```

## Scope

The generated wiki indexes the following documentation areas. Path prefixes
(everything under that path is included):

- `docs/`
- `BackgroundProcessingInstances/docs/`
- `BackgroundProcessingInstances/EmailIntakeWorker/docs/`
- `BackgroundProcessingInstances/SchedulerNotificationWorker/docs/`
- `BackgroundProcessingInstances/OcrEngine/docs/`
- `BackgroundProcessingInstances/ExtractionWorker/docs/`
- `CoreInstances/docs/`
- `CoreInstances/ApiServer/docs/`
- `CoreInstances/FrontendWebServer/docs/`
- `nanoBanana/`
- `Storyboard/`
- `StorageConfigurationInstances/`
- `ExternalSharedInstances/`

Plus these individually-allowlisted top-level and per-instance README files:

- `README.md`
- `HighLevelDesignSpecification.md`
- `DOCKER.md`
- `OPEN_ISSUES.md`
- `BackgroundProcessingInstances/README.md`
- `BackgroundProcessingInstances/EmailIntakeWorker/README.md`
- `BackgroundProcessingInstances/SchedulerNotificationWorker/README.md`
- `BackgroundProcessingInstances/OcrEngine/README.md`
- `BackgroundProcessingInstances/ExtractionWorker/README.md`
- `CoreInstances/README.md`
- `CoreInstances/ApiServer/README.md`
- `CoreInstances/FrontendWebServer/README.md`

Diagram images are rendered from `nanoBanana/D{NN}_*.md` files, each of which
embeds its corresponding `nanoBanana/D{NN}_*.png` via a `## Generated Output`
section.
