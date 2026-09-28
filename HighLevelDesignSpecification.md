# High-Level Design Specification

## Certificate Tracking, Extraction, Review, Compliance Reporting, Notifications, and Service Mesh mTLS

**Primary operator:** Carla Morgan (Certification Coordinator)
**Organization:** City of Laredo Public Health Department
**Academic project context:** Texas A&M International University

---

## 1. Purpose and Target Outcomes

### 1.1 System purpose

Deliver a secure, auditable system that reduces manual spreadsheet updates by automating certificate intake, document storage, template-driven data extraction, and due-date and expiration tracking, with a mandatory human verification step before any certificate is recorded as verified.

This system supports both computer-generated PDFs (for example, from an LMS) and scanned/signed documents.

### 1.2 Target outcomes (what “success” means)

Aligned to Dr. Morgan’s stated success criteria:

1. **Reduced time to update and report** training and certification completion (monthly reporting becomes a few clicks, not spreadsheet reconciliation).
2. **Employee self-submission without portal friction** using a dedicated inbound mailbox, where the sender’s city email becomes the employee identity for intake.
3. **Evidence-rich review UI** that presents a side-by-side view of the document and extracted fields, allowing “approve as-is” or “correct then approve.”
4. **No auto-verification**: verification is always a deliberate approval action by the Coordinator.
5. **Template-first extraction** using configurable certificate templates (JSON files loaded at runtime), with a generic fallback that never auto-verifies.
6. **Deterministic notifications** for due dates and expirations at configurable intervals (default: **90/60/30/15/7/6/5/4/3/2/1/0 days**, with daily overdue), sent to the employee and the Coordinator.
7. **Strong privacy boundaries** appropriate for public health operations (no sensitive certificate content in logs; auditable access and changes).

---

## 2. Scope and Non-Goals

### 2.1 In-scope capabilities

#### Intake channels

* **Primary:** Employee emails their certificate attachment to a dedicated address (for example, `certs@...`).

  * Sender must be the employee’s city email address (identity binding).
  * Attachments are extracted and processed automatically.
* **Secondary (exception path):** Coordinator manual upload (for paper copies or edge cases).
* **Tertiary (initial migration):** Bulk import from Excel manifest and certificate image directory. Used for one-time onboarding of historical data (employees, certificates, requirement assignments). Bulk-imported certificates are recorded as pre-verified (no extraction pipeline or review queue involvement). Coordinator attribution is recorded for audit purposes.

#### Certificate processing

* Immutable storage of uploaded documents (original bytes preserved).
* Template identification and template-zone extraction (primary path).
* Generic extraction fallback producing reviewer-ready candidates only (never creates verified records by itself).
* Field-level evidence and provenance (page, bounding box, source method).

#### Human verification workflow (Coordinator)

* Review queue (one document at a time).
* Side-by-side comparison: document preview vs extracted data.
* Correct-and-approve or reject.
* Approval creates the only “verified certificate” record.

#### Requirements, due dates, and compliance

* Track required certifications per employee with due dates.
* Keep **requirement due dates** and **certificate lifecycle (expiration)** as separate timelines.
* Compute compliance for dashboards and reports.

#### Notifications and reporting

* Notifications: due soon and expiring soon at configurable intervals (default: **90/60/30/15/7/6/5/4/3/2/1/0 days**, with daily overdue). Cadence is managed via alert rules (see Section 5.2.2).
* Monthly reporting: names, completed certs, completion date, expiration date, title, issuer/agency.
* Dashboard counts: active, expiring soon, expired, assigned-not-completed.
* Requirements tracking and compliance are presented as two linked Coordinator views: a **Requirements** page (operational table with search, status filter, pagination, and export) and a **Compliance** page (dashboard with overall rate, status breakdown, and per-certificate-type breakdown). Each page links to the other.
* Export to XLSX or CSV for compliance and requirement reports.
* Custom date range filtering for review queue and reports (in addition to preset filters).

#### Onboarding acknowledgment forms

* Two acknowledgment forms are processed through the same extraction pipeline as certificates:
  * **HIPAA Acknowledgment** — privacy and confidentiality acknowledgment (annual renewal, 365-day validity).
  * **Employee Policies Acknowledgment** — general policies acknowledgment (annual renewal, 365-day validity).
* Employees submit these via the email channel like any other certificate.
* These forms may include an employee ID field that is extracted and stored alongside the verified record.

#### Security and governance

* Authentication required for UI/API.
* Access scoped so only the Coordinator can view department-wide records and documents.
* Strong audit logging with actor vs initiator.

### 2.2 Explicit non-goals

* Automatic verification or confidence-based approval.
* ML dependence for V1 (ML may assist template identification only). However, the system's human-in-the-loop verification workflow (cert image + extracted fields + approve/reject) inherently produces labeled training data. This positions the organization to train supervised models in the future to reduce or eliminate manual review — a strategic benefit of the platform architecture.
* Supporting arbitrary formats beyond PDF and supported image types in V1.
* Persisting computed compliance as authoritative state (computed for reporting).
* Building a full supervisor-facing portal if the operating model is “Coordinator-only visibility” (optional future).

---

## 3. Operating Model and Access Model

### 3.1 Roles

The system uses three distinct roles to enforce privacy and integrity:

* **Employee (Submitter):** submits certificates for self via the email channel only. Employees **do not have web login access**. The employee role exists in the system as a tracking entity (not a login account). Employee records may be auto-created when a new city-domain sender in the GAL submits for the first time.
* **Coordinator (Reviewer):** full web UI access. Reviews and approves extractions, manages employees, assigns certification requirements, runs reports, controls templates, and can manually upload certificates on behalf of employees. This is the primary user of the system (Dr. Morgan).
* **Admin (IT):** can assign or unassign the Coordinator role. This is a safety net so that if the Coordinator leaves or is replaced, IT can transfer access. Admin does not perform certificate operations.
* **System:** automated actors (email ingestion, extraction worker, scheduler).

No other roles exist in the system. Roles such as Manager or Reviewer were evaluated and excluded — they add complexity without matching the operating model, which is Coordinator-only visibility with exports shared externally.

This is a minimal RBAC model designed to match Dr. Morgan's statement that only she should see records and then share with leadership/supervisors outside the tool.

### 3.2 Visibility rules (baseline)

* Coordinator: view all employees, documents, extraction runs, verified records, and reports.
* Employee: **submit-only via email**. No web UI access, no portal login.
* Admin: can manage Coordinator role assignments. Read-only access to audit logs for governance oversight. No access to certificate data or operational workflows.
* No supervisor access by default (Coordinator shares outputs externally).

---

## 4. Non-Negotiable Principles (Hard Gates)

### INV-01: Template-first extraction with controlled fallback

* The system selects certificate type and template before zone extraction.
* If template is not confidently selected or required checks fail, run generic extraction and present candidates for review.
* Neither path can create a verified record without explicit approval.

### INV-02: Human approval hard gate (no automatic verification)

* A **VerifiedCertificateRecord** is created only by Coordinator approval.
* No automated workflow step may create verified records.
* **Exception:** Bulk import (WF-09) creates pre-verified records as a deliberate, Coordinator-initiated migration action. The Coordinator is recorded as the reviewer for audit purposes.

### INV-03: Two timelines remain uncoupled

* Requirement due-date tracking never changes because a certificate expires.
* Certificate lifecycle comes only from verified record expiration data.
* Compliance is computed for dashboards and reporting.

### INV-04: Versioned, runtime-loaded TemplateRegistry with retention

* Templates are configuration-driven, versioned, validated on load, and retained while referenced.

### INV-05: Evidence-rich outputs with canonical provenance

* Extracted and verified fields carry provenance sufficient for review and audit (page and bounding box coordinates, extraction source, zone identity).
* **Confidence scores are retained internally** for pipeline diagnostics and logging, but are **not displayed to the reviewer** in the review UI. They add noise without helping the reviewer make better decisions. The reviewer relies on the document preview, bounding box highlights, and candidate values instead.

### INV-06: Governance boundaries aligned to the Coordinator model

* Employees have no web login and cannot waive requirements or approve verifications.
* Coordinator can manage requirements and perform approvals.
* Admin (IT) can only assign or unassign the Coordinator role.
* All privileged actions must be enforced server-side (not only UI).

### INV-07: Deterministic, deduped notifications with backfill

* Scheduler is idempotent and resilient to missed runs, using trigger-date-based dedupe keys and a monotonic cursor.

### INV-08: Canonical coordinates and deterministic reading order

* Bounding boxes use normalized [x1, y1, x2, y2] with top-left origin, 0..1.
* Multi-span text assembled deterministically (top-to-bottom, left-to-right).

### INV-09: Email submission is identity-bound and audited

* The sender's city email address is the primary employee identity for email intake.
* Intake must silently **ignore** emails from outside the city domain (non-city senders are never processed or replied to).
* For city-domain senders:

  * If the sender is in the Global Address List (GAL) **and** an employee record already exists: process normally.
  * If the sender is in the GAL **but no employee record exists** (first-time submission): **auto-create** an employee record from the GAL (name, email) and continue processing. This is a tracking entity only, not a login account.
  * If the sender is a distribution list (not a person): ignore.
  * Attachments failing validation (type, size, malware): quarantine and notify Coordinator.
* All email-to-document conversions are auditable (message id, sender, received time, attachment metadata).

---

## 5. Logical Architecture

### 5.1 Components

1. **Ingress + Web UI/API Server**

   * Public TLS termination at ingress.
   * Serves the Coordinator UI (review queue, reports).
   * Provides APIs for requirements, document access, review actions, reporting.

2. **Email Intake Service (Inbound Mailbox Connector)**

   * Polls or receives events from the dedicated mailbox.
   * Validates sender identity and extracts attachments.
   * Runs boundary validation (type, size, malware scan).
   * Creates CertificateDocument records and triggers extraction.

3. **Document Storage**

   * Immutable object storage with non-guessable keys.
   * Stores original uploaded bytes plus metadata (sanitized filename, MIME).

4. **TemplateRegistry Service**

   * Loads versioned templates at runtime.
   * Validates schema and fails closed on invalid config.
   * Provides template lookup and listing.

5. **Extraction Worker**

   * Normalizes document (PDF text layer vs OCR).
   * Detects template and performs zone extraction or generic fallback.
   * Produces ExtractionRun — initially in **Processing** state, transitioned to **PendingReview** only after extraction completes (see SM-01).
   * **GPU auto-detection at startup:** The worker detects available GPU hardware and configures the LLM consensus pipeline accordingly:
     * No GPU or ≤4 GB VRAM: all 3 consensus LLM runs and the judge run sequentially.
     * \>4 GB VRAM: the 3 consensus LLM runs execute in parallel; the judge runs sequentially after.

6. **Review Workflow (Coordinator UI + Review API)**

   * Presents one document at a time: preview + extracted fields + evidence.
   * Allows edits and approval or rejection.
   * Approval creates VerifiedCertificateRecord and links requirement if applicable.

7. **Repository/Data Access Layer**

   * Transactional store (SQL recommended) enforcing constraints and idempotency.

8. **Notification Scheduler/Worker**

   * Daily run with backfill capability using JobCursor.
   * Creates NotificationEvent rows with deterministic dedupe keys.
   * Delivery mechanism (email) is configurable.

9. **Audit Logger**

   * Append-only audit records for all privileged actions and system automations.
   * Actor vs initiator semantics.

10. **Observability Stack**

* Logs, metrics, traces with redaction rules and retention policy.

---

## 5.2 Configuration Domain

The system includes a unified **Configuration** page accessible to Coordinators, replacing the standalone Upload card in the primary navigation. Configuration provides management interfaces for the operational entities that control system behavior.

### 5.2.1 Certificate Type Management

Coordinators manage certificate types through the Configuration page. Each certificate type defines:

* Display name and description
* Renewal periodicity (months; null for non-recurring)
* Active/inactive status (inactive types are hidden from new assignments)

Certificate types are the foundation for requirement assignments, template selection, and compliance reporting. The certificate type owns its periodicity — renewal period is an attribute of the type, not computed from individual certificates.

### 5.2.2 Alert Rule Management

Notification cadence is managed configuration, not hardcoded. Each alert rule defines:

* Day offsets for reminders (default: `[90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1, 0]`)
* Daily overdue reminder behavior (on/off)
* Preferred send time (default: `06:00`)
* Optional scoping to a specific certificate type (null = global default)

The scheduler reads alert rules from the database at each run, replacing previously hardcoded constants. See Section 7.12 for the AlertRule entity and Section 10 for notification operations.

### 5.2.3 Issuing Authority

Issuing authority (the organization that issues a certificate, e.g., OSHA, CDC, EPA) is **template-authoritative**. The issuing organization is defined as an attribute of the template definition, not extracted per document. This ensures consistency across all certificates of a given type and avoids extraction noise from varying document formats.

See Section 7.11 for the TemplateDefinition entity.

### 5.2.4 Template Management

Template management (viewing and previewing extraction templates) remains available through the Configuration page. See existing Section 5.1 Component 4 (TemplateRegistry Service) for template details.

---

## 6. Service Mesh mTLS (Encryption in Transit for East-West Traffic)

This section operationalizes “mTLS for service-to-service where supported” by placing internal services behind mesh-enforced mTLS while keeping standard TLS at the ingress edge.

### MESH-01: Service-to-service encryption and identity

* All internal service-to-service traffic is encrypted and mutually authenticated (mTLS).
* Workload identity is bound to:

  * service/workload name
  * environment/namespace (prevents cross-environment impersonation)

### MESH-02: Mesh placement

Mesh protects traffic between:

* API Server ↔ TemplateRegistry
* API Server ↔ Review endpoints (if separated)
* Email Intake Service ↔ API/Repository
* Extraction Worker ↔ TemplateRegistry/Repository
* Scheduler ↔ Repository
* Any other east-west calls

Ingress remains the public TLS boundary.

### MESH-03: CA, rotation, custody

* Workload certificates are short-lived and rotated automatically.
* Root/intermediate CA materials are tightly controlled and audited.
* Option to integrate with enterprise PKI if required.

### MESH-04: Rollout modes

* Permissive/monitoring mode first, then strict mTLS by namespace/environment.
* Must be reversible per environment to prevent outages during adoption.

### MESH-05: Identity-based service authorization

* After mTLS identity is established, enforce service-to-service allow rules by identity, not IP.
* Policy changes are governed and auditable.

### MESH-06: Egress controls

* External calls remain standard TLS end-to-end.
* Optional egress gateway for allowlisting and observability.

### MESH-07: Mesh observability and audit evidence

* Evidence must be available for audits:

  * mTLS enabled per workload
  * handshake failures
  * cert rotations
  * policy denies
* Mesh telemetry must comply with privacy constraints (no raw certificate contents in logs).

### MESH-08: DB and storage connectivity

Explicit decision required per deployment:

* Keep DB outside mesh with native TLS, or
* Put DB behind a mesh-aware gateway/proxy, or
* If DB is a service, include it in mesh

Default: DB out of mesh, enforce DB-native TLS and network controls, to reduce outage coupling.

---

## 7. Core Data Model (Entities)

### 7.1 Employee

* `employee_id` (internal UUID)
* `city_email` (unique, authoritative for email intake)
* `display_name`
* Optional: `employee_number`, `lms_username_id` (aliases)

### 7.2 CertificateType

Canonical types tied to requirements and templates. The certificate type owns its renewal periodicity.

* `certificate_type_id` (internal UUID)
* `name` (unique display name, e.g., "CPR / First Aid")
* `description` (optional)
* `periodicity_months` (renewal period in months; null if non-recurring)
* `is_active` (boolean; inactive types are hidden from new assignments but retained for historical records)
* `created_at`, `updated_at`

### 7.3 RequirementAssignment

* `employee_id`, `certificate_type_id`
* `due_date`
* `satisfied_by_certificate_id` (nullable)
* `waived_at/by/reason` (nullable)
* Optional: `created_by` (Coordinator) and `requested_by` (if supervisors request via a lightweight intake flow)

### 7.4 CertificateDocument

* `employee_id` (subject/owner)
* `intake_channel`: `EMAIL` | `MANUAL_UPLOAD` | `BULK_IMPORT`
* `uploaded_by_employee_id` (nullable; for manual)
* `source_email_message_id` (nullable)
* `storage_key`, `sanitized_filename`, `detected_mime_type`, `upload_time`
* Optional link to requirement assignment

### 7.5 EmailIntakeMessage (recommended for audit and dedupe)

* `message_id` (provider id)
* `from_address`, `received_at`
* `attachment_fingerprints`
* `processing_state` and error reason codes

### 7.6 ExtractionRun (pre-review)

* Template selection provenance (type, template id/version, match evidence)
* Canonical extracted fields (null-safe)
* Evidence per field (bbox/page/zone/source)
* `needs_review` + reasons
* `review_state`: Pending/Approved/Rejected

### 7.7 VerifiedCertificateRecord (post-review)

Created only upon approval. Stores:

* Verified field values
* Reviewer attribution: `reviewed_by`, `reviewed_at`
* Field provenance retained (what evidence supported the final value)
* Link to document and extraction run
* Expiration date optional

### 7.8 NotificationEvent

* `type`, `recipient_employee_id` (employee or Coordinator)
* Links to requirement and/or verified record
* `effective_date` (logical trigger date)
* `dedupe_key` (unique)

### 7.9 AuditLog

* Actor: System or Employee
* Initiator (when System acts because a user initiated)
* Action, target, safe structured details
* Dual timestamps: `created_at` (event time) and `recorded_at` (database write time)
* `correlation_id` (groups related audit events within a single operation)
* `source_service` (originating service, e.g., `api`, `scheduler`, `email-intake`)
* `outcome` (result of the action, e.g., `success`, `failure`, `denied`)

### 7.10 JobCursor

* `job_name`, `last_success_date` (monotonic)

### 7.11 TemplateDefinition (registry)

* `template_id`, `template_version`, `certificate_type_id`
* `issuing_authority` (template-authoritative; the issuing organization is defined at the template level, not extracted per document)
* detection signals, alignment rules
* zones (canonical coordinates)
* parsing/validators/review rules

### 7.12 AlertRule (notification configuration)

* `alert_rule_id` (internal UUID)
* `certificate_type_id` (nullable; null = global default)
* `day_offsets` (array of integers, e.g., `[90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1, 0]`)
* `daily_overdue` (boolean; when true, send daily reminders for overdue items)
* `send_time` (time of day for notification delivery, e.g., `06:00`)
* `is_active` (boolean)
* `created_at`, `updated_at`

---

## 8. End-to-End Workflows

### WF-01: Requirement assignment and due-date tracking

* Coordinator creates or imports RequirementAssignments (spreadsheet import is a pragmatic accelerator).
* Due-date status computed (Assigned, Submitted, Overdue, Completed, Waived).

### WF-02: Employee submits certificate via email (primary path)

1. Employee emails dedicated inbox from city email address.
2. Email Intake Service:

   * validates sender domain and directory membership
   * extracts attachments
   * validates file types/sizes and malware scans
   * stores raw bytes immutably
   * creates CertificateDocument
   * triggers ExtractionRun creation

Operational safeguards:

* Dedupe using `(message_id, attachment_hash)` to avoid double-processing retries.
* If the certificate's extracted name does not match the employee record, **auto-reject** and send a reply email to the sender explaining: "This does not appear to be your certificate. Have the certificate holder email it themselves, or forward it to the Coordinator for manual processing."
* Name-mismatch enforcement is **bypassed** when the Coordinator uploads a certificate manually (WF-03).

### WF-03: Manual upload (exception path)

Coordinator uploads a scanned copy for employees who provided paper documents, following the same validation and extraction pipeline.

### WF-04: Extraction pipeline (template-first with fallback)

* Normalize (PDF text vs OCR).
* Identify certificate type and template.
* If selected:

  * zone extraction + validators
* Else:

  * generic extraction candidates
* Transition ExtractionRun from Processing to PendingReview once extraction is complete.

### WF-05: Coordinator review (side-by-side)

* Queue shows PendingReview items only (not Processing).
* One-at-a-time review screen:

  * Document preview (page navigation/zoom)
  * Extracted fields with bounding box highlights on the document (no confidence scores displayed)
* **Record navigation:** Next/Previous buttons allow the Coordinator to move between records without returning to the queue list.
* **Date filtering:** In addition to preset filters (Any Age, Today, This Week, Older than 7 days), a custom date range picker allows filtering by arbitrary date ranges.
* Coordinator actions:

  * Approve (optionally after edits)
  * Reject (with reason)

### WF-06: Approval creates verified record and links requirement

On approve:

* Atomic transition Pending → Approved
* Create one VerifiedCertificateRecord (idempotent by unique constraint on extraction id)
* Link matching RequirementAssignment (update-if-unset) if certificate type matches.

### WF-07: Status computation and reporting

* RequirementStatus computed by strict rule order (waived, completed, overdue, submitted, assigned).
* CertificateLifecycleStatus computed from verified expiration date.
* Compliance computed for dashboards and reports.
* Requirements tracking and compliance reporting are presented as two linked Coordinator views:
  * **Requirements page** (`/requirements`): operational table with status filters (all, overdue, due-soon, on-track, satisfied, waived), search, days-left tracking, pagination, CSV export, and XLSX export. Links to the Compliance page.
  * **Compliance page** (`/compliance`): dashboard showing overall compliance rate, status breakdown (Compliant / Due Soon / Overdue / Waived with progress bars), and per-certificate-type breakdown table. Links to the Requirements page.

### WF-08: Notifications (daily job, backfill, dedupe)

* Scheduler processes trigger dates between last_success_date + 1 and today.
* Creates NotificationEvent rows with trigger-date-based dedupe keys.
* Sends reminders to employee and Coordinator.

### WF-09: Bulk import for day-one onboarding

For initial deployment, the system supports bulk import of historical data from Excel spreadsheets and a certificate image directory. This is a one-time migration path, not a recurring intake channel.

**Phases:**

1. **Employees:** Import employee records (name, email, department) from Excel.
2. **Certificate Types:** Ensure all certificate types referenced in the manifest exist.
3. **Certificates:** Import certificate images/PDFs without changing the source bytes, store them in object storage, and create pre-verified records with Coordinator attribution. Image-to-PDF conversion is preview-only and occurs on demand.
4. **Requirement Assignments:** Create requirement assignments linked to verified certificates where applicable.

**Key invariants:**

* SHA-256 hash dedup on original file bytes ensures idempotent re-runs.
* Images are converted to PDF before storage (matches extraction worker behavior).
* Pre-verified records bypass the review queue but are fully auditable.
* `intake_channel = BULK_IMPORT` distinguishes these from email or manual uploads.

### WF-10: Self-service forgot password / account recovery

**Actors:** User → Client → Auth Service → DB → Email Service → User

1. User submits their email address to the recovery endpoint (`POST /auth/forgot-password`).
2. Auth Service returns a **generic** response regardless of whether the account exists (anti-enumeration). The response body and status code are identical for existing and non-existing addresses.
3. If the account exists and is eligible for reset, Auth Service:
   * Generates a 32-byte CSPRNG token.
   * Stores **only a SHA-256 hash** of the token alongside `expires_at` (30 minutes from now) and `used_at` (null).
   * Emails a reset link constructed from a configured canonical origin — **never** from the `Host` request header (prevents host-header injection attacks).
4. User opens link. Auth Service validates: token hash matches a stored record, `expires_at` has not passed, and `used_at` is null.
5. User submits new password. Auth Service enforces the same password policy (min/max length, no composition rules, blocklist) used at registration and password change.
6. Auth Service atomically:
   * Updates the password hash.
   * Marks the reset token as used (`used_at = now`).
   * Increments `token_version` on the employee record (invalidating all outstanding JWTs).
   * Sets `last_logout_at = now` (invalidating all outstanding refresh tokens).
7. Auth Service logs the event: `actor=user`, `action=password_reset_completed`.

**Invariants:**
* Reset tokens are one-time use. A second attempt with the same token returns 400.
* Tokens expire after 30 minutes. An expired token returns 400 (same response as used tokens — no enumeration).
* Token hashes, not plaintext tokens, are stored in the database. A database breach does not grant immediate reset capability.
* The reset endpoint is rate-limited with the same per-account + per-IP policy as login.
* The reset flow does not require the current password (the user has lost access); possession of the single-use email link is the only credential.

---

### WF-11: Employee account creation with self-service password setup

**Actors:** Coordinator/Admin → API → Email Service → Employee

**Policy:** Coordinators and Admins may not set or read another user's password. When a new employee account is created through the web UI or API, the system sets `password_hash = NULL` and immediately sends an account setup email to the employee's city email address.

1. Coordinator/Admin submits `POST /api/employees` with: employee number, name, email, role, optional manager.
2. API creates the employee record with `password_hash = NULL` (account cannot log in until setup is complete).
3. API calls `AuthService.send_account_setup_email()`, which:
   * Generates a 32-byte CSPRNG token.
   * Stores only a SHA-256 hash alongside `expires_at` (30 minutes) in `password_reset_tokens`.
   * Emails a setup link to the employee: `{FRONTEND_URL}/reset-password?token={raw_token}`.
   * Subject: "Welcome — Set Up Your City of Laredo Account".
4. Employee opens the link, submits a new password that satisfies policy (min 8 characters, max 128, no composition rules).
5. `POST /auth/reset-password` validates the token, stores the Argon2id hash, marks the token used, and invalidates any in-flight sessions (increments `token_version`, sets `last_logout_at`).
6. Employee is redirected to `/login` with a success notice and can now log in.

**Resend:** If the setup link expires before the employee acts, a Coordinator/Admin can trigger a fresh token via `POST /api/employees/{id}/send-setup-email` (UI: "Send Setup Email" button in the edit modal). The new token replaces the old one (old token hash remains in DB as used-equivalent once expired).

**Invariants:**
* Admins/Coordinators cannot set a plaintext password for another user at any point.
* A new employee with `password_hash = NULL` cannot log in; the `/auth/login` endpoint returns `"Invalid email or password"` (same generic message, anti-enumeration).
* The setup email reuses the same `password_reset_tokens` mechanism and one-time-use rules as WF-10.
* Email delivery failure does not block account creation — the account is created and the admin can manually resend.

---

## 9. Status Logic (Deterministic)

### SM-01: ExtractionRun review_state

* **Processing → PendingReview:** The extraction is created in `Processing` state at upload time. It transitions to `PendingReview` only after the extraction pipeline has fully completed and populated the extracted fields. Extractions in `Processing` state must **not** appear in the review queue.
* PendingReview → Approved or PendingReview → Rejected
* No regression; single-winner transitions with concurrency safety.

### SM-02: RequirementStatus (due-date timeline only)

Strict order:

1. Waived
2. Completed (satisfied_by_certificate_id set)
3. Overdue (now > due_date)
4. Submitted (upload exists but not verified)
5. Assigned

### SM-03: CertificateLifecycleStatus (certificate timeline only)

Strict order:

1. expiration_date null → Active + missing_expiration flag
2. now > expiration_date → Expired
3. days_to_expiration in {90,60,30} windows (or <= threshold) → ExpiringSoon (with days remaining)
4. else Active

### SM-04: Compliance status (computed for dashboard)

**Compliance rate** = `(Compliant + Waived) / Total_Requirements × 100%`

A requirement is counted as **Compliant** if:

* It is satisfied (linked to a verified certificate), OR
* It is not yet within 30 days of its due date (grace period — the employee still has time)

A requirement is counted as **Not Compliant** if:

* It is overdue (past due date without satisfaction), OR
* It is due soon (within 30 days of due date and not yet satisfied)

Waived requirements count toward compliance (they are explicitly excused).

---

## 10. Notifications (Updated to Dr. Morgan’s Rules)

### OPS-01: Notification types and cadence

Default reminder schedule (configurable via alert rules): **90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1, 0** days before due date or expiration date.

* Due reminders at each configured day offset before the due date
* Expiration reminders at each configured day offset before the expiration date
* Daily overdue reminders (configurable per alert rule)
* Expired notifications

Notification cadence is managed through the AlertRule entity (see Section 7.12). Each alert rule defines `day_offsets`, `daily_overdue`, and `send_time`. Rules can be global (default) or scoped to a specific certificate type.

### OPS-02: Recipients

* Employee always (based on employee email identity).
* Coordinator always (so Dr. Morgan can act and report).

### OPS-03: Dedupe intent

* Dedupe key includes:

  * type
  * recipient
  * related requirement/certificate ids
  * effective trigger date
* Unique constraint prevents duplicates across reruns/backfills.

### OPS-04: Backfill via JobCursor

* Monotonic cursor; atomic cursor advance with inserts.

---

## 11. Security, Privacy, Auditability, Retention

### SEC-01: Authentication

* Coordinator and Admin UI and APIs require authentication.
* Employees do not have login accounts. Their identity is established by their city email address during email submission.

**Anti-enumeration:**
* Login, registration, and account-recovery endpoints return identical generic responses (e.g., `"Invalid email or password"`) regardless of whether the account exists, is disabled, or is unconfigured.
* The password verification path must be constant-time; when no account is found, equivalent dummy work is performed to prevent timing-based enumeration attacks.

**Rate limiting / throttling:**
* Per-account graduated backoff is applied on failed login attempts. IP-only throttling is insufficient because credential-stuffing attacks distribute across many IPs.
* Hard permanent lockouts are avoided to prevent account-lockout DoS; exponential backoff with step-up (MFA prompt or CAPTCHA) is the preferred pattern.
* `/auth/login` and `/auth/forgot-password` are both rate-limited.

**MFA:**
* Admin accounts require MFA. TOTP (authenticator app) is the minimum; passkeys/WebAuthn are preferred for phishing resistance. NIST AAL2 is the target assurance level for Admin.
* Coordinator MFA is strongly recommended and should be offered at enrollment; may be made mandatory in a future iteration based on organizational policy.
* Multiple "something you know" factors (password + PIN) is not MFA and does not satisfy this requirement.

**Reauthentication gates:**
* Password change, email change, MFA enrollment/removal, and MFA reset each require verification of the current password (or an existing MFA factor). This prevents silent takeover via unattended sessions.

### SEC-02: Email intake security controls

* Silently ignore all messages from outside the city email domain.
* Accept messages only from city-domain personal addresses (not distribution lists) that appear in the Global Address List.
* First-time city-domain senders in the GAL are auto-provisioned as employee records (tracking only, no login account).
* Log only minimal metadata (message id, sender, received time), never certificate contents.
* Quarantine failures (invalid attachment, malware scan failure) and notify the Coordinator.

### SEC-03: Encryption and key management

* External: TLS at ingress (TLS 1.2+).
* Internal: mesh-enforced mTLS for east-west traffic.
* At-rest: encrypted storage and database encryption with managed keys.
* Key rotation and access controls governed.

### SEC-04: Access control aligned to "Coordinator-only visibility"

* Coordinator can see everything.
* Employees have no web access; they interact only via the email channel.
* Admin (IT) can manage Coordinator role assignments but cannot access certificate data.

### SEC-05: Audit logging with actor vs initiator

Examples:

* Email intake created document (actor=System, initiator=Employee)
* Extraction created run (actor=System, initiator=Employee)
* Coordinator approved/rejected (actor=Employee)
* Scheduler created notifications (actor=System, initiator=null)

### SEC-06: Privacy boundaries

* No raw certificate content in logs or analytics.
* Export is Coordinator-only and auditable.
* Redaction rules apply to operational telemetry.

Public health documentation and acknowledgments handled by this workflow should be treated as sensitive, and confidentiality controls must be enforced accordingly.

### SEC-07: Retention and legal hold

Retention must be configurable. Baseline defaults may be retained from the earlier plan but should be validated with department policy. Purge must:

* respect legal holds
* write tombstones
* produce audit entries

### SEC-08: Password Storage and Credential Management

**Algorithm selection:**
* Preferred: **Argon2id** (memory-hard, GPU-resistant, current OWASP recommendation).
* Acceptable fallback: scrypt with OWASP baseline parameters.
* Legacy / FIPS-constrained only: bcrypt (rounds ≥ 12). Note: bcrypt silently truncates inputs at 72 bytes — this is a correctness and security bug for passwords > 72 bytes.
* PBKDF2 is acceptable only where FIPS compliance explicitly mandates it.

**Storage format:** The algorithm identifier and cost parameters are stored alongside each hash (e.g., in the encoded verifier string). This enables in-place migration without schema changes.

**Transparent migration:** Existing bcrypt hashes are upgraded to Argon2id on the next successful login (rehash-on-login). No forced password resets are required for active users. Inactive accounts may be required to reset after a configurable migration deadline.

**Password policy (aligned to NIST SP 800-63B):**
* Minimum length: **8 characters** for single-factor password authentication.
* Maximum length: **128 characters**, enforced at every interface (UI, API, mobile). Prevents bcrypt truncation exploitation and CPU-exhaustion attacks via oversized inputs.
* Accepted characters: all printing ASCII, space, and Unicode (length counted in Unicode code points, not bytes).
* **No composition rules.** Uppercase/lowercase/digit/special character requirements are explicitly prohibited by NIST SP 800-63B. They cause predictable transformations without increasing real entropy and must not be enforced.
* Breached/common password blocklist screening applied at registration, password change, and password reset. Rejection messages provide guidance without revealing blocklist contents or candidates.
* Paste and autofill must be permitted at every interface. Password managers are a primary defense against credential reuse.

**Pepper (optional):** A server-side pepper may be applied as an additional layer (HMAC-SHA256 keyed pre-hash before Argon2id). If used, the pepper is stored in a separate secrets system, never in the user database. Pepper rotation requires an opportunistic upgrade plan (rehash on next login; forced reset for inactive accounts after a deadline).

**Unique salts:** Each password hash has a unique, CSPRNG-generated salt (minimum 16 bytes for Argon2id per RFC 9106). Library-managed encoding formats that embed the salt in the verifier string are preferred to avoid implementation errors.

### SEC-09: Session Token Lifecycle

**Token storage (browser clients):** Refresh tokens are delivered and stored as `HttpOnly`, `Secure`, `SameSite=Strict` cookies. Access tokens are short-lived (≤30 min) in-memory bearer tokens. Persistent localStorage is not used for session tokens; Web Storage is accessible to JavaScript and does not receive OS-level encryption at rest.

**Revocability:** Refresh tokens must be revocable. The minimum implementation is a per-user `last_logout_at` timestamp stored in the database. Any refresh token with `iat < last_logout_at` is rejected. This provides instant "invalidate all sessions" on logout, password change, or security event without requiring a token blocklist table.

**Session wall-clock limit:** `SESSION_MAX_HOURS` (default 8, configurable) is enforced by embedding a `session_created_at` claim in both access and refresh tokens. A refresh is rejected if `now() − session_created_at > SESSION_MAX_HOURS`, regardless of the token's own expiry.

**Rotation on key events:** New tokens with a fresh `session_created_at` are issued after: password change, MFA enrollment or removal, email address change, and admin-initiated role change.

**Cookie attributes summary:**
* `Secure` — prevents transmission over non-TLS connections.
* `HttpOnly` — prevents JavaScript access, reducing XSS token-exfiltration risk.
* `SameSite=Strict` — prevents the browser from sending the cookie on cross-site requests, mitigating portions of CSRF risk.

---

## 12. Testing and Acceptance Criteria (Adjusted)

### 12.1 Functional acceptance

* Email intake reliably creates CertificateDocument and ExtractionRun for valid submissions.
* Coordinator review queue works one-at-a-time with side-by-side view.
* No VerifiedCertificateRecord is created without Coordinator approval.
* Templates for the initial internal certificates operate template-first; unknown layouts fall back safely.

### 12.2 Notification acceptance

* Due and expiring reminders occur at 90/60/30 (both due date and expiration), to employee and Coordinator.
* Scheduler backfill produces no duplicates.

### 12.3 Security acceptance

* Non-city email senders are silently ignored.
* First-time city-domain senders in the GAL are auto-provisioned and processed.
* Distribution lists and city addresses not in the GAL are ignored.
* East-west traffic is mTLS under strict mode in mesh-covered environments.

**Authentication hardening (from SEC-01, SEC-08, SEC-09):**
* Timing test: "valid user, wrong password" vs "non-existent user" response time distributions overlap with no statistically significant difference (measured over ≥1000 requests).
* Enumeration test: login endpoint returns identical body, status code, and timing envelope for — wrong password, non-existent email, disabled account, and unconfigured account.
* Rate-limiting test: scripted login attempts at ≥10 req/s against a single account trigger graduated slowdown within ≤5 attempts.
* Truncation test: after Argon2id migration, a password of 73+ characters does not verify against the hash of the same password truncated to 72 characters (bcrypt truncation bug is absent).
* Length boundary test: passwords of exactly 8 and 128 characters are accepted at all auth interfaces; 7-character passwords are rejected.
* Composition-rule test: a password that satisfies only the length requirement (no uppercase, no digits, no special characters) is accepted.
* Forgot-password replay test: submitting the same reset token twice returns 400 on the second attempt; an expired token returns 400.
* Refresh-token revocation test: a refresh token issued before the most recent logout is rejected with 401.

### 12.4 “Useful by end of semester” criteria

* Monthly report generation is automated and does not require manual spreadsheet reconciliation.
* Manual entry is limited to corrections during review, not full transcription.

---

## 13. Key Configuration Defaults (Deployment-Configurable)

* Scheduler time zone (recommended local ops zone).
* Due reminders: [90, 60, 30].
* Expiration reminders: [90, 60, 30].
* File types: PDF, JPEG, PNG (V1).
* Email intake: allowed sender domains; directory allowlist mode.
* Template thresholds and ambiguity rules.
* Expiration handling: optional expiration allowed; missing expiration flagged but not treated as expired.
* Mesh rollout order: dev → staging → prod, permissive then strict.
* Retention durations and legal hold policies.

---

## 14. Decisions Captured for This Revision

1. **Primary intake is email-based employee self-submission** (Coordinator is not the uploader).
2. **Coordinator is the single human approver/corrector** (hard gate preserved).
3. **Visibility is Coordinator-only by default**; supervisor/executive access is handled via exports, not portal roles.
4. **Notifications and reminders use configurable day offsets** (default: 90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1, 0) for both due dates and expirations, to employee and Coordinator. Cadence is managed via alert rules (see Section 5.2.2).
5. **Service mesh mTLS is included** for east-west traffic as the standardized enforcement mechanism, without changing the core verification invariants.
6. **Employees have no web login.** The employee role is a tracking entity only; all employee interaction is via email.
7. **Admin is IT-only.** The Admin role is separated from Coordinator and limited to assigning/unassigning the Coordinator role. Admin has read-only access to audit logs for governance oversight but no access to certificate data or operational workflows.
8. **Name mismatches are auto-rejected** with a reply email to the sender, not flagged for review. This enforcement is bypassed for Coordinator manual uploads.
9. **Unknown city-domain senders in the GAL are auto-provisioned** as employee records. Non-city-domain emails are silently ignored. Distribution lists are ignored.
10. **Confidence scores are not shown to the reviewer.** They are retained internally for pipeline diagnostics but removed from the review UI.
11. **Extractions use a Processing → PendingReview state transition.** Documents do not appear in the review queue until extraction is complete.
12. **GPU auto-detection configures LLM parallelism.** >4 GB VRAM enables parallel consensus runs; otherwise sequential.
13. **Two onboarding acknowledgment forms** (HIPAA and Employee Policies) are processed through the standard extraction pipeline with annual renewal.
14. **Only three roles exist: Admin, Coordinator, Employee.** Manager and Reviewer roles were evaluated and explicitly excluded. They add complexity without matching the single-Coordinator operating model.
15. **Bulk Import is a supported intake channel** (`BULK_IMPORT`) for initial data migration. Bulk-imported certificates are pre-verified and bypass the extraction/review pipeline.
16. **Requirements and compliance are two linked views.** The Coordinator accesses requirement tracking at `/requirements` (operational table) and compliance reporting at `/compliance` (dashboard). Each page links to the other. The `/reports` alias redirects to `/compliance`.
17. **XLSX export is supported** alongside CSV for compliance and requirement reports.
18. **Review queue supports custom date ranges** in addition to preset filters (Any Age, Today, This Week, Older than 7 days).
19. **Compliance formula is explicit:** `(Compliant + Waived) / Total × 100%`, where unsatisfied requirements not yet within 30 days of due date count as compliant.
20. **Argon2id replaces bcrypt as the preferred KDF** for password storage (SEC-08). Existing bcrypt hashes are upgraded transparently via rehash-on-login; no forced password resets are required for active users.
21. **Password policy follows NIST SP 800-63B** (SEC-08): minimum 8 characters, maximum 128 characters, no composition rules (uppercase/lowercase/digit/special requirements are prohibited), all printing ASCII + Unicode accepted, paste and autofill permitted. Breached/common password blocklist screening applied at registration, password change, and password reset.
22. **Self-service forgot-password flow is in scope** (WF-10). Reset tokens are 32-byte CSPRNG values stored as SHA-256 hashes, one-time-use with 30-minute expiry. Reset atomically increments `token_version` and sets `last_logout_at`, invalidating all outstanding sessions.
23. **Refresh token revocation uses a per-user `last_logout_at` timestamp** (SEC-09). Tokens with `iat < last_logout_at` are rejected. `SESSION_MAX_HOURS` (default 8) is enforced by embedding `session_created_at` in tokens and rejecting refreshes that exceed the wall-clock limit.
24. **Login and account-recovery endpoints use per-account + per-IP graduated backoff** (SEC-01). Hard permanent lockouts are not used. Login error messages are generic regardless of failure reason (anti-enumeration).
25. **Coordinators and Admins cannot set passwords for other users** (WF-11). Employee accounts are created without a password; a setup email with a one-time link is sent automatically. Admins can resend the email via `POST /api/employees/{id}/send-setup-email`. This eliminates shared-secret provisioning and ensures each user chooses their own credential.
26. **Configuration replaces Upload card in navigation.** Certificate types, templates, and alert rules are managed through a unified Configuration page (Section 5.2). Manual upload remains available as an exception path within the system but is no longer a primary navigation destination.
27. **Certificate type owns periodicity.** Renewal period (`periodicity_months`) is an attribute of the CertificateType entity, not computed from individual certificates.
28. **Alert rules are managed configuration.** Notification cadence (day offsets, overdue behavior, send time) is stored in the AlertRule entity (Section 7.12) and read by the scheduler, replacing previously hardcoded constants.
29. **Issuing authority is template-authoritative.** The issuing organization is defined at the template level (Section 7.11), not extracted per document. This ensures consistency and avoids extraction noise.
30. **Audit log uses dual timestamps** (`created_at` for event time, `recorded_at` for database write time) and includes `correlation_id`, `source_service`, and `outcome` columns (Section 7.9).
31. **Admin has read-only audit log access** for governance oversight. Admin cannot modify audit records or access certificate data.

---
