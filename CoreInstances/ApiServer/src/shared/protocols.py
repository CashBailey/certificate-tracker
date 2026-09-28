"""
Protocol classes (interfaces) for the City of Laredo Certificate Management System.

These define the contracts that implementations must follow.
"""

from datetime import date, datetime
from typing import Optional, Protocol, runtime_checkable
from uuid import UUID

from .models import (
    AlertConfiguration,
    AuditLog,
    CertificateDocument,
    CertificateType,
    Employee,
    ExtractionRun,
    JobCursor,
    NotificationEvent,
    NormalizedDocument,
    PageImage,
    PasswordResetToken,
    RequirementAssignment,
    ReviewState,
    TemplateDefinition,
    TextSpan,
    VerifiedCertificateRecord,
)


# ==================== EXCEPTIONS ====================


class TemplateNotFoundError(Exception):
    """Raised when a template is not found in the registry."""

    pass


class TemplateVersionNotFoundError(Exception):
    """Raised when a specific template version is not found."""

    pass


class UploadValidationError(Exception):
    """Raised when uploaded file validation fails."""

    pass


class AuthorizationError(Exception):
    """Raised when user is not authorized to perform an action."""

    pass


class ReviewConflictError(Exception):
    """Raised when review state transition conflicts with current state."""

    pass


class ConcurrencyError(Exception):
    """Raised when optimistic locking fails."""

    pass


# ==================== CORE PROTOCOLS ====================


@runtime_checkable
class Clock(Protocol):
    """Protocol for getting current time."""

    def now(self) -> datetime:
        """Return current UTC datetime."""
        ...

    def today(self) -> date:
        """Return current UTC date."""
        ...


@runtime_checkable
class UuidGenerator(Protocol):
    """Protocol for generating UUIDs."""

    def generate(self) -> UUID:
        """Generate a new UUID."""
        ...


@runtime_checkable
class Storage(Protocol):
    """Protocol for object storage operations."""

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Store object with given key."""
        ...

    async def get(self, key: str) -> bytes:
        """Retrieve object by key."""
        ...

    async def delete(self, key: str) -> None:
        """Delete object by key."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if object exists."""
        ...


# ==================== REPOSITORY PROTOCOL ====================


@runtime_checkable
class Repository(Protocol):
    """Protocol for database operations."""

    # Employee operations
    async def get_employee_by_id(self, employee_id: int) -> Optional[Employee]:
        """Get employee by ID."""
        ...

    async def get_employee_by_email(self, email: str) -> Optional[Employee]:
        """Get employee by email."""
        ...

    async def get_employee_by_number(self, employee_number: str) -> Optional[Employee]:
        """Get employee by employee number."""
        ...

    async def list_employees(self) -> list[Employee]:
        """List all employees."""
        ...

    async def create_employee(self, employee: Employee) -> Employee:
        """Create a new employee."""
        ...

    async def update_employee_password(self, employee_id: int, password_hash: str) -> None:
        """Update employee password hash and increment token_version."""
        ...

    async def update_password_hash_only(self, employee_id: int, password_hash: str) -> None:
        """Update password hash WITHOUT bumping token_version (transparent rehash)."""
        ...

    async def update_employee_last_logout_at(self, employee_id: int, timestamp: datetime) -> None:
        """Set last_logout_at for refresh token revocation."""
        ...

    async def create_password_reset_token(
        self, employee_id: int, token_hash: str, expires_at: datetime
    ) -> None:
        """Insert a new password reset token record."""
        ...

    async def get_password_reset_token_by_hash(
        self, token_hash: str
    ) -> Optional[PasswordResetToken]:
        """Fetch password reset token by its SHA-256 hash."""
        ...

    async def mark_password_reset_token_used(self, token_id: int) -> None:
        """Mark a password reset token as used."""
        ...

    # Certificate type operations
    async def get_certificate_type_by_id(
        self, cert_type_id: int
    ) -> Optional[CertificateType]:
        """Get certificate type by ID."""
        ...

    async def get_certificate_type_by_name(
        self, name: str
    ) -> Optional[CertificateType]:
        """Get certificate type by name."""
        ...

    async def list_certificate_types(self) -> list[CertificateType]:
        """List all certificate types."""
        ...

    async def create_certificate_type(
        self, cert_type: CertificateType
    ) -> CertificateType:
        """Create a new certificate type."""
        ...

    async def update_certificate_type(
        self, cert_type_id: int, updates: dict
    ) -> Optional[CertificateType]:
        """Update a certificate type. Returns None if not found."""
        ...

    async def delete_certificate_type(self, cert_type_id: int) -> bool:
        """Delete a certificate type. Returns True if deleted, False if not found."""
        ...

    async def count_requirements_for_cert_type(self, cert_type_id: int) -> int:
        """Count requirement assignments referencing a certificate type."""
        ...

    # Requirement operations
    async def create_requirement(
        self, requirement: RequirementAssignment
    ) -> RequirementAssignment:
        """Create a new requirement assignment."""
        ...

    async def get_requirement_by_id(
        self, requirement_id: int
    ) -> Optional[RequirementAssignment]:
        """Get requirement by ID."""
        ...

    async def list_all_requirements(
        self, limit: Optional[int] = 10_000
    ) -> list[RequirementAssignment]:
        """List all requirement assignments across all employees.

        Default applies a 10,000-row safety cap. Pass ``limit=None`` to bypass
        the cap (only for endpoints that need every row, e.g. CSV/XLSX export
        and dashboard counter feed).
        """
        ...

    async def list_all_requirements_paginated(
        self,
        limit: int = 25,
        offset: int = 0,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[list[RequirementAssignment], int]:
        """List requirements with pagination, optional status filter, and optional search."""
        ...

    async def list_requirements_for_employee(
        self, employee_id: int
    ) -> list[RequirementAssignment]:
        """List all requirements for an employee."""
        ...

    async def list_requirements_due_between(
        self, start_date: date, end_date: date
    ) -> list[RequirementAssignment]:
        """List requirements due between dates."""
        ...

    async def update_requirement_status(self, requirement_id: int, status: str) -> None:
        """Update requirement status."""
        ...

    async def link_requirement_if_unset(
        self,
        requirement_id: int,
        verified_record_id: int,
        expected_employee_id: int,
        expected_certificate_type_id: int,
    ) -> bool:
        """Atomically satisfy one compatible, open, unwaived requirement."""
        ...

    async def find_open_requirement_by_cert_type(
        self, employee_id: int, certificate_type_name: str
    ) -> Optional[int]:
        """Find an unsatisfied requirement matching employee + cert type name."""
        ...

    async def waive_requirement(
        self,
        requirement_id: int,
        waived_by_id: int,
        reason: str,
        expiration: Optional[date] = None,
    ) -> None:
        """Mark requirement as waived."""
        ...

    # Document operations
    async def create_document(
        self, document: CertificateDocument
    ) -> CertificateDocument:
        """Create a new document record."""
        ...

    async def get_document_by_id(
        self, document_id: int
    ) -> Optional[CertificateDocument]:
        """Get document by ID."""
        ...

    async def list_documents_for_employee(
        self, employee_id: int
    ) -> list[CertificateDocument]:
        """List all documents for an employee."""
        ...

    # Extraction operations
    async def create_extraction(self, extraction: ExtractionRun) -> ExtractionRun:
        """Create a new extraction run."""
        ...

    async def get_extraction_by_id(self, extraction_id: int) -> Optional[ExtractionRun]:
        """Get extraction by ID."""
        ...

    async def list_extractions_by_state(
        self, state: ReviewState
    ) -> list[ExtractionRun]:
        """List extractions by review state."""
        ...

    async def list_all_extractions(
        self, limit: Optional[int] = 10_000
    ) -> list[ExtractionRun]:
        """List all extractions regardless of review state.

        Default applies a 10,000-row safety cap. Pass ``limit=None`` to bypass.
        """
        ...

    async def try_transition_extraction_review_state(
        self,
        extraction_id: int,
        expected_state: ReviewState,
        expected_version: int,
        new_state: ReviewState,
        reviewed_by_id: Optional[int] = None,
    ) -> bool:
        """
        Attempt to transition extraction review state with optimistic locking.
        Returns True if transition succeeded, False if version conflict.
        """
        ...

    # Verified record operations
    async def insert_verified_record_idempotent(
        self, record: VerifiedCertificateRecord
    ) -> VerifiedCertificateRecord:
        """
        Insert verified record with idempotency guarantee on extraction_id.
        Returns existing record if already exists.
        """
        ...

    async def get_verified_record_by_extraction_id(
        self, extraction_id: int
    ) -> Optional[VerifiedCertificateRecord]:
        """Get verified record by extraction ID."""
        ...

    async def list_verified_records_for_employee(
        self, employee_id: int
    ) -> list[VerifiedCertificateRecord]:
        """List all verified records for an employee."""
        ...

    async def list_verified_records_expiring_between(
        self,
        start_date: date,
        end_date: date,
    ) -> list[VerifiedCertificateRecord]:
        """List verified records expiring between dates."""
        ...

    async def list_verified_records_created_between(
        self,
        start_date: date,
        end_date: date,
    ) -> list[VerifiedCertificateRecord]:
        """List verified records created between dates (inclusive)."""
        ...

    # Notification operations
    async def insert_notification_if_absent(
        self, notification: NotificationEvent
    ) -> bool:
        """
        Insert notification with idempotency guarantee on dedupe_key.
        Returns True if inserted, False if already exists.
        """
        ...

    async def list_undelivered_notifications(
        self, limit: int = 5000
    ) -> list[NotificationEvent]:
        """List undelivered notifications."""
        ...

    async def mark_notification_delivered(self, notification_id: int) -> None:
        """Mark notification as delivered."""
        ...

    async def mark_notifications_delivered_batch(
        self, notification_ids: list[int]
    ) -> None:
        """Mark multiple notifications as delivered."""
        ...

    async def mark_notification_read(self, notification_id: int) -> None:
        """Mark notification as read."""
        ...

    async def list_notifications_for_user(
        self, employee_id: int, unread_only: bool = False, limit: int = 100
    ) -> list[NotificationEvent]:
        """List notifications for a user."""
        ...

    async def get_notification_by_id(
        self, notification_id: int
    ) -> Optional[NotificationEvent]:
        """Get notification by ID."""
        ...

    async def mark_all_notifications_read(self, employee_id: int) -> int:
        """Mark all notifications as read for a user."""
        ...

    async def count_unread_notifications(self, employee_id: int) -> int:
        """Count unread notifications for a user."""
        ...

    # Alert configuration operations
    async def get_alert_configuration(self) -> Optional[AlertConfiguration]:
        """Get the singleton alert configuration."""
        ...

    async def update_alert_configuration(
        self, config: AlertConfiguration
    ) -> AlertConfiguration:
        """Update the singleton alert configuration."""
        ...

    # Job cursor operations
    async def upsert_job_cursor(self, cursor: JobCursor) -> None:
        """
        Upsert job cursor with monotonic date guarantee.
        Raises ValueError if new date is before existing date.
        """
        ...

    async def get_job_cursor(self, job_name: str) -> Optional[JobCursor]:
        """Get job cursor by name."""
        ...

    # Audit log operations
    async def create_audit_log(self, log: AuditLog) -> AuditLog:
        """Create an audit log entry."""
        ...

    async def list_audit_logs(
        self,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        action: Optional[str] = None,
        employee_id: Optional[int] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        source_service: Optional[str] = None,
        outcome: Optional[str] = None,
        actor_role: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[AuditLog], int]:
        """List audit logs with optional filters, pagination, and total count."""
        ...


# ==================== PDF & OCR PROTOCOLS ====================


@runtime_checkable
class PdfTextExtractor(Protocol):
    """Protocol for extracting text from PDFs."""

    def extract_text_with_positions(self, pdf_bytes: bytes) -> list[TextSpan]:
        """Extract text with bounding box positions from PDF."""
        ...


@runtime_checkable
class PdfRasterizer(Protocol):
    """Protocol for rasterizing PDFs to images."""

    def rasterize_pages(self, pdf_bytes: bytes, dpi: int = 300) -> list[PageImage]:
        """Rasterize all pages of PDF to images."""
        ...


@runtime_checkable
class ImagePreprocessor(Protocol):
    """Protocol for preprocessing images."""

    def deskew(self, image_bytes: bytes) -> bytes:
        """Deskew (straighten) an image."""
        ...

    def denoise(self, image_bytes: bytes) -> bytes:
        """Remove noise from an image."""
        ...


@runtime_checkable
class OcrEngine(Protocol):
    """Protocol for OCR operations."""

    async def ocr_region(
        self,
        page_image: PageImage,
        bbox_norm: tuple[float, float, float, float],
    ) -> list[TextSpan]:
        """
        Perform OCR on a specific region of a page image.
        Returns text spans with positions relative to the region.
        """
        ...


# ==================== TEMPLATE PROTOCOLS ====================


@runtime_checkable
class TemplateRegistry(Protocol):
    """Protocol for template registry operations."""

    def get_template(
        self, template_id: str, version: Optional[int] = None
    ) -> TemplateDefinition:
        """
        Get template by ID and optional version.
        If version is None, returns latest version.
        Raises TemplateNotFoundError or TemplateVersionNotFoundError.
        """
        ...

    def list_templates(self) -> list[TemplateDefinition]:
        """List all templates (latest versions only)."""
        ...

    def get_all_versions(self, template_id: str) -> list[TemplateDefinition]:
        """Get all versions of a template."""
        ...

    def get_registry_hash(self) -> str:
        """Get hash of entire registry for cache invalidation."""
        ...


@runtime_checkable
class OptionalTemplateClassifier(Protocol):
    """Optional protocol for ML-based template classification."""

    async def classify_document(
        self, document: NormalizedDocument
    ) -> Optional[tuple[str, int, float]]:
        """
        Classify document to a template.
        Returns (template_id, version, confidence) or None.
        """
        ...
