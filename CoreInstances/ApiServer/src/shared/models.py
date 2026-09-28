"""
Shared data models for the City of Laredo Certificate Management System.

This module contains all enums, dataclasses, and constants used across the application.
Single source of truth - copied into worker containers at build time.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional


# ==================== ENUMS ====================


class Role(str, Enum):
    """User roles in the system (HLSD Decision 14).

    - COORDINATOR: Full web UI access — reviews, uploads, reports,
      employee management, requirement assignments (INV-06).
    - EMPLOYEE: Submit-only via email. No web login (SEC-01).
    - ADMIN: IT safety net — can assign/unassign Coordinator role only.
      No certificate operations (SEC-04).
    """

    COORDINATOR = "Coordinator"
    EMPLOYEE = "Employee"
    ADMIN = "Admin"


class RequirementStatus(str, Enum):
    """Status of a requirement assignment.

    Lifecycle flow:
    - NOT_STARTED: No document uploaded yet
    - SUBMITTED: Document uploaded, pending extraction/review
    - IN_PROGRESS: Extraction started but not yet approved
    - SATISFIED: Extraction approved, requirement fulfilled
    - OVERDUE: Due date passed without satisfaction
    - WAIVED: Requirement waived by coordinator
    """

    NOT_STARTED = "NotStarted"
    SUBMITTED = "Submitted"  # Document uploaded, pending review
    IN_PROGRESS = "InProgress"
    SATISFIED = "Satisfied"
    OVERDUE = "Overdue"
    WAIVED = "Waived"


class CertificateLifecycleStatus(str, Enum):
    """Lifecycle status of a certificate."""

    VALID = "Valid"
    EXPIRING_SOON = "ExpiringSoon"
    EXPIRED = "Expired"
    NOT_APPLICABLE = "NotApplicable"


@dataclass
class CertificateLifecycleResult:
    """
    Result of computing certificate lifecycle status.

    Contains both the status enum and a flag indicating if the expiration
    date is missing. Per SM-03: when expiration_date is null, the certificate
    is considered Active but with missing_expiration flag set to True.

    This allows callers to distinguish between:
    - Certificate with no expiration (non-expiring cert): status=VALID, missing_expiration=False
    - Certificate missing expiration data: status=VALID, missing_expiration=True
    """

    status: CertificateLifecycleStatus
    missing_expiration: bool = False


class RequirementComplianceStatus(str, Enum):
    """Compliance status for requirements."""

    COMPLIANT = "Compliant"
    DUE_SOON = "DueSoon"
    OVERDUE = "Overdue"
    WAIVED = "Waived"


class NotificationType(str, Enum):
    """Types of notifications that can be sent."""

    REQUIREMENT_DUE_SOON = "RequirementDueSoon"
    REQUIREMENT_DUE_TOMORROW = "RequirementDueTomorrow"
    REQUIREMENT_OVERDUE = "RequirementOverdue"
    REQUIREMENT_ESCALATION = "RequirementEscalation"
    CERTIFICATE_EXPIRING_SOON = "CertificateExpiringSoon"
    CERTIFICATE_EXPIRED = "CertificateExpired"


class ReviewState(str, Enum):
    """Review state of an extraction.

    State machine (SM-01):
        Processing → PendingReview → Approved
        Processing → PendingReview → Rejected

    Processing: extraction pipeline is running; must NOT appear in review queue.
    PendingReview: extraction complete, awaiting Coordinator review.
    """

    PROCESSING = "Processing"
    PENDING_REVIEW = "PendingReview"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class AuditActorType(str, Enum):
    """Type of actor performing an action."""

    SYSTEM = "System"
    EMPLOYEE = "Employee"


# ==================== ENTITY MODELS ====================


@dataclass
class Employee:
    """Employee entity."""

    id: int
    employee_number: str
    first_name: str
    last_name: str
    email: str
    role: Role
    manager_id: Optional[int] = None
    password_hash: Optional[str] = None
    is_active: bool = True
    lms_username_id: Optional[str] = None  # LMS alias for integration
    token_version: int = 1  # Incremented on password change to invalidate JWTs
    last_logout_at: Optional[datetime] = None  # For refresh token revocation (SEC-09)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class PasswordResetToken:
    """Password reset token record (WF-10)."""

    id: int
    employee_id: int
    token_hash: str  # SHA-256 hex digest of the raw token
    expires_at: datetime
    created_at: datetime
    used_at: Optional[datetime] = None


@dataclass
class CertificateType:
    """Certificate type definition."""

    id: int
    name: str
    description: str
    validity_period_days: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class RequirementAssignment:
    """Requirement assignment to an employee."""

    id: int
    employee_id: int
    certificate_type_id: int
    due_date: date
    status: RequirementStatus
    satisfied_by_id: Optional[int] = None
    waived_at: Optional[datetime] = None
    waived_by_id: Optional[int] = None
    waiver_reason: Optional[str] = None
    waiver_expiration: Optional[date] = None
    created_by_id: Optional[int] = None  # Coordinator who created the assignment
    requested_by_id: Optional[int] = None  # Supervisor who requested (origin tracking)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class IntakeChannel(str, Enum):
    """Channel through which a document was received."""

    MANUAL_UPLOAD = "MANUAL_UPLOAD"
    EMAIL = "EMAIL"
    BULK_IMPORT = "BULK_IMPORT"


class EmailProcessingState(str, Enum):
    """Processing state for email intake messages."""

    PROCESSED = "PROCESSED"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


@dataclass
class CertificateDocument:
    """Uploaded certificate document."""

    id: int
    employee_id: int
    storage_key: str
    file_name: str
    file_type: str
    file_size_bytes: int
    uploaded_by_id: int
    acting_as: str
    intake_channel: IntakeChannel = IntakeChannel.MANUAL_UPLOAD
    source_email_message_id: Optional[int] = None
    target_requirement_id: Optional[int] = None  # Requirement this document satisfies
    file_hash: Optional[str] = None  # SHA-256 hash for deduplication
    created_at: Optional[datetime] = None


@dataclass
class ExtractionRun:
    """Record of an extraction run on a document."""

    id: int
    document_id: int
    review_state: ReviewState
    extracted_fields: dict[str, Any]
    needs_review: bool
    needs_review_reasons: list[str]
    template_id: Optional[str] = None
    template_version: Optional[int] = None
    template_match_evidence: Optional[dict[str, Any]] = None
    review_assist: Optional[dict[str, Any]] = None
    # Field-level provenance captured at extraction time (DM-02)
    # Structure: {field_name: {bbox, page, zone_id, source}}
    field_evidence: Optional[dict[str, Any]] = None
    reviewed_by_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    review_state_version: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class VerifiedCertificateRecord:
    """Verified certificate record after approval."""

    id: int
    extraction_id: int
    document_id: int
    employee_id: int
    certificate_holder_name: Optional[str] = None
    certificate_type: Optional[str] = None
    certificate_number: Optional[str] = None
    issuing_authority: Optional[str] = None
    issue_date: Optional[date] = None
    expiration_date: Optional[date] = None
    training_hours: Optional[float] = None
    license_class: Optional[str] = None
    endorsements: Optional[str] = None
    reviewed_by_id: Optional[int] = None  # Reviewer who approved
    reviewed_at: Optional[datetime] = None  # When approved
    field_provenance: Optional[dict[str, Any]] = None  # Per-field provenance info
    created_at: Optional[datetime] = None


@dataclass
class NotificationEvent:
    """Notification event to be delivered."""

    id: int
    notification_type: NotificationType
    recipient_employee_id: int
    subject: str
    body: str
    dedupe_key: str
    related_requirement_id: Optional[int] = None
    related_certificate_id: Optional[int] = None
    # Logical trigger date for the notification (DM-03)
    # e.g., for "due soon" notification, this is the due date
    effective_date: Optional[date] = None
    delivered: bool = False
    delivered_at: Optional[datetime] = None
    read: bool = False
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


@dataclass
class AuditLog:
    """Audit log entry."""

    id: int
    actor_type: AuditActorType
    employee_id: Optional[int]
    action: str
    target_type: str
    target_id: str
    details: Optional[dict[str, Any]] = None
    initiated_by_id: Optional[int] = None
    occurred_at_utc: Optional[datetime] = None
    recorded_at_utc: Optional[datetime] = None
    actor_role: Optional[str] = None
    correlation_id: Optional[str] = None
    source_service: Optional[str] = None
    outcome: Optional[str] = None
    ip_address: Optional[str] = None


@dataclass
class DeletionTombstone:
    """Tombstone record for hard-deleted entities."""

    id: int
    entity_type: str
    entity_id: int
    deleted_at: datetime
    deleted_by_id: Optional[int] = None
    deletion_reason: Optional[str] = None
    entity_metadata: Optional[dict[str, Any]] = None


@dataclass
class AlertConfiguration:
    """Singleton alert configuration for notification behavior.

    Controls reminder intervals, daily-overdue toggle, and global send time.
    Always a single row (id=1) — seeded by migration, updated via API.
    """

    id: int
    requirement_reminder_days: list[int]
    certificate_reminder_days: list[int]
    daily_overdue_enabled: bool = True
    global_send_hour: int = 6
    global_send_minute: int = 0
    updated_at: Optional[datetime] = None
    updated_by_id: Optional[int] = None


@dataclass
class JobCursor:
    """Job cursor for tracking scheduled job progress."""

    job_name: str
    last_success_date: date
    updated_at: Optional[datetime] = None


@dataclass
class EmailIntakeMessage:
    """Email intake message for tracking processed emails."""

    id: int
    message_id: str
    from_address: str
    received_at: datetime
    processing_state: EmailProcessingState
    subject: Optional[str] = None
    attachment_count: Optional[int] = None
    error_reason: Optional[str] = None
    employee_id: Optional[int] = None
    attachment_hashes: Optional[list[str]] = None  # SHA-256 hashes of attachments
    created_at: Optional[datetime] = None


# ==================== EXTRACTION TYPES ====================


@dataclass
class ExtractionConfidence:
    """Confidence metrics for an extraction."""

    zone: float
    ocr: float
    parse: float
    validate: float
    overall: float


@dataclass
class ExtractedFieldValue:
    """A field extracted from a document."""

    field_name: str
    value: Optional[str]
    confidence: ExtractionConfidence
    extraction_source: str  # "zone" | "generic"
    needs_review: bool
    source_page_num: Optional[int] = None
    source_bbox_norm: Optional[tuple[float, float, float, float]] = None
    parse_success: Optional[bool] = None
    validation_passed: Optional[bool] = None


@dataclass
class VerifiedFieldValue:
    """A verified field value after review."""

    field_name: str
    value: Optional[str]
    source_method: str  # from EXTRACTION_SOURCES
    entry_mode: str  # from ENTRY_MODES
    original_machine_confidence: Optional[float] = None
    original_machine_value: Optional[str] = None


@dataclass
class GenericFieldCandidate:
    """A candidate match for generic field extraction."""

    field_name: str
    value: str
    confidence: float
    match_span: tuple[int, int]
    pattern_name: str


@dataclass
class GenericExtractionResult:
    """Result of generic field extraction."""

    field_name: str
    best_candidate: Optional[GenericFieldCandidate]
    all_candidates: list[GenericFieldCandidate]


@dataclass
class SpanMatchInfo:
    """Information about a span match in searchable text."""

    char_start: int
    char_end: int
    matched_text: str


@dataclass
class DocumentToken:
    """A token in the document with position information."""

    token_id: str
    text: str
    bbox_norm: tuple[float, float, float, float]  # x0, y0, x1, y1 normalized to 0-1
    page_num: int
    confidence: float = 1.0


@dataclass
class TextSpan:
    """A span of text with bounding box."""

    text: str
    bbox_norm: tuple[float, float, float, float]
    confidence: float


@dataclass
class PageImage:
    """Rasterized page image."""

    page_num: int
    image_bytes: bytes
    width_px: int
    height_px: int
    dpi: int


@dataclass
class SearchableText:
    """Searchable text representation of document."""

    full_text: str
    token_map: dict[tuple[int, int], list[str]]  # (char_start, char_end) -> [token_ids]


@dataclass
class NormalizedPage:
    """Normalized representation of a document page."""

    page_num: int
    tokens: list[DocumentToken]
    page_text: str
    is_digital: bool
    raster: Optional[PageImage] = None


@dataclass
class NormalizedDocument:
    """Normalized representation of entire document."""

    pages: list[NormalizedPage]
    searchable_text: SearchableText
    total_pages: int


@dataclass
class NormalizationConfig:
    """Configuration for document normalization."""

    raster_dpi: int = 300
    digital_text_confidence: float = 1.0
    min_token_confidence: float = 0.3
    enable_deskew: bool = True


# ==================== TEMPLATE TYPES ====================


@dataclass
class ZoneParsing:
    """Parsing configuration for a zone."""

    regex_pattern: Optional[str] = None
    date_format: Optional[str] = None
    allow_multiline: bool = False
    strip_whitespace: bool = True


@dataclass
class ZoneValidators:
    """Validators for a zone."""

    min_length: Optional[int] = None
    max_length: Optional[int] = None
    regex_match: Optional[str] = None
    date_range: Optional[tuple[str, str]] = None


@dataclass
class FieldZone:
    """Zone definition for template-based extraction."""

    field_name: str
    bbox_norm: tuple[float, float, float, float]
    parsing: ZoneParsing
    validators: ZoneValidators
    required: bool = False
    hardcoded_value: Optional[str] = None


@dataclass
class TemplateDetection:
    """Detection configuration for template matching."""

    anchor_keywords: list[str]
    anchor_regex: Optional[str] = None
    min_keyword_matches: int = 2
    min_confidence_score: float = 0.7


@dataclass
class TemplateAlignment:
    """Alignment configuration for template."""

    reference_anchors: list[tuple[str, tuple[float, float]]]  # (text, (x, y))
    tolerance_bbox: float = 0.02
    min_anchors_matched: int = 2


@dataclass
class TemplateReviewRules:
    """Review rules for template."""

    always_review_fields: list[str] = field(default_factory=list)
    skip_generic_if_zone_confident: bool = True


@dataclass
class TemplateDefinition:
    """Complete template definition."""

    template_id: str
    version: int
    name: str
    description: str
    detection: TemplateDetection
    alignment: TemplateAlignment
    zones: list[FieldZone]
    review_rules: TemplateReviewRules
    issuing_authority: Optional[str] = None
    certificate_type_ref: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


# ==================== CONSTANTS ====================

# Confidence component caps
CONFIDENCE_CAPS = {
    "zone": 0.35,
    "ocr": 0.40,
    "parse": 0.35,
    "validate": 0.25,
}

# Per-field confidence thresholds
FIELD_CONFIDENCE_THRESHOLDS = {
    "certificate_holder_name": 0.80,
    "certificate_type": 0.85,
    "certificate_number": 0.80,
    "issuing_authority": 0.75,
    "issue_date": 0.90,
    "expiration_date": 0.90,
    "training_hours": 0.70,
    "license_class": 0.75,
    "endorsements": 0.65,
}

# Default threshold for needs_review flag
DEFAULT_NEEDS_REVIEW_BELOW = 0.75

# Overall extraction confidence threshold
EXTRACTION_CONFIDENCE_THRESHOLD = 0.70

# Match quality penalty when multiple candidates found for a field
MULTIPLE_CANDIDATE_MATCH_QUALITY = 0.8

# Canonical field names (10 fields)
CANONICAL_FIELDS = [
    "certificate_holder_name",
    "certificate_type",
    "certificate_number",
    "issuing_authority",
    "issue_date",
    "expiration_date",
    "training_hours",
    "license_class",
    "endorsements",
    "employee_id",
]

# Extraction sources
EXTRACTION_SOURCES = {
    "TEMPLATE_ZONE": "template_zone",
    "GENERIC_PATTERN": "generic_pattern",
    "MANUAL_ENTRY": "manual_entry",
    "MANUAL_CORRECTION": "manual_correction",
}

# Source methods for verified fields
SOURCE_METHODS = {
    "MACHINE_TEMPLATE": "machine_template",
    "MACHINE_GENERIC": "machine_generic",
    "HUMAN_CONFIRMED": "human_confirmed",
    "HUMAN_CORRECTED": "human_corrected",
    "HUMAN_ENTERED": "human_entered",
}

# Entry modes for verified fields
ENTRY_MODES = {
    "EXTRACTED": "extracted",
    "CONFIRMED": "confirmed",
    "CORRECTED": "corrected",
    "MANUAL": "manual",
}

# Pipeline version for tracking changes
PIPELINE_VERSION = "1.0.0"
