# FrontendWebServer

Purpose

- Web UI for employees, reviewers, admins, and managers.

Directory overview

- Entrypoint: `index.html` -> `src/main.tsx`.
- Route composition and role gating: `src/App.tsx`.
- API layer and contracts: `src/api/`.
- Route-level screens: `src/pages/`.

Documentation

- Docs hub: `docs/README.md`
- Structure map: `docs/DIRECTORY_MAP.md`
- Operations guide: `docs/OPERATIONS.md`
- Architecture: `docs/ARCHITECTURE.md`

Quickstart

```bash
npm install
npm run dev
```

Containerized (from repository root)

```bash
cd ../..
make up
make logs-frontend
```
