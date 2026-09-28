"""
SQLAlchemy ORM models for the City of Laredo Certificate Management System.

Uses SQLAlchemy 2.0 declarative mapping with async support.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# ==================== CERTIFICATES SCHEMA ====================


class EmployeeORM(Base):
    """Employee ORM model."""

    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("email", name="uq_employees_email"),
        UniqueConstraint("employee_number", name="uq_employees_employee_number"),
        CheckConstraint(
            "role IN ('Coordinator', 'Admin', 'Employee')",
            name="ck_employees_role",
        ),
        {"schema": "certificates"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_number: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Email-intake has column-level INSERT permission that deliberately omits
    # role. PostgreSQL supplies Employee, preventing that parser-facing service
    # from provisioning an authenticating Coordinator/Admin account.
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="Employee"
    )
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    manager_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )
    # LMS (Learning Management System) username/alias for integration
    lms_username_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    # Incremented on password change to invalidate all existing JWTs
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    # Set on explicit logout for refresh token revocation (SEC-09)
    last_logout_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # DB-authoritative progressive lockout state (migration 037). Keeping
    # these mapped prevents autogenerate from proposing destructive drops.
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lockout_level: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    failed_login_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    last_failed_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_lockout_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PasswordResetTokenORM(Base):
    """Password reset token ORM model (WF-10)."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = {"schema": "certificates"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("certificates.employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GALDirectoryORM(Base):
    """Global Address List directory entry for city employee lookup (INV-09)."""

    __tablename__ = "gal_directory"
    __table_args__ = (
        UniqueConstraint("email", name="uq_gal_directory_email"),
        {"schema": "certificates"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_person: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


class CertificateTypeORM(Base):
    """Certificate type ORM model."""

    __tablename__ = "certificate_types"
    __table_args__ = (
        UniqueConstraint("name", name="uq_certificate_types_name"),
        {"schema": "certificates"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    validity_period_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class RequirementAssignmentORM(Base):
    """Requirement assignment ORM model."""

    __tablename__ = "requirement_assignments"
    __table_args__ = {"schema": "certificates"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=False, index=True
    )
    certificate_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certificates.certificate_types.id"), nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="NotStarted", index=True
    )
    satisfied_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("certificates.verified_certificate_records.id", use_alter=True),
        nullable=True,
    )
    waived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    waived_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True
    )
    waiver_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    waiver_expiration: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Coordinator who created this requirement assignment
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True, index=True
    )
    # Optional: supervisor who requested this requirement (origin tracking)
    requested_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class CertificateDocumentORM(Base):
    """Certificate document ORM model."""

    __tablename__ = "certificate_documents"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_certificate_documents_storage_key"),
        CheckConstraint(
            "acting_as IN ('Self', 'Coordinator')",
            name="ck_certificate_documents_acting_as",
        ),
        CheckConstraint(
            "file_type IN ('application/pdf', 'image/png', 'image/jpeg', 'image/tiff')",
            name="ck_certificate_documents_file_type",
        ),
        CheckConstraint(
            "intake_channel IN ('MANUAL_UPLOAD', 'EMAIL', 'BULK_IMPORT')",
            name="ck_certificate_documents_intake_channel",
        ),
        {"schema": "certificates"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=False
    )
    acting_as: Mapped[str] = mapped_column(String(20), nullable=False)
    intake_channel: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="MANUAL_UPLOAD"
    )
    source_email_message_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("notifications.email_intake_messages.id"), nullable=True
    )
    # Optional link to requirement this document was uploaded to satisfy
    target_requirement_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("certificates.requirement_assignments.id"),
        nullable=True,
        index=True,
    )
    # File hash for deduplication (SHA-256, 64-char hex)
    file_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    # Retention and legal hold fields
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    legal_hold: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    retention_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ExtractionRunORM(Base):
    """Extraction run ORM model."""

    __tablename__ = "extraction_runs"
    __table_args__ = (
        CheckConstraint(
            "review_state IN ('Processing', 'PendingReview', 'Approved', 'Rejected')",
            name="ck_extraction_runs_review_state",
        ),
        {"schema": "certificates"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("certificates.certificate_documents.id"),
        nullable=False,
        index=True,
    )
    review_state: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="Processing", index=True
    )
    extracted_fields: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    needs_review_reasons: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    template_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    template_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    template_issuing_authority: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    template_match_evidence: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
    review_assist: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Field-level provenance captured at extraction time (DM-02)
    # Structure: {field_name: {bbox, page, zone_id, source}}
    field_evidence: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class VerifiedCertificateRecordORM(Base):
    """Verified certificate record ORM model."""

    __tablename__ = "verified_certificate_records"
    __table_args__ = (
        UniqueConstraint(
            "extraction_id", name="uq_verified_certificate_records_extraction_id"
        ),
        {"schema": "certificates"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certificates.extraction_runs.id"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certificates.certificate_documents.id"), nullable=False
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=False, index=True
    )
    certificate_holder_name: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    certificate_type: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    certificate_number: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    issuing_authority: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
    )
    training_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    license_class: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    endorsements: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Reviewer attribution
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True, index=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Per-field provenance information (source_method, entry_mode, original values)
    field_provenance: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    # Retention and legal hold fields
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    legal_hold: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )


# ==================== NOTIFICATIONS SCHEMA ====================


class NotificationEventORM(Base):
    """Notification event ORM model."""

    __tablename__ = "notification_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_notification_events_dedupe_key"),
        CheckConstraint(
            "notification_type IN ('RequirementDueSoon', 'RequirementDueTomorrow', 'RequirementOverdue', 'RequirementEscalation', 'CertificateExpiringSoon', 'CertificateExpired')",
            name="ck_notification_events_notification_type",
        ),
        {"schema": "notifications"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient_employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(500), nullable=False)
    related_requirement_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    related_certificate_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    # Logical trigger date for the notification (DM-03)
    # e.g., for "due soon" notification, this is the due date, not creation time
    effective_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
    )
    delivered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", index=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
        index=True,
    )


class AlertConfigurationORM(Base):
    """Singleton alert configuration ORM model."""

    __tablename__ = "alert_configuration"
    __table_args__ = {"schema": "notifications"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requirement_reminder_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False
    )
    certificate_reminder_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False
    )
    daily_overdue_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    global_send_hour: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="6"
    )
    global_send_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True
    )


class JobCursorORM(Base):
    """Job cursor ORM model."""

    __tablename__ = "job_cursors"
    __table_args__ = {"schema": "notifications"}

    job_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_success_date: Mapped[date] = mapped_column(Date, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class EmailIntakeMessageORM(Base):
    """Email intake message ORM model for tracking processed emails."""

    __tablename__ = "email_intake_messages"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_email_intake_messages_message_id"),
        CheckConstraint(
            "processing_state IN ('PROCESSED', 'QUARANTINED', 'FAILED')",
            name="ck_email_intake_messages_state",
        ),
        {"schema": "notifications"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    from_address: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    attachment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processing_state: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    error_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    employee_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True
    )
    # JSONB array of SHA-256 hashes for all attachments in the email
    attachment_hashes: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )


# ==================== AUDIT SCHEMA ====================


class DeletionTombstoneORM(Base):
    """Deletion tombstone ORM model for tracking hard-deleted entities."""

    __tablename__ = "deletion_tombstones"
    __table_args__ = {"schema": "audit"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    deleted_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True
    )
    deletion_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    entity_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class AuditLogORM(Base):
    """Audit log ORM model."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('System', 'Employee')", name="ck_audit_logs_actor_type"
        ),
        CheckConstraint(
            "(actor_type = 'System' AND employee_id IS NULL) OR (actor_type = 'Employee' AND employee_id IS NOT NULL)",
            name="ck_audit_logs_actor_constraints",
        ),
        {"schema": "audit"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    employee_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    initiated_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("certificates.employees.id"), nullable=True
    )
    # Dual timestamps: when the event occurred vs when the row was recorded
    occurred_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
        index=True,
    )
    recorded_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
        index=True,
    )
    # Actor's role at time of action (Admin/Coordinator/Employee); NULL for System
    actor_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # UUID grouping related audit entries within a request/workflow
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    # Which service produced this entry (api/extraction-worker/scheduler-worker/email-intake)
    source_service: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    )
    # Result of the action (success/failure/denied)
    outcome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Client IP address; NULL for system/worker actions
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
