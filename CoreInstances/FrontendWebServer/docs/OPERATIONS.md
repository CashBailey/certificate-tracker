# Operations Guide

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Setup Prerequisites
- Node.js runtime: required; this directory does not constrain local version with an `engines` field.  
  Evidence: `package.json`.
- Containerized frontend build/runtime images use Node `20-alpine`.  
  Evidence: `../../docker/frontend/Dockerfile`, `../../docker/frontend/Dockerfile.dev`.
- npm CLI: required (`package-lock.json` is present and scripts are npm-centric).  
  Evidence: `package-lock.json`, `package.json`.
- Backend API endpoint reachable by this frontend (default fallback is `/api` (relative) when `VITE_API_URL` is unset).  
  Evidence: `src/api/client.ts`, `src/api/auth.ts`, `src/api/index.ts`.

## Install
```bash
npm install
```
Evidence: dependency manifests in `package.json` and `package-lock.json`.

## Run Modes
| Mode | Command | What It Does | Evidence |
|---|---|---|---|
| Development | `npm run dev` | Starts Vite dev server (`vite`). | `package.json` |
| Build | `npm run build` | Type-check/build pipeline (`tsc && vite build`). | `package.json` |
| Preview | `npm run preview` | Serves built output with Vite preview server. | `package.json` |

## Repository-Level Container Run Modes
Run these from repository root (`../../` relative to this directory).

| Mode | Command | What It Does | Evidence |
|---|---|---|---|
| Full local stack (dev) | `cd ../.. && make up` | Starts `frontend` + backend/infrastructure services via compose. | `../../Makefile`, `../../docker-compose.yml` |
| Frontend logs | `cd ../.. && make logs-frontend` | Follows frontend container logs. | `../../Makefile` |
| Frontend shell | `cd ../.. && make shell-frontend` | Opens shell in frontend container. | `../../Makefile` |
| Production-like stack | `cd ../.. && docker compose -f docker-compose.prod.yml up -d` | Runs prebuilt images including `laredo-certs/frontend:latest`. | `../../docker-compose.prod.yml` |

## Common Task Runbook
| Task | Command(s) | Evidence |
|---|---|---|
| Install deps | `npm install` | `package.json`, `package-lock.json` |
| Start local dev server | `npm run dev` | `package.json` |
| Produce production bundle | `npm run build` | `package.json` |
| Preview built bundle | `npm run preview` | `package.json` |
| Lint TS/TSX sources | `npm run lint` | `package.json` |

Additional dev-server behavior:
- Host bound to `0.0.0.0`.
- Port set to `3000`.
- File watching uses polling (`watch.usePolling: true`).

Evidence: `vite.config.ts`.

## Testing
- Automated test command: none defined in this directory (`package.json` has no `test` script).
- Test files/config in this directory: none found (`*.test.*`, `*.spec.*`, `vitest/jest/playwright` configs not present).
- Repository CI workflow currently targets `CoreInstances/ApiServer` jobs and Docker API build checks; no dedicated frontend lint/test job block was found.

Evidence: `package.json`, source tree inventory under `src/`, `../../.github/workflows/ci.yml`.

## Lint / Format
- Lint command:
```bash
npm run lint
```
- Lint implementation:
```text
eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0
```
Evidence: `package.json`.

Notes:
- No local ESLint config file was found in this directory (for example `.eslintrc*` or `eslint.config.*`), so final lint behavior may depend on inherited config or may fail if none exists upstream.  
  Evidence: file inventory in current directory.
- No formatter script was found in `package.json`.  
  Evidence: `package.json`.
- Repository root `make lint` runs backend `ruff` checks (not frontend ESLint).
  Evidence: `../../Makefile`.

## Build / Release
- Build artifact generation is defined via `npm run build` only (`tsc` + `vite build`).  
  Evidence: `package.json`.
- This directory has no local Docker/compose files, but repository-level files provide frontend build/deploy paths:
  - Dev image/build context: `../../docker/frontend/Dockerfile.dev`, `../../docker-compose.yml`.
  - Production image/runtime: `../../docker/frontend/Dockerfile`, `../../docker/frontend/nginx.conf`, `../../docker-compose.prod.yml`.
  Evidence: top-level file inventory (current directory), `../../docker/frontend/Dockerfile.dev`, `../../docker/frontend/Dockerfile`, `../../docker/frontend/nginx.conf`, `../../docker-compose.yml`, `../../docker-compose.prod.yml`.

## Environment Variables
| Name | Required | Default | Where Used |
|---|---|---|---|
| `VITE_API_URL` | No (runtime fallback exists) | `/api` (relative) | `src/api/client.ts`, `src/api/auth.ts`, `src/api/index.ts` |
| `VITE_INACTIVITY_TIMEOUT_MINUTES` | No | `30` | Minutes of inactivity before auto-logout fires. Warning modal appears 60 s before timeout. Evidence: `src/contexts/AuthContext.tsx`. |

Repository-level compose variables that affect frontend container wiring:

| Name | Required | Default | Where Used |
|---|---|---|---|
| `FRONTEND_PORT` | No | `3000` (dev compose), `80` (prod compose) | Frontend service port mapping. (`../../docker-compose.yml`, `../../docker-compose.prod.yml`) |
| `API_PORT` | No | unused | No longer used to construct `VITE_API_URL`; Caddy proxies `/api/` to the API container. (`../../docker-compose.yml`) |

Additional config notes:
- `src/vite-env.d.ts` types `VITE_API_URL` as present in `ImportMetaEnv`, but runtime code still includes a fallback URL.
- Production nginx container routes `/api/` to `api:8000`; production frontend builds can align `VITE_API_URL` with `/api` when this proxy path is used.
Evidence: `src/vite-env.d.ts`, `src/api/client.ts`, `../../docker/frontend/nginx.conf`.

## Operational Behavior Notes
- Auth session model uses an in-memory access token and refresh via cookie-backed `/auth/refresh` calls with `credentials: include`.
Evidence: `src/api/client.ts`, `src/api/auth.ts`, `src/contexts/AuthContext.tsx`.
- 401 responses trigger token refresh retry logic; on failed refresh, the app dispatches `auth:logout` and raises a "Session expired" error.
Evidence: `src/api/client.ts`, `src/contexts/AuthContext.tsx`.
- Route-level access control uses `ProtectedRoute` with role checks and redirects to `/login` or `/unauthorized`.
Evidence: `src/components/ProtectedRoute.tsx`, `src/App.tsx`.

## I/O Paths And Runtime Side Effects
- Upload input: user-selected file from browser is validated client-side and posted as `FormData` to document endpoints.
Evidence: `src/pages/UploadPage.tsx`, `src/api/index.ts`.
- Download output: requirements CSV and report XLSX files are generated/downloaded in-browser via `Blob` + `URL.createObjectURL`.
Evidence: `src/pages/RequirementsPage.tsx`, `src/api/index.ts`.
- Static asset reads: branding images are loaded from `public/logos/`.
Evidence: `public/logos/`, `src/pages/LoginPage.tsx`, `src/components/Header.tsx`.
- Browser persistence: theme preference is stored in `localStorage` key `theme`.
Evidence: `index.html`, `src/contexts/ThemeContext.tsx`.
- Local filesystem logs/output folders: none declared by scripts or config in this directory.
Evidence: `package.json`, top-level file inventory.

## Troubleshooting (Evidence-Backed)
1. Symptom: immediate API failures or login failure in local dev.
- Check `VITE_API_URL` target and backend availability; frontend falls back to `/api` (relative) if unset. Ensure Caddy is running.
- Evidence: `src/api/client.ts`, `src/api/auth.ts`, `src/api/index.ts`.

2. Symptom: API calls fail in production container deployment while frontend loads.
- Ensure production build sets API base consistent with nginx proxy path (`/api`) or another reachable backend URL.
- Evidence: `../../docker/frontend/nginx.conf`, `src/api/client.ts`.

3. Symptom: user gets logged out during normal navigation.
- Likely cause is refresh failure (`/auth/refresh` non-OK or network error), which clears token and emits `auth:logout`.
- Evidence: `src/api/client.ts`, `src/contexts/AuthContext.tsx`.

4. Symptom: PDF preview fails in review detail.
- `DocumentViewer` configures PDF worker from `//unpkg.com/pdfjs-dist@...`; network/CSP blocking of that URL can break loading.
- Evidence: `src/components/DocumentViewer.tsx`.

5. Symptom: upload button disabled or upload rejected.
- Upload flow enforces MIME allowlist (`pdf/jpeg/png/tiff`) and 20MB max before API upload.
- Evidence: `src/pages/UploadPage.tsx`.

6. Symptom: template save is rejected.
- Save requires non-empty template ID/name, at least one zone, all canonical fields present, and template ID matching `^[a-z0-9_]+$`.
- Evidence: `src/pages/TemplateEditorPage.tsx`.

7. Symptom: requirements page shows stale data after uploads/reviews.
- Requirements page caches data in module-level `_cache`; related flows explicitly call `invalidateRequirementsCache()`.
- Evidence: `src/pages/RequirementsPage.tsx`, `src/pages/UploadPage.tsx`, `src/pages/ReviewDetailPage.tsx`.

## Security / Data Handling Notes
- Access tokens are intentionally kept in memory only (not persisted).
- Refresh token is expected via httpOnly cookie (frontend never reads it directly).
- Document content URL helper can append bearer token as query parameter for viewer compatibility.
- API errors are surfaced to UI as sanitized message strings (usually `detail` fallback), not raw stack traces.

Evidence: `src/api/client.ts`, `src/api/auth.ts`, `src/api/index.ts`, `src/pages/LoginPage.tsx`, `src/pages/RequirementsPage.tsx`, `src/pages/EmployeesPage.tsx`.
