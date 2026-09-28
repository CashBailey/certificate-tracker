"""
Pydantic schemas for API request/response models.
"""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, EmailStr


# ==================== REQUIREMENT SCHEMAS ====================


class RequirementCreate(BaseModel):
    """Request to create a requirement assignment."""

    employee_id: int = Field(..., description="ID of employee to assign requirement to")
    certificate_type_id: int = Field(..., description="ID of certificate type required")
    due_date: date = Field(..., description="Due date for the requirement")


class RequirementWaive(BaseModel):
    """Request to waive a requirement."""

    reason: str = Field(..., min_length=10, max_length=1000, description="Reason for waiver")
    expiration: Optional[date] = Field(
        None, description="Optional waiver expiration date"
    )


class RequirementResponse(BaseModel):
    """Requirement assignment response."""

    id: int
    employee_id: int
    employee_name: Optional[str] = None
    certificate_type_id: int
    due_date: date
    status: str
    satisfied_by_id: Optional[int] = None
    expiration_date: Optional[date] = None
    waived_at: Optional[datetime] = None
    waived_by_id: Optional[int] = None
    waiver_reason: Optional[str] = None
    waiver_expiration: Optional[date] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RequirementsPageResponse(BaseModel):
    """Paginated requirements response."""

    total: int
    page: int
    page_size: int
    items: list[RequirementResponse]


class ImportRowResult(BaseModel):
    """Result for a single row in a bulk import operation."""

    row: int
    status: str  # "created", "skipped", "error"
    requirement_id: Optional[int] = None
    reason: Optional[str] = None


class RequirementImportResponse(BaseModel):
    """Response for bulk requirement import operation."""

    success: bool
    dry_run: bool
    total_rows: int
    created: int
    skipped: int
    errors: int
    results: list[ImportRowResult]


# ==================== DOCUMENT SCHEMAS ====================


class DocumentUploadResponse(BaseModel):
    """Response after document upload."""

    document_id: int
    extraction_id: int
    file_name: str
    file_type: str
    file_size_bytes: int
    message: str = "Document uploaded successfully"


class DocumentResponse(BaseModel):
    """Document response."""

    id: int
    employee_id: int
    file_name: str
    file_type: str
    file_size_bytes: int
    uploaded_by_id: int
    acting_as: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== EXTRACTION SCHEMAS ====================


class ExtractionResponse(BaseModel):
    """Extraction run response."""

    id: int
    document_id: int
    review_state: str
    extracted_fields: dict[str, Any]
    needs_review: bool
    needs_review_reasons: list[str]
    template_id: Optional[str] = None
    template_version: Optional[int] = None
    template_match_evidence: Optional[dict] = None
    review_assist: Optional[dict] = None
    # Field-level provenance captured at extraction time (DM-02)
    # Structure: {field_name: {bbox, page, zone_id, source}}
    field_evidence: Optional[dict] = None
    reviewed_by_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExtractionApprove(BaseModel):
    """Request to approve an extraction."""

    corrections: Optional[dict[str, str]] = Field(
        None, description="Field corrections {field_name: corrected_value}"
    )
    requirement_id: Optional[int] = Field(
        None, ge=1, description="Requirement ID to satisfy with this certificate"
    )


class ExtractionReject(BaseModel):
    """Request to reject an extraction."""

    reason: str = Field(..., min_length=10, max_length=1000, description="Reason for rejection")


# ==================== REPORT SCHEMAS ====================


class ComplianceStatusCount(BaseModel):
    """Count of requirements by status."""

    compliant: int = 0
    due_soon: int = 0
    overdue: int = 0
    waived: int = 0


class ComplianceReportResponse(BaseModel):
    """Compliance dashboard response."""

    total_employees: int
    total_requirements: int
    status_counts: ComplianceStatusCount
    by_certificate_type: dict[str, ComplianceStatusCount]


class MonthlyReportRow(BaseModel):
    """Single row in monthly compliance report."""

    row_type: str = Field(
        ...,
        description="Type of row: 'requirement_due', 'certificate_verified', 'certificate_expiring'",
    )
    employee_id: int
    employee_number: str
    employee_name: str
    employee_email: str
    certificate_type: str

    # Requirement fields (for requirement_due rows)
    requirement_id: Optional[int] = None
    due_date: Optional[date] = None
    requirement_status: Optional[str] = None
    compliance_status: Optional[str] = None

    # Certificate fields (for certificate_verified and certificate_expiring rows)
    satisfied_at: Optional[datetime] = None
    expiration_date: Optional[date] = None
    certificate_lifecycle_status: Optional[str] = None

    class Config:
        from_attributes = True


class MonthlyReportResponse(BaseModel):
    """Monthly compliance report response.

    Per spec 1.2: "monthly reporting becomes a few clicks" - this provides
    a comprehensive monthly export with detailed requirement and certificate data.
    """

    month: str = Field(..., description="Report month in YYYY-MM format")
    generated_at: datetime = Field(..., description="When the report was generated")
    summary: dict[str, int] = Field(
        ...,
        description="Summary counts: requirements_due, certificates_verified, certificates_expiring, total_rows",
    )
    rows: list[MonthlyReportRow] = Field(..., description="Detailed report rows")


# ==================== TEMPLATE SCHEMAS ====================


class TemplateZoneResponse(BaseModel):
    """Template zone definition."""

    field_name: str
    bbox_norm: list[float]
    required: bool


class TemplateResponse(BaseModel):
    """Template definition response."""

    template_id: str
    version: int
    name: str
    description: str
    issuing_authority: Optional[str] = None
    certificate_type_ref: Optional[str] = None
    zones: list[TemplateZoneResponse]
    created_at: str
    updated_at: str


class TemplateListResponse(BaseModel):
    """List of templates response."""

    templates: list[TemplateResponse]
    registry_hash: str


class TemplateZoneCreate(BaseModel):
    """Zone definition in a template create request."""

    field_name: str
    bbox_norm: list[float] = Field(..., min_length=4, max_length=4)
    required: bool = False
    hardcoded_value: Optional[str] = None
    regex_pattern: Optional[str] = Field(None, max_length=500)
    date_format: Optional[str] = None
    allow_multiline: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None


class TemplateCreateRequest(BaseModel):
    """Request to create a new template."""

    template_id: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9_]+$")
    version: int = Field(1, ge=1)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    issuing_authority: Optional[str] = None
    certificate_type_ref: Optional[str] = None
    anchor_keywords: Optional[list[str]] = None
    anchor_regex: Optional[str] = Field(None, max_length=500)
    min_keyword_matches: int = Field(2, ge=1)
    zones: list[TemplateZoneCreate] = Field(..., min_length=1)
    always_review_fields: Optional[list[str]] = None
    created_at: str
    updated_at: str


# ==================== EMPLOYEE SCHEMAS ====================


class EmployeeCreate(BaseModel):
    """Request to create an employee."""

    employee_number: str = Field(..., min_length=1, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    role: str = Field(..., pattern="^(Coordinator|Employee)$")
    manager_id: Optional[int] = None


class EmployeeUpdate(BaseModel):
    """Request to update an employee."""

    employee_number: Optional[str] = Field(None, min_length=1, max_length=50)
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(
        None, pattern="^(Coordinator|Employee)$"
    )
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None


class EmployeeResponse(BaseModel):
    """Employee response."""

    id: int
    employee_number: str
    first_name: str
    last_name: str
    email: str
    role: str
    manager_id: Optional[int] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EmployeeListResponse(BaseModel):
    """Paginated list of employees."""

    employees: list[EmployeeResponse]
    total: int
    skip: int
    limit: int


# ==================== CERTIFICATE TYPE SCHEMAS ====================


class CertificateTypeCreate(BaseModel):
    """Request to create a certificate type."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    validity_period_days: Optional[int] = Field(None, ge=1, le=36500)


class CertificateTypeUpdate(BaseModel):
    """Request to update a certificate type."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1, max_length=2000)
    validity_period_days: Optional[int] = Field(None, ge=1, le=36500)


class CertificateTypeResponse(BaseModel):
    """Certificate type response."""

    id: int
    name: str
    description: str
    validity_period_days: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== VERIFIED RECORD SCHEMAS ====================


class VerifiedRecordResponse(BaseModel):
    """Verified certificate record response."""

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
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== AUDIT LOG SCHEMAS ====================


class AuditLogResponse(BaseModel):
    """Audit log entry response."""

    id: int
    actor_type: str
    employee_id: Optional[int] = None
    actor_name: Optional[str] = None
    action: str
    target_type: str
    target_id: str
    details: Optional[dict] = None
    initiated_by_id: Optional[int] = None
    occurred_at_utc: datetime
    recorded_at_utc: datetime
    actor_role: Optional[str] = None
    correlation_id: Optional[str] = None
    source_service: Optional[str] = None
    outcome: Optional[str] = None
    ip_address: Optional[str] = None

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Paginated audit log list response."""

    total: int
    skip: int
    limit: int
    items: list[AuditLogResponse]


# ==================== NOTIFICATION SCHEMAS ====================


class NotificationResponse(BaseModel):
    """Notification event response."""

    id: int
    notification_type: str
    recipient_employee_id: int
    subject: str
    body: str
    read: bool = Field(..., description="Whether the notification has been read")
    read_at: Optional[datetime] = None
    related_requirement_id: Optional[int] = None
    related_certificate_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Paginated notification list response."""

    notifications: list[NotificationResponse]
    total_unread: int


class MarkReadResponse(BaseModel):
    """Response after marking notifications as read."""

    marked_count: int
    message: str


# ==================== ALERT CONFIGURATION SCHEMAS ====================


class AlertConfigResponse(BaseModel):
    """Alert configuration response."""

    requirement_reminder_days: list[int]
    certificate_reminder_days: list[int]
    daily_overdue_enabled: bool
    global_send_hour: int
    global_send_minute: int
    updated_at: datetime
    updated_by_id: Optional[int] = None

    class Config:
        from_attributes = True


class AlertConfigUpdate(BaseModel):
    """Request to update alert configuration."""

    requirement_reminder_days: list[int] = Field(
        ..., min_length=1, max_length=20,
        description="Days before due date to send reminders (sorted desc, 1-365)",
    )
    certificate_reminder_days: list[int] = Field(
        ..., min_length=1, max_length=20,
        description="Days before expiration to send reminders (sorted desc, 1-365)",
    )
    daily_overdue_enabled: bool = Field(
        ..., description="Whether to send daily overdue notifications",
    )
    global_send_hour: int = Field(
        ..., ge=0, le=23, description="Hour (0-23) for daily notification generation",
    )
    global_send_minute: int = Field(
        ..., ge=0, le=59, description="Minute (0-59) for daily notification generation",
    )
