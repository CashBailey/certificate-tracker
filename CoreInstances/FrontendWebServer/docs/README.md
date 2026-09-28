# Frontend Web Server Docs

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## What This Directory Is
This directory contains a Vite + React + TypeScript single-page frontend for certificate management workflows (login, requirements tracking, upload, review, compliance reporting, templates, and employee management). App composition uses `AuthProvider` + `ThemeProvider` around router routes with role-aware guards.  
Evidence: `package.json`, `src/App.tsx`, `src/contexts/AuthContext.tsx`, `src/contexts/ThemeContext.tsx`, `src/components/ProtectedRoute.tsx`, `src/pages/LoginPage.tsx`, `src/pages/RequirementsPage.tsx`, `src/pages/ReviewDetailPage.tsx`.

## Quick Start (Verified Commands)
### Prerequisites
- Node.js runtime: no explicit `engines` constraint is declared in this directory’s `package.json`.  
  Evidence: `package.json`.
- Dockerized frontend runtime/build image uses Node `20-alpine`.  
  Evidence: `../../docker/frontend/Dockerfile`, `../../docker/frontend/Dockerfile.dev`.
- npm CLI.  
  Evidence: `package-lock.json`, `package.json`.

### Install
```bash
npm install
```
Evidence: `package.json`, `package-lock.json`.

### Local Development
```bash
npm run dev
```
Uses Vite dev server on `0.0.0.0:3000` with polling watch.  
Evidence: `package.json`, `vite.config.ts`.

### Production Build + Local Preview
```bash
npm run build
npm run preview
```
Build runs `tsc && vite build`; preview serves the built output.  
Evidence: `package.json`.

### Lint
```bash
npm run lint
```
Evidence: `package.json`.

### Dockerized Development (Repository-Level)
From repository root:
```bash
cd ../..
make up
make logs-frontend
```
This runs the `frontend` service from `docker-compose.yml`, mounting this directory to `/app` for live Vite development.  
Evidence: `../../Makefile`, `../../docker-compose.yml`, `../../README.md`.

## Entrypoints (How To Choose)
| Entrypoint | When To Use | Evidence |
|---|---|---|
| `index.html` -> `/src/main.tsx` | Browser/runtime bootstrap for all app usage. | `index.html`, `src/main.tsx` |
| Route `/login` | Unauthenticated sign-in flow. | `src/App.tsx`, `src/pages/LoginPage.tsx` |
| Route `/` | Main dashboard for `Coordinator` and `Admin`. | `src/App.tsx`, `src/pages/DashboardPage.tsx` |
| Route `/requirements` | Requirement-level operations (filter/export/upload handoff), `Coordinator` role. | `src/App.tsx`, `src/pages/RequirementsPage.tsx` |
| Route `/upload` | Direct upload flow; supports optional requirement context via query params. | `src/App.tsx`, `src/pages/UploadPage.tsx` |
| Route `/review` and `/review/:id` | Review queue and detail approval/rejection, `Coordinator` role. | `src/App.tsx`, `src/pages/ReviewQueuePage.tsx`, `src/pages/ReviewDetailPage.tsx` |
| Route `/compliance` | Aggregate compliance analytics, `Coordinator` role. | `src/App.tsx`, `src/pages/CompliancePage.tsx` |
| Route `/templates` and `/templates/new` | Template registry and editor, `Coordinator` role. | `src/App.tsx`, `src/pages/TemplatesPage.tsx`, `src/pages/TemplateEditorPage.tsx` |
| Route `/employees` | Employee management for `Coordinator` and `Admin`. | `src/App.tsx`, `src/pages/EmployeesPage.tsx` |

## Key Conventions
- Route authorization is centralized at route declarations using `ProtectedRoute` and `allowedRoles`.  
  Evidence: `src/App.tsx`, `src/components/ProtectedRoute.tsx`.
- API calls are centralized in `src/api/` and use `apiFetch` for auth headers/401 refresh handling where applicable.  
  Evidence: `src/api/client.ts`, `src/api/auth.ts`, `src/api/index.ts`.
- Frontend session model uses in-memory access token + httpOnly refresh cookie workflow.  
  Evidence: `src/api/client.ts`, `src/api/auth.ts`, `src/contexts/AuthContext.tsx`.
- CSS is mostly feature-collocated (`Page.tsx` + `Page.css`, `Component.tsx` + `Component.css`) with shared tokens in `src/styles/tokens.css`.  
  Evidence: `src/pages/UploadPage.tsx`, `src/pages/UploadPage.css`, `src/components/Header.tsx`, `src/components/Header.css`, `src/styles/tokens.css`.

## Where To Look Next
- Structure and hotspots: [`./DIRECTORY_MAP.md`](./DIRECTORY_MAP.md)
- Runbook and troubleshooting: [`./OPERATIONS.md`](./OPERATIONS.md)
- Architecture/data flow details: [`./ARCHITECTURE.md`](./ARCHITECTURE.md)

## Assumptions And Unknowns
- Assumption: canonical operation for this directory is through repository-level compose/make workflows rather than directory-local Docker orchestration.
  Evidence: `../../Makefile`, `../../docker-compose.yml`, `../../docker-compose.prod.yml`.
- Unknown: recommended local (non-Docker) Node version policy is not explicitly pinned by an `engines` field or `.nvmrc`/`.node-version` in scope; repository Dockerfiles use Node 20.
  Evidence: `package.json`, `../../docker/frontend/Dockerfile`, `../../docker/frontend/Dockerfile.dev`.
- Unknown: supported frontend automated test command for this directory; `package.json` has no `test` script and no local test files/configs were found in this directory.  
  Evidence: `package.json`, `src/` file inventory.
- Unknown: dedicated frontend CI lint/test job scope in `.github/workflows/ci.yml`; no frontend-specific job block was found (workflow targets `CoreInstances/ApiServer` jobs and Docker API build check).  
  Evidence: `../../.github/workflows/ci.yml`.
- Known constraint: this directory itself has no local `Dockerfile` or compose file; repository-level container orchestration exists in `../../docker-compose.yml`, `../../docker-compose.prod.yml`, `../../docker/frontend/Dockerfile`, and `../../docker/frontend/Dockerfile.dev`.  
  Evidence: top-level file inventory for current directory, `../../docker-compose.yml`, `../../docker-compose.prod.yml`, `../../docker/frontend/Dockerfile`, `../../docker/frontend/Dockerfile.dev`.
- Unknown: static OpenAPI schema file path in this directory; frontend contract is expressed in `src/api/index.ts` and backend route registration lives in `../../CoreInstances/ApiServer/src/main.py` (API root response includes `docs_url: "/docs"`).
  Evidence: `src/api/index.ts`, `src/types/auth.ts`, `../../CoreInstances/ApiServer/src/main.py`.
