# Architecture

> Path base convention: Unless explicitly stated otherwise, file references are relative to the directory root for this docs pack (the parent of this `docs/` folder). Line numbers are point-in-time anchors and may drift; treat file paths as canonical evidence.

## High-Level Overview
This directory implements a single-page frontend application for certificate-management operations (login, requirements tracking, upload, review, compliance analytics, template management, and employee administration). The app is bootstrapped by Vite/React, uses client-side routing, and gates most routes through role-aware auth checks.
Evidence: `package.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/components/ProtectedRoute.tsx`, `src/pages/LoginPage.tsx`, `src/pages/RequirementsPage.tsx`, `src/pages/ReviewDetailPage.tsx`, `src/pages/TemplateEditorPage.tsx`, `src/pages/EmployeesPage.tsx`.

The frontend communicates with a backend over HTTP using a shared API layer. Session handling is split between an in-memory access token and refresh-cookie flow; pages call typed API helpers from `src/api/index.ts` and `src/api/auth.ts`, while common retry/refresh behavior lives in `src/api/client.ts`.
Evidence: `src/api/client.ts`, `src/api/auth.ts`, `src/api/index.ts`, `src/contexts/AuthContext.tsx`.

## Component Diagram

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

Evidence: `index.html`, `src/main.tsx`, `src/App.tsx`, `src/contexts/AuthContext.tsx`, `src/contexts/ThemeContext.tsx`, `src/components/ProtectedRoute.tsx`, `src/pages/RequirementsPage.tsx`, `src/pages/ReviewDetailPage.tsx`, `src/pages/TemplateEditorPage.tsx`, `src/api/client.ts`, `src/api/auth.ts`, `src/api/index.ts`.

## Runtime Topologies
| Topology | How It Runs | Frontend URL/Port | Backend Reachability Model | Evidence |
|---|---|---|---|---|
| Local npm-only | `npm run dev` from this directory | `http://localhost:3000` (Vite default) | Frontend calls `VITE_API_URL` or fallback `/api` (relative). Set `VITE_API_URL` explicitly for non-Docker dev. | `package.json`, `vite.config.ts`, `src/api/client.ts` |
| Repo compose dev | `cd ../.. && make up` | Via Caddy at `https://localhost` | Caddy proxies `/api/` to `api:8000`; frontend uses `/api` relative fallback. | `../../Makefile`, `../../docker-compose.yml` |
| Repo compose prod | `cd ../.. && docker compose -f docker-compose.prod.yml up -d` | `${FRONTEND_PORT:-80}` mapped to container 80 | Nginx serves SPA and proxies `/api/` to `api:8000`; prebuilt image `laredo-certs/frontend:latest`. | `../../docker-compose.prod.yml`, `../../docker/frontend/nginx.conf` |

## Module Responsibilities
| Module / Folder | Responsibility | Evidence |
|---|---|---|
| `src/main.tsx` | App bootstrap and `#root` mount. | `src/main.tsx` |
| `src/App.tsx` | Route declarations, protected-route role policy, redirects (`/reports` to `/compliance`, wildcard fallback). | `src/App.tsx` |
| `src/contexts/AuthContext.tsx` | Auth state lifecycle, login/logout API calls, and four auto-logout mechanisms: (1) forced logout via `auth:logout` custom event on refresh failure; (2) cross-tab sync via `storage` event when `laredo_access_token` is removed from localStorage in any tab; (3) proactive token refresh scheduled 60 s before JWT expiry using `getTokenExpiryMs()`; (4) inactivity logout via `useInactivityLogout` hook, with `InactivityWarningModal` shown 60 s before timeout. | `src/contexts/AuthContext.tsx`, `src/api/auth.ts`, `src/hooks/useInactivityLogout.ts`, `src/components/InactivityWarningModal.tsx` |
| `src/contexts/ThemeContext.tsx` | Theme state (`light`/`dark`), persistence in `localStorage`, system preference sync. | `src/contexts/ThemeContext.tsx`, `index.html` |
| `src/api/client.ts` | Core fetch wrapper, auth header injection, refresh dedupe, 401 retry, normalized error throwing. Exports `getTokenExpiryMs(token)` which decodes the JWT payload and returns `exp * 1000` (ms) for proactive refresh scheduling. | `src/api/client.ts` |
| `src/api/auth.ts` | Auth-specific API operations (`login`, `/auth/me`, refresh, logout, `forgotPassword`, `resetPassword`). | `src/api/auth.ts` |
| `src/api/index.ts` | Endpoint wrappers + TypeScript contracts for requirements/documents/extractions/reports/templates/employees. Includes `sendSetupEmail(employeeId)` to resend an account setup email. `EmployeeCreate` and `EmployeeUpdate` no longer contain a `password` field. | `src/api/index.ts` |
| `src/components/DocumentViewer.tsx` | PDF rendering and bounding-box highlight interactions for review. | `src/components/DocumentViewer.tsx` |
| `src/components/FieldEditor.tsx` | Editable extracted-field input with optional candidate shortcuts. | `src/components/FieldEditor.tsx` |
| `src/pages/RequirementsPage.tsx` | Requirement listing/filtering/pagination and CSV/XLSX export actions. | `src/pages/RequirementsPage.tsx` |
| `src/pages/UploadPage.tsx` | Upload flow, file validation, optional employee auto-identification, success handoff to review. | `src/pages/UploadPage.tsx` |
| `src/pages/ReviewQueuePage.tsx` | Extraction queue listing, filtering, and queue context for review detail navigation. | `src/pages/ReviewQueuePage.tsx` |
| `src/pages/ReviewDetailPage.tsx` | Review/approve/reject workflow with field correction and document highlights. | `src/pages/ReviewDetailPage.tsx` |
| `src/pages/TemplateEditorPage.tsx` | Visual template-zone editor with undo/redo/normalize and save payload construction. | `src/pages/TemplateEditorPage.tsx` |
| `src/pages/EmployeesPage.tsx` | Employee CRUD-like management (list/create/update/activate/deactivate). Create form has no password field — a setup email is sent automatically. Edit modal includes a "Send Setup Email" button to issue a fresh one-time setup link. | `src/pages/EmployeesPage.tsx` |
| `src/pages/ForgotPasswordPage.tsx` | Email input form for self-service password recovery. Submits to `POST /auth/forgot-password`; always shows a generic confirmation message (anti-enumeration). | `src/pages/ForgotPasswordPage.tsx` |
| `src/pages/ResetPasswordPage.tsx` | Password-setup/reset form reached via emailed one-time link. Reads `?token` from URL; validates confirm-match client-side; redirects to `/login` with success state on completion. | `src/pages/ResetPasswordPage.tsx` |
| `src/hooks/useInactivityLogout.ts` | Tracks user activity events (`mousemove`, `mousedown`, `keydown`, `scroll`, `touchstart`, `click`). Fires `onWarning(secondsRemaining)` 60 s before timeout, then `onLogout` at timeout. Returns `{ resetTimer }`. Only active when `enabled` is `true`. | `src/hooks/useInactivityLogout.ts` |
| `src/components/InactivityWarningModal.tsx` | Modal displayed during the 60-second countdown before inactivity auto-logout. Shows seconds remaining with `aria-live` for screen reader support; "Stay Logged In" button calls `resetTimer`. Uses `role="alertdialog"`. | `src/components/InactivityWarningModal.tsx` |

## Route And Access Matrix
| Route | Component | Access Policy | Choose This Route When | Evidence |
|---|---|---|---|---|
| `/login` | `LoginPage` | Public | User needs to authenticate. Includes "Forgot password?" link. | `src/App.tsx`, `src/pages/LoginPage.tsx` |
| `/forgot-password` | `ForgotPasswordPage` | Public | User needs to initiate self-service password recovery. | `src/App.tsx`, `src/pages/ForgotPasswordPage.tsx` |
| `/reset-password` | `ResetPasswordPage` | Public (token-gated) | User follows an emailed one-time link to set or reset their password. | `src/App.tsx`, `src/pages/ResetPasswordPage.tsx` |
| `/` | `DashboardPage` | `Coordinator` or `Admin` | Landing dashboard and quick actions. | `src/App.tsx`, `src/pages/DashboardPage.tsx` |
| `/requirements` | `RequirementsPage` | `Coordinator` | Requirement-level tracking/export/upload handoff. | `src/App.tsx`, `src/pages/RequirementsPage.tsx` |
| `/upload` | `UploadPage` | `Coordinator` | Upload certificate file (with/without requirement context). | `src/App.tsx`, `src/pages/UploadPage.tsx` |
| `/review` | `ReviewQueuePage` | `Coordinator` | Work extraction queue. | `src/App.tsx`, `src/pages/ReviewQueuePage.tsx` |
| `/review/:id` | `ReviewDetailPage` | `Coordinator` | Review a specific extraction record. | `src/App.tsx`, `src/pages/ReviewDetailPage.tsx` |
| `/compliance` | `CompliancePage` | `Coordinator` | View aggregate compliance metrics. | `src/App.tsx`, `src/pages/CompliancePage.tsx` |
| `/reports` | Redirect to `/compliance` | Redirect | Legacy/alias path to compliance view. | `src/App.tsx` |
| `/templates` | `TemplatesPage` | `Coordinator` | Browse template registry. | `src/App.tsx`, `src/pages/TemplatesPage.tsx` |
| `/templates/new` | `TemplateEditorPage` | `Coordinator` | Create template zones/metadata. | `src/App.tsx`, `src/pages/TemplateEditorPage.tsx` |
| `/employees` | `EmployeesPage` | `Coordinator` or `Admin` | Manage employee records and status. | `src/App.tsx`, `src/pages/EmployeesPage.tsx` |
| `/admin` | Inline placeholder | `Admin` | Admin-only role management placeholder screen. | `src/App.tsx` |
| `/unauthorized` | Inline view | Public | Redirect target for unauthorized access. | `src/App.tsx` |

## Data Flow
### 1) Authentication + Route Access

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

Evidence: `src/contexts/AuthContext.tsx`, `src/api/auth.ts`, `src/components/ProtectedRoute.tsx`, `src/App.tsx`.

### 2) Requirements -> Upload -> Review loop

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

Evidence: `src/pages/RequirementsPage.tsx`, `src/pages/UploadPage.tsx`, `src/pages/ReviewQueuePage.tsx`, `src/pages/ReviewDetailPage.tsx`, `src/api/index.ts`.

### 3) Review Detail rendering

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

Evidence: `src/pages/ReviewDetailPage.tsx`, `src/components/DocumentViewer.tsx`, `src/components/FieldEditor.tsx`, `src/api/index.ts`.

### 4) Template editor authoring

> **Note:** Architecture diagrams are pending migration to this repository.
> See the textual description below for current architecture details.

Evidence: `src/pages/TemplateEditorPage.tsx`, `src/api/index.ts`, `src/pages/TemplatesPage.tsx`.

## Key Conventions
- Role names in auth typing are `Coordinator`, `Admin`, `Employee`; route role checks consume these values directly.
Evidence: `src/types/auth.ts`, `src/App.tsx`, `src/components/ProtectedRoute.tsx`.
- Review status handling primarily uses PascalCase values (`PendingReview`, `Approved`, `Rejected`) with explicit legacy snake_case fallback in queue display mapping.
Evidence: `src/pages/ReviewQueuePage.tsx`, `src/api/index.ts`.
- Requirements and compliance pages use module-level in-memory caches to avoid refetch on same-page session navigation.
Evidence: `src/pages/RequirementsPage.tsx`, `src/pages/CompliancePage.tsx`.
- There are two auth-facing API surfaces (`src/api/auth.ts` and auth exports in `src/api/index.ts`); either works, but context currently uses `src/api/auth.ts`.
Evidence: `src/api/auth.ts`, `src/api/index.ts`, `src/contexts/AuthContext.tsx`.
- Production container runtime can route API traffic via Nginx `/api` proxy; deployment scripts show a build pattern setting `VITE_API_URL=/api`.
Evidence: `../../docker/frontend/nginx.conf`.

## Configuration Model
| Config Surface | Location | Behavior |
|---|---|---|
| Dev server config | `vite.config.ts` | Host/port/watch behavior for local development. |
| Runtime API base URL | `VITE_API_URL` in `import.meta.env` | Used by API clients with localhost fallback. |
| Theme preference | `localStorage.theme` + `data-theme` attribute | Applied on startup and toggled via context/provider. |
| Type safety for env | `src/vite-env.d.ts` | Declares expected `VITE_API_URL` key in TS. |
| Container dev service wiring | `../../docker-compose.yml` | Frontend uses `/api` relative fallback; Caddy handles routing. Port map and source mount via compose. |
| Container prod web/proxy | `../../docker/frontend/nginx.conf`, `../../docker-compose.prod.yml` | Provides SPA fallback, `/health`, and `/api/` proxy to backend service. |
| `VITE_INACTIVITY_TIMEOUT_MINUTES` env var | `src/contexts/AuthContext.tsx` | Minutes of inactivity before auto-logout fires (default `30`). Warning modal appears 60 s before timeout. Override via `.env` or compose `environment`. |

Evidence: `vite.config.ts`, `src/api/client.ts`, `src/api/auth.ts`, `src/api/index.ts`, `index.html`, `src/contexts/ThemeContext.tsx`, `src/vite-env.d.ts`, `../../docker-compose.yml`, `../../docker/frontend/nginx.conf`, `../../docker-compose.prod.yml`, `src/contexts/AuthContext.tsx`.

## API Contract Sources
- Frontend-side contract surfaces: `src/api/index.ts` interfaces and request wrappers.
- Backend-side contract surfaces (outside this directory): FastAPI app and router registration in `../../CoreInstances/ApiServer/src/main.py` and related route modules.
- Static OpenAPI file in this directory: not present.
- Backend root endpoint payload includes `docs_url: "/docs"` (discoverable API docs entrypoint at runtime).

Evidence: `src/api/index.ts`, `../../CoreInstances/ApiServer/src/main.py`.

## Entrypoints
- Browser entry shell: `index.html` (loads `/src/main.tsx` and sets initial theme attribute).
- React runtime entrypoint: `src/main.tsx` (creates root and renders `<App />`).
- Route entrypoints (feature-level): paths declared in `src/App.tsx` (`/login`, `/forgot-password`, `/reset-password`, `/`, `/requirements`, `/upload`, `/review`, `/review/:id`, `/compliance`, `/templates`, `/templates/new`, `/employees`, `/admin`, `/unauthorized`).

Evidence: `index.html`, `src/main.tsx`, `src/App.tsx`.

## Extension Points
1. Add a new page/feature route.
- Add page module under `src/pages/`.
- Register route and role policy in `src/App.tsx` via `ProtectedRoute`.
- Add navigation entry where needed (for example dashboard/header links).
Evidence: `src/App.tsx`, `src/pages/DashboardPage.tsx`, `src/components/Header.tsx`.

2. Add a new backend endpoint integration.
- Add typed API function and interfaces in `src/api/index.ts` (or `src/api/auth.ts` for auth).
- Consume from page/component.
- Reuse `apiFetch` where token refresh/retry is needed.
Evidence: `src/api/index.ts`, `src/api/auth.ts`, `src/api/client.ts`.

3. Add new extraction/review fields.
- Update field labels/editing surfaces in `FieldEditor`.
- Update highlight color mappings where needed.
- Ensure review/detail mapping covers new field payload shape.
Evidence: `src/components/FieldEditor.tsx`, `src/components/DocumentViewer.tsx`, `src/pages/ReviewDetailPage.tsx`.

4. Extend template authoring.
- Update canonical field constants and zone property handling in `TemplateEditorPage`.
- Ensure `createTemplate` payload mapping includes new options.
Evidence: `src/pages/TemplateEditorPage.tsx`, `src/api/index.ts`.

5. Adjust deployment behavior for API base/pathing.
- If deployment network topology changes, align frontend `VITE_API_URL` and/or Nginx `/api` proxy behavior.
- Keep compose/docker script wiring consistent with frontend expectations.
Evidence: `src/api/client.ts`, `../../docker/frontend/nginx.conf`, `../../docker-compose.yml`.
