# Directory Map

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.


## Rendered Tree (Noise Trimmed)
Excluded from tree: `node_modules/`, `.vite/`, `dist/`, `build/`, `__pycache__/`.

```text
.
|-- README.md
|-- docs/
|   |-- README.md
|   |-- DIRECTORY_MAP.md
|   |-- OPERATIONS.md
|   `-- ARCHITECTURE.md
|-- index.html
|-- package.json
|-- package-lock.json
|-- public/
|   `-- logos/
|       |-- CityOfLaredoLogo.png
|       `-- CityOfLaredoPublicHealthLogo.png
|-- src/
|   |-- main.tsx
|   |-- App.tsx
|   |-- index.css
|   |-- App.css
|   |-- api/
|   |   |-- client.ts
|   |   |-- auth.ts
|   |   `-- index.ts
|   |-- components/
|   |   |-- Header.tsx
|   |   |-- ProtectedRoute.tsx
|   |   |-- DocumentViewer.tsx
|   |   |-- FieldEditor.tsx
|   |   |-- EmployeeSelectionModal.tsx
|   |   `-- StatusBadge.tsx
|   |-- contexts/
|   |   |-- AuthContext.tsx
|   |   `-- ThemeContext.tsx
|   |-- pages/
|   |   |-- LoginPage.tsx
|   |   |-- DashboardPage.tsx
|   |   |-- RequirementsPage.tsx
|   |   |-- UploadPage.tsx
|   |   |-- ReviewQueuePage.tsx
|   |   |-- ReviewDetailPage.tsx
|   |   |-- CompliancePage.tsx
|   |   |-- TemplatesPage.tsx
|   |   |-- TemplateEditorPage.tsx
|   |   `-- EmployeesPage.tsx
|   |-- styles/
|   |   `-- tokens.css
|   |-- types/
|   |   `-- auth.ts
|   `-- vite-env.d.ts
|-- tsconfig.json
|-- tsconfig.node.json
`-- vite.config.ts
```

Evidence: top-level file inventory and `src/` file inventory in this directory.

## Top-Level Anchors
| Anchor | Status In This Directory | Evidence |
|---|---|---|
| `README*` | Present (`README.md`) | `README.md` |
| `LICENSE*` | Not found | top-level file inventory |
| `CHANGELOG*` | Not found | top-level file inventory |
| `CONTRIBUTING*` | Not found | top-level file inventory |
| `docs/` | Present | `docs/` |
| `scripts/` | Not found | top-level file inventory |
| `src/` | Present | `src/` |
| `tests/` | Not found | top-level file inventory |
| Ecosystem manifest | Present (`package.json`) | `package.json` |

## Path Purpose Table
| Path | Purpose | Key Files Inside | Notes (Entrypoint/Config/Data) |
|---|---|---|---|
| `README.md` | Top-level directory readme | `README.md` | Minimal summary; now links full docs. |
| `docs/` | Developer-facing operational and architecture docs | `README.md`, `DIRECTORY_MAP.md`, `OPERATIONS.md`, `ARCHITECTURE.md` | Documentation anchor folder for this directory. |
| `index.html` | Browser HTML entry shell | `index.html` | Loads `/src/main.tsx`; sets initial `data-theme` from `localStorage`/system preference. Evidence: `index.html`. |
| `package.json` | JS/TS toolchain manifest + scripts | `package.json` | Defines `dev`, `build`, `lint`, `preview` scripts and React/Vite/TS dependencies. |
| `public/logos/` | Static branding assets | `CityOfLaredoLogo.png`, `CityOfLaredoPublicHealthLogo.png` | Used in login/header UI. Evidence: `src/pages/LoginPage.tsx`, `src/components/Header.tsx`. |
| `src/main.tsx` | React app mount point | `src/main.tsx` | Single runtime app mount to `#root`. |
| `src/App.tsx` | Route graph and route-level access control | `src/App.tsx` | Declares routes, `ProtectedRoute` role gates, redirects, and fallback route. |
| `src/api/` | HTTP client + frontend API contracts/wrappers | `client.ts`, `auth.ts`, `index.ts` | `VITE_API_URL` base URL usage; token/session logic; endpoint wrappers and DTO interfaces. |
| `src/components/` | Shared UI and reusable domain widgets | `Header.tsx`, `ProtectedRoute.tsx`, `DocumentViewer.tsx`, `FieldEditor.tsx`, `StatusBadge.tsx`, `EmployeeSelectionModal.tsx` | Includes PDF rendering (`react-pdf`) and role-gated nav controls. |
| `src/contexts/` | Application state providers for auth/theme | `AuthContext.tsx`, `ThemeContext.tsx` | Auth refresh bootstrap and logout event handling; theme persistence in `localStorage`. |
| `src/pages/` | Route-level page modules | `LoginPage.tsx`, `RequirementsPage.tsx`, `UploadPage.tsx`, `ReviewQueuePage.tsx`, `ReviewDetailPage.tsx`, `CompliancePage.tsx`, `TemplatesPage.tsx`, `TemplateEditorPage.tsx`, `EmployeesPage.tsx`, `DashboardPage.tsx` | Implements operational flows (login, requirements, upload, review queue/detail, compliance, templates, employees). |
| `src/styles/` | Design tokens and theme variables | `tokens.css` | Light/dark theme CSS variables consumed by global/component styles. |
| `src/types/` | Shared TypeScript domain types | `auth.ts` | Role/user/auth context typing for auth and route guards. |
| `src/vite-env.d.ts` | Vite env typing | `src/vite-env.d.ts` | Declares `ImportMetaEnv.VITE_API_URL`. |
| `tsconfig.json` | Main TS compiler settings for app code | `tsconfig.json` | Strict settings; includes only `src`. |
| `tsconfig.node.json` | TS config for Vite/node-side file | `tsconfig.node.json` | Includes `vite.config.ts`. |
| `vite.config.ts` | Vite server/build configuration | `vite.config.ts` | React plugin; dev server host/port/watch polling. |

## Shared Repository Files This Directory Depends On
These are outside this directory but directly affect how this frontend is built/run/deployed.

| Path | Purpose | Frontend Impact | Evidence |
|---|---|---|---|
| `../../docker-compose.yml` | Local multi-service orchestration | Runs `frontend` service on `FRONTEND_PORT` with source mount and `VITE_API_URL` env wiring to API. | `../../docker-compose.yml` |
| `../../docker-compose.prod.yml` | Production-oriented compose file | Uses prebuilt `laredo-certs/frontend:latest` image, exposes port `80`, and healthchecks `/health`. | `../../docker-compose.prod.yml` |
| `../../docker/frontend/Dockerfile.dev` | Frontend dev image build | Node `20-alpine`, runs `npm run dev -- --host 0.0.0.0 --port 3000`. | `../../docker/frontend/Dockerfile.dev` |
| `../../docker/frontend/Dockerfile` | Frontend production image build | Multi-stage Node build + Nginx runtime; supports `ARG VITE_API_URL`. | `../../docker/frontend/Dockerfile` |
| `../../docker/frontend/nginx.conf` | Nginx runtime routing/proxy | Defines `/health`, `/api/` proxy to `api:8000`, and SPA fallback to `index.html`. | `../../docker/frontend/nginx.conf` |
| `../../Makefile` | Convenience commands from repo root | `make up`, `make logs-frontend`, `make shell-frontend` used by developers. | `../../Makefile` |
| `../../.github/workflows/ci.yml` | Repository CI workflow | CI jobs currently target ApiServer/Python paths; no dedicated frontend lint/test job block. | `../../.github/workflows/ci.yml` |

## Interface And Contract Surfaces
- Frontend-to-backend endpoint wrappers and DTO-like interfaces: `src/api/index.ts`.
- Auth-specific contract handling (`/auth/login`, `/auth/refresh`, `/auth/me`, `/auth/logout`): `src/api/auth.ts`.
- Runtime HTTP/token behavior contract (401 refresh + retry): `src/api/client.ts`.
- Auth and role type contracts for route guards/context: `src/types/auth.ts`.
- Template editor save payload schema shape at call-site: `src/pages/TemplateEditorPage.tsx`.

Evidence: `src/api/index.ts`, `src/api/auth.ts`, `src/api/client.ts`, `src/types/auth.ts`, `src/pages/TemplateEditorPage.tsx`.

## Hotspots (Likely Frequent Edit Areas)
- `src/App.tsx`: central route map and role gating changes generally start here.
- `src/api/index.ts`: endpoint wrappers + data contracts for most page features.
- `src/pages/RequirementsPage.tsx`: filtering/export and requirement-level workflows.
- `src/pages/ReviewDetailPage.tsx`: extraction review/approval behavior and document highlight flow.
- `src/pages/TemplateEditorPage.tsx`: largest page module; visual zone editor, keyboard shortcuts, and save payload shaping.
- `src/contexts/AuthContext.tsx` and `src/api/client.ts`: session bootstrap/refresh and 401-handling behavior.

Evidence: `src/App.tsx`, `src/api/index.ts`, `src/pages/RequirementsPage.tsx`, `src/pages/ReviewDetailPage.tsx`, `src/pages/TemplateEditorPage.tsx`, `src/contexts/AuthContext.tsx`, `src/api/client.ts`.
