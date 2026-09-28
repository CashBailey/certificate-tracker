"""
Review service for extraction approval/rejection workflow.

Handles the transactional review process with optimistic locking,
verified record creation, and audit logging.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .authorizer import authorizer
from .shared.audit import audit_employee_action
from .shared.models import (
    Employee,
    RequirementStatus,
    ReviewState,
    VerifiedCertificateRecord,
)
from .shared.protocols import (
    ConcurrencyError,
    Repository,
    ReviewConflictError,
)


class ReviewService:
    """Service for handling extraction reviews."""

    _REQUIRED_FIELDS = (
        "certificate_holder_name",
        "certificate_type",
        "issue_date",
    )
    _FIELD_MAX_LENGTHS = {
        "certificate_holder_name": 200,
        "certificate_type": 200,
        "certificate_number": 100,
        "issuing_authority": 200,
        "issue_date": 10,
        "expiration_date": 10,
        "training_hours": 32,
        "license_class": 50,
        "endorsements": 2000,
    }

    def __init__(self, repository: Repository):
        """
        Initialize review service.

        Args:
            repository: Repository instance
        """
        self.repository = repository

    @staticmethod
    def _get_positive_validity_days(cert_type: object | None) -> Optional[int]:
        """Return a usable validity period only for real positive integer values."""
        if cert_type is None:
            return None
        validity_days = getattr(cert_type, "validity_period_days", None)
        if isinstance(validity_days, int) and 0 < validity_days <= 36_500:
            return validity_days
        return None

    async def reviewer_approve(
        self,
        extraction_id: int,
        reviewer: Employee,
        corrections: Optional[dict[str, str]] = None,
        requirement_id: Optional[int] = None,
    ) -> VerifiedCertificateRecord:
        """
        Approve an extraction and create verified record.

        Transactional flow:
        1. Auth check
        2. Idempotency check (already approved?)
        3. Optimistic lock transition
        4. Build verified fields
        5. Insert verified record
        6. Link requirement (if provided)
        7. Audit log

        Args:
            extraction_id: ID of extraction to approve
            reviewer: Employee performing the review
            corrections: Optional dict of field corrections {field_name: corrected_value}
            requirement_id: Optional requirement to satisfy

        Returns:
            Created VerifiedCertificateRecord

        Raises:
            AuthorizationError: If reviewer lacks permission
            ReviewConflictError: If extraction not in reviewable state
            ConcurrencyError: If optimistic lock fails
        """
        # 1. Get extraction (needed to fetch document for self-review check)
        extraction = await self.repository.get_extraction_by_id(extraction_id)
        if not extraction:
            raise ReviewConflictError(f"Extraction {extraction_id} not found")

        # 2. Get document to resolve the authoritative certificate holder.
        document = await self.repository.get_document_by_id(extraction.document_id)
        if not document:
            raise ReviewConflictError(
                f"Document for extraction {extraction_id} not found"
            )

        # Separation of duties follows record ownership, not intake channel. A
        # Coordinator may upload manually, but still cannot approve a document
        # whose certificate holder is that same Coordinator.
        self._check_review_permission(reviewer, document.employee_id)

        # 4. Idempotency check - if already approved, return existing record
        if extraction.review_state == ReviewState.APPROVED:
            existing = await self.repository.get_verified_record_by_extraction_id(
                extraction_id
            )
            if existing:
                return existing

        # 5. Check state is reviewable
        if extraction.review_state != ReviewState.PENDING_REVIEW:
            raise ReviewConflictError(
                f"Extraction {extraction_id} is {extraction.review_state.value}, cannot approve"
            )

        # 6. Validate bounded, known corrections before they can enter the
        # verified record or append-only provenance JSON.
        corrections = corrections or {}
        self._validate_corrections(corrections)

        # 7. Build verified fields + per-field provenance (entry mode, original
        # machine value, source method). Provenance is a domain invariant: the
        # verified record must record whether each field was extracted,
        # confirmed, corrected, or manually entered by the reviewer.
        verified_fields = self._build_verified_fields(
            extraction.extracted_fields,
            corrections,
        )
        field_provenance = self._build_field_provenance(
            extraction.extracted_fields,
            corrections,
            template_id=extraction.template_id,
        )
        self._validate_required_fields(verified_fields)

        issue_date = self._parse_date(verified_fields.get("issue_date"))
        if issue_date is None:
            raise ReviewConflictError("Issue date must use YYYY-MM-DD format")
        cert_type_name = str(verified_fields["certificate_type"]).strip()

        # 8. Resolve and authorize the target requirement relationship before
        # mutating review state. Foreign keys prove existence, not employee,
        # certificate-type, waiver, or open-state compatibility.
        actual_requirement_id = requirement_id
        if not actual_requirement_id and document.target_requirement_id:
            actual_requirement_id = document.target_requirement_id
        if not actual_requirement_id:
            actual_requirement_id = (
                await self.repository.find_open_requirement_by_cert_type(
                    employee_id=document.employee_id,
                    certificate_type_name=cert_type_name,
                )
            )

        cert_type = None
        target_requirement = None
        if actual_requirement_id:
            target_requirement = await self.repository.get_requirement_by_id(
                actual_requirement_id
            )
            if not target_requirement:
                raise ReviewConflictError(
                    f"Requirement {actual_requirement_id} not found"
                )
            if target_requirement.employee_id != document.employee_id:
                raise ReviewConflictError(
                    "Requirement belongs to a different employee"
                )
            target_status = getattr(
                target_requirement.status, "value", target_requirement.status
            )
            if (
                target_requirement.satisfied_by_id is not None
                or target_requirement.waived_at is not None
                or target_status
                in (RequirementStatus.SATISFIED.value, RequirementStatus.WAIVED.value)
            ):
                raise ReviewConflictError("Requirement is already closed or waived")

            cert_type = await self.repository.get_certificate_type_by_id(
                target_requirement.certificate_type_id
            )
            if not cert_type:
                raise ReviewConflictError("Requirement certificate type not found")
            if self._normalize_name(cert_type.name) != self._normalize_name(
                cert_type_name
            ):
                raise ReviewConflictError(
                    "Certificate type does not match the selected requirement"
                )
        else:
            cert_type = await self.repository.get_certificate_type_by_name(
                cert_type_name
            )

        # 8a. Compute expiration_date: prefer the extracted value if present;
        # otherwise derive from cert_type.validity_period_days.
        expiration_raw = verified_fields.get("expiration_date")
        expiration_date = self._parse_date(expiration_raw)
        if expiration_raw and expiration_date is None:
            raise ReviewConflictError("Expiration date must use YYYY-MM-DD format")
        validity_days = self._get_positive_validity_days(cert_type)
        if expiration_date is None and validity_days:
            expiration_date = issue_date + timedelta(
                days=validity_days
            )
        if expiration_date is not None and expiration_date < issue_date:
            raise ReviewConflictError("Expiration date cannot precede issue date")

        # 9. Claim the review transition only after all validation succeeds.
        success = await self.repository.try_transition_extraction_review_state(
            extraction_id=extraction_id,
            expected_state=ReviewState.PENDING_REVIEW,
            expected_version=extraction.review_state_version,
            new_state=ReviewState.APPROVED,
            reviewed_by_id=reviewer.id,
        )

        if not success:
            raise ConcurrencyError(
                f"Extraction {extraction_id} was modified by another user"
            )

        # 10. Create verified record (with reviewer attribution + expiration).
        record = VerifiedCertificateRecord(
            id=0,  # Will be set by DB
            extraction_id=extraction_id,
            document_id=extraction.document_id,
            employee_id=document.employee_id,
            certificate_holder_name=verified_fields.get("certificate_holder_name"),
            certificate_type=verified_fields.get("certificate_type"),
            certificate_number=verified_fields.get("certificate_number"),
            issuing_authority=verified_fields.get("issuing_authority"),
            issue_date=issue_date,
            expiration_date=expiration_date,
            training_hours=self._parse_float(verified_fields.get("training_hours")),
            license_class=verified_fields.get("license_class"),
            endorsements=verified_fields.get("endorsements"),
            reviewed_by_id=reviewer.id,
            reviewed_at=datetime.now(timezone.utc),
            field_provenance=field_provenance,
        )

        saved_record = await self.repository.insert_verified_record_idempotent(record)

        # 11. Link requirement atomically. Requirement due_date is a policy
        # deadline and must never be replaced with certificate expiration.
        linked_requirement_id = None
        if actual_requirement_id:
            linked = await self.repository.link_requirement_if_unset(
                requirement_id=actual_requirement_id,
                verified_record_id=saved_record.id,
                expected_employee_id=document.employee_id,
                expected_certificate_type_id=target_requirement.certificate_type_id,
            )
            if not linked:
                raise ConcurrencyError(
                    f"Requirement {actual_requirement_id} was modified concurrently"
                )
            linked_requirement_id = actual_requirement_id

        # 12. Audit only the relationship actually persisted.
        await audit_employee_action(
            repository=self.repository,
            actor=reviewer,
            action="extraction_approved",
            target_type="extraction",
            target_id=str(extraction_id),
            details={
                "corrections_made": bool(corrections),
                "requirement_linked": linked_requirement_id,
            },
        )

        return saved_record

    async def reviewer_reject(
        self,
        extraction_id: int,
        reviewer: Employee,
        reason: str,
    ) -> None:
        """
        Reject an extraction.

        Args:
            extraction_id: ID of extraction to reject
            reviewer: Employee performing the review
            reason: Reason for rejection

        Raises:
            AuthorizationError: If reviewer lacks permission
            ReviewConflictError: If extraction not in reviewable state
            ConcurrencyError: If optimistic lock fails
        """
        # 1. Get extraction (needed to resolve certificate holder for self-review check)
        extraction = await self.repository.get_extraction_by_id(extraction_id)
        if not extraction:
            raise ReviewConflictError(f"Extraction {extraction_id} not found")

        # 2. Get document to resolve cert holder for separation-of-duties check
        document = await self.repository.get_document_by_id(extraction.document_id)
        if not document:
            raise ReviewConflictError(
                f"Document for extraction {extraction_id} not found"
            )

        # 3. Auth check — enforces Coordinator role + separation-of-duties
        self._check_review_permission(reviewer, document.employee_id)

        # 4. Check state is reviewable
        if extraction.review_state != ReviewState.PENDING_REVIEW:
            raise ReviewConflictError(
                f"Extraction {extraction_id} is {extraction.review_state.value}, cannot reject"
            )

        # 5. Optimistic lock transition
        success = await self.repository.try_transition_extraction_review_state(
            extraction_id=extraction_id,
            expected_state=ReviewState.PENDING_REVIEW,
            expected_version=extraction.review_state_version,
            new_state=ReviewState.REJECTED,
            reviewed_by_id=reviewer.id,
        )

        if not success:
            raise ConcurrencyError(
                f"Extraction {extraction_id} was modified by another user"
            )

        # 6. Audit log
        await audit_employee_action(
            repository=self.repository,
            actor=reviewer,
            action="extraction_rejected",
            target_type="extraction",
            target_id=str(extraction_id),
            details={
                "reason": reason,
            },
        )

    def _check_review_permission(
        self,
        employee: Employee,
        employee_id: Optional[int] = None,
    ) -> None:
        """
        Check if employee has permission to review an extraction.

        Enforces two rules:
        1. Reviewer must have the Coordinator role.
        2. Reviewer must not be the certificate holder
           (separation-of-duties).

        Raises:
            PermissionError: If the employee is not authorized.
        """
        authorizer.require_can_review_extraction(employee, employee_id)

    def _build_verified_fields(
        self,
        extracted_fields: dict,
        corrections: dict[str, str],
    ) -> dict[str, Optional[str]]:
        """
        Build verified field values from extracted fields and corrections.

        Args:
            extracted_fields: Original extracted fields
            corrections: User corrections

        Returns:
            Dict of field_name -> final verified value
        """
        result: dict[str, Optional[str]] = {}

        for field_name, field_data in extracted_fields.items():
            original_value = (
                field_data.get("value") if isinstance(field_data, dict) else None
            )

            if field_name in corrections:
                # User provided correction
                result[field_name] = corrections[field_name]
            else:
                # Use original extracted value
                result[field_name] = original_value

        # Include any fields only in corrections (manual entry)
        for field_name, value in corrections.items():
            if field_name not in result:
                result[field_name] = value

        return result

    def _validate_corrections(self, corrections: dict[str, str]) -> None:
        """Reject unknown or oversized values before durable provenance writes."""
        if len(corrections) > len(self._FIELD_MAX_LENGTHS):
            raise ReviewConflictError("Too many corrected fields")
        for field_name, value in corrections.items():
            max_length = self._FIELD_MAX_LENGTHS.get(field_name)
            if max_length is None:
                raise ReviewConflictError(f"Unknown correction field: {field_name}")
            if len(value) > max_length:
                raise ReviewConflictError(
                    f"Correction for {field_name} exceeds {max_length} characters"
                )

    def _validate_required_fields(
        self, verified_fields: dict[str, Optional[str]]
    ) -> None:
        missing = [
            name
            for name in self._REQUIRED_FIELDS
            if not str(verified_fields.get(name) or "").strip()
        ]
        if missing:
            raise ReviewConflictError(
                f"Required review fields are missing: {', '.join(missing)}"
            )

    @staticmethod
    def _normalize_name(value: str) -> str:
        return " ".join(value.casefold().split())

    def _build_field_provenance(
        self,
        extracted_fields: dict,
        corrections: dict[str, str],
        template_id: Optional[str],
    ) -> dict[str, dict]:
        """
        Record per-field provenance for the verified record.

        For each field, capture:
          - entry_mode: extracted | confirmed | corrected | manual
          - original_value: the machine-extracted value (None for manual entry)
          - source_method: 'template' if template-matched, else 'generic'

        This is what preserves the "who set this field, and how" audit trail
        that the field_provenance column exists for.
        """
        provenance: dict[str, dict] = {}

        def _original(field_name: str):
            field_data = extracted_fields.get(field_name)
            return field_data.get("value") if isinstance(field_data, dict) else None

        for field_name in extracted_fields:
            field_data = extracted_fields.get(field_name)
            original_value = _original(field_name)
            if field_name in corrections:
                corrected = corrections[field_name]
                entry_mode = "corrected" if corrected != original_value else "confirmed"
            else:
                entry_mode = "extracted"
            provenance[field_name] = {
                "entry_mode": entry_mode,
                "original_value": original_value,
                "source_method": (
                    field_data.get("extraction_source")
                    if isinstance(field_data, dict)
                    and field_data.get("extraction_source")
                    else ("template" if template_id else "generic")
                ),
            }

        # Fields present only in corrections were typed in by the reviewer.
        for field_name in corrections:
            if field_name not in provenance:
                provenance[field_name] = {
                    "entry_mode": "manual",
                    "original_value": None,
                    "source_method": "manual",
                }

        return provenance

    def _parse_date(self, value: Optional[str]) -> Optional[date]:
        """Parse date string to date object."""
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        """Parse string to float."""
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
