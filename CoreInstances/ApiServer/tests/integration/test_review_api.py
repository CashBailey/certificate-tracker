"""
Integration tests for the review API (extraction approval/rejection).

Tests the ReviewService with mocked repository to verify:
- Approval happy path
- Approval with corrections
- Idempotent approval
- Optimistic lock conflicts (ConcurrencyError)
- Rejection flow
- Separation of duties enforcement
- State transition validation
"""

import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from src.review import ReviewService
from src.shared.models import (
    AuditActorType,
    CertificateDocument,
    CertificateType,
    Employee,
    ExtractionRun,
    IntakeChannel,
    RequirementAssignment,
    RequirementStatus,
    ReviewState,
    Role,
    VerifiedCertificateRecord,
)
from src.shared.protocols import ConcurrencyError, ReviewConflictError


# ==================== Fixtures ====================


@pytest.fixture
def mock_repository(sample_document):
    """Create a mock repository for review service tests."""
    repo = AsyncMock()
    repo.get_extraction_by_id = AsyncMock(return_value=None)
    repo.get_document_by_id = AsyncMock(return_value=sample_document)
    repo.get_verified_record_by_extraction_id = AsyncMock(return_value=None)
    repo.try_transition_extraction_review_state = AsyncMock(return_value=True)
    repo.insert_verified_record_idempotent = AsyncMock()
    repo.link_requirement_if_unset = AsyncMock(return_value=True)
    repo.find_open_requirement_by_cert_type = AsyncMock(return_value=None)

    async def compatible_requirement(requirement_id):
        return RequirementAssignment(
            id=requirement_id,
            employee_id=sample_document.employee_id,
            certificate_type_id=5,
            due_date=date(2026, 12, 31),
            status=RequirementStatus.NOT_STARTED,
        )

    repo.get_requirement_by_id = AsyncMock(side_effect=compatible_requirement)
    repo.get_certificate_type_by_id = AsyncMock(
        return_value=CertificateType(
            id=5,
            name="CPR/BLS",
            description="CPR and basic life support",
            validity_period_days=365,
        )
    )
    repo.get_certificate_type_by_name = AsyncMock(return_value=None)
    repo.create_audit_log = AsyncMock()
    return repo


@pytest.fixture
def review_service(mock_repository):
    """Create a ReviewService with mock repository."""
    return ReviewService(mock_repository)


@pytest.fixture
def reviewer():
    """Create a reviewer (Coordinator role) for approval tests.

    CRIT-03: Only Coordinators can review extractions.
    """
    return Employee(
        id=100,
        employee_number="R00001",
        first_name="Review",
        last_name="Coordinator",
        email="reviewer@ci.laredo.tx.us",
        role=Role.COORDINATOR,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def second_coordinator():
    """Create a second Coordinator for multi-reviewer tests."""
    return Employee(
        id=101,
        employee_number="C00002",
        first_name="Second",
        last_name="Coordinator",
        email="coordinator2@ci.laredo.tx.us",
        role=Role.COORDINATOR,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def employee():
    """Create a regular employee (uploader)."""
    return Employee(
        id=1,
        employee_number="E12345",
        first_name="John",
        last_name="Doe",
        email="john.doe@ci.laredo.tx.us",
        role=Role.EMPLOYEE,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_document(employee):
    """Create a sample document."""
    return CertificateDocument(
        id=1,
        employee_id=employee.id,
        file_name="certificate.pdf",
        file_type="application/pdf",
        file_size_bytes=1024,
        storage_key="documents/1/abc123/certificate.pdf",
        uploaded_by_id=employee.id,
        acting_as="self",
        intake_channel=IntakeChannel.MANUAL_UPLOAD,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def pending_extraction():
    """Create an extraction in PENDING_REVIEW state."""
    return ExtractionRun(
        id=1,
        document_id=1,
        review_state=ReviewState.PENDING_REVIEW,
        extracted_fields={
            "certificate_holder_name": {
                "value": "John Doe",
                "confidence": {"overall": 0.95},
                "extraction_source": "ocr",
                "needs_review": False,
            },
            "certificate_type": {
                "value": "CPR/BLS",
                "confidence": {"overall": 0.90},
                "extraction_source": "ocr",
                "needs_review": False,
            },
            "issue_date": {
                "value": "2026-01-15",
                "confidence": {"overall": 0.92},
                "extraction_source": "ocr",
                "needs_review": False,
            },
            "expiration_date": {
                "value": "2027-01-15",
                "confidence": {"overall": 0.85},
                "extraction_source": "ocr",
                "needs_review": True,
            },
            "certificate_number": {
                "value": "CERT-12345",
                "confidence": {"overall": 0.88},
                "extraction_source": "ocr",
                "needs_review": False,
            },
        },
        needs_review=True,
        needs_review_reasons=["Low confidence on expiration_date"],
        review_state_version=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def approved_extraction():
    """Create an extraction that has already been approved."""
    return ExtractionRun(
        id=2,
        document_id=2,
        review_state=ReviewState.APPROVED,
        extracted_fields={
            "certificate_holder_name": {"value": "Jane Smith"},
        },
        needs_review=False,
        needs_review_reasons=[],
        review_state_version=1,
        reviewed_by_id=100,
        reviewed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def rejected_extraction():
    """Create an extraction that has been rejected."""
    return ExtractionRun(
        id=3,
        document_id=3,
        review_state=ReviewState.REJECTED,
        extracted_fields={},
        needs_review=False,
        needs_review_reasons=[],
        review_state_version=1,
        reviewed_by_id=100,
        reviewed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def existing_verified_record():
    """Create an existing verified record for idempotency tests."""
    return VerifiedCertificateRecord(
        id=1,
        extraction_id=2,
        document_id=2,
        employee_id=1,
        certificate_holder_name="Jane Smith",
        certificate_type="CPR/BLS",
        certificate_number="CERT-99999",
        issuing_authority="American Red Cross",
        issue_date=date(2025, 1, 15),
        expiration_date=date(2027, 1, 15),
        training_hours=8.0,
        license_class=None,
        endorsements=None,
        created_at=datetime.now(timezone.utc),
    )


# ==================== Approval Happy Path Tests ====================


class TestApprovalHappyPath:
    """Tests for successful extraction approval."""

    @pytest.mark.asyncio
    async def test_approve_creates_verified_record(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Approval should create a VerifiedCertificateRecord."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document
        mock_repository.try_transition_extraction_review_state.return_value = True

        # Create expected saved record
        saved_record = VerifiedCertificateRecord(
            id=1,
            extraction_id=pending_extraction.id,
            document_id=pending_extraction.document_id,
            employee_id=sample_document.employee_id,
            certificate_holder_name="John Doe",
            certificate_type="CPR/BLS",
            expiration_date=date(2027, 1, 15),
            created_at=datetime.now(timezone.utc),
        )
        mock_repository.insert_verified_record_idempotent.return_value = saved_record

        # Execute
        result = await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
        )

        # Assert
        assert result.id == 1
        assert result.extraction_id == pending_extraction.id
        assert result.certificate_holder_name == "John Doe"
        mock_repository.try_transition_extraction_review_state.assert_called_once()
        mock_repository.insert_verified_record_idempotent.assert_called_once()
        mock_repository.create_audit_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_updates_state_to_approved(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Approval should transition state from PENDING_REVIEW to APPROVED."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        saved_record = VerifiedCertificateRecord(
            id=1,
            extraction_id=1,
            document_id=1,
            employee_id=1,
            created_at=datetime.now(timezone.utc),
        )
        mock_repository.insert_verified_record_idempotent.return_value = saved_record

        # Execute
        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
        )

        # Assert state transition was called correctly
        mock_repository.try_transition_extraction_review_state.assert_called_once_with(
            extraction_id=pending_extraction.id,
            expected_state=ReviewState.PENDING_REVIEW,
            expected_version=pending_extraction.review_state_version,
            new_state=ReviewState.APPROVED,
            reviewed_by_id=reviewer.id,
        )

    @pytest.mark.asyncio
    async def test_approve_creates_audit_log(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Approval should create an audit log entry."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        saved_record = VerifiedCertificateRecord(
            id=1,
            extraction_id=1,
            document_id=1,
            employee_id=1,
            created_at=datetime.now(timezone.utc),
        )
        mock_repository.insert_verified_record_idempotent.return_value = saved_record

        # Execute
        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
        )

        # Assert audit log
        mock_repository.create_audit_log.assert_called_once()
        audit_log = mock_repository.create_audit_log.call_args[0][0]
        assert audit_log.actor_type == AuditActorType.EMPLOYEE
        assert audit_log.employee_id == reviewer.id
        assert audit_log.action == "extraction_approved"
        assert audit_log.target_type == "extraction"
        assert audit_log.target_id == str(pending_extraction.id)

    @pytest.mark.asyncio
    async def test_admin_cannot_approve(
        self, review_service, mock_repository, pending_extraction, sample_document
    ):
        """CRIT-03: Admin role must NOT be able to approve (only Coordinators can)."""
        admin = Employee(
            id=101,
            employee_number="A00001",
            first_name="Admin",
            last_name="User",
            email="admin@ci.laredo.tx.us",
            role=Role.ADMIN,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        with pytest.raises(PermissionError, match="Coordinators"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=admin,
            )


# ==================== Approval with Corrections Tests ====================


class TestApprovalWithCorrections:
    """Tests for approval with field corrections."""

    @pytest.mark.asyncio
    async def test_corrections_override_extracted_values(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Corrections should override extracted field values."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        captured_record = None

        async def capture_record(record):
            nonlocal captured_record
            captured_record = record
            record.id = 1
            return record

        mock_repository.insert_verified_record_idempotent.side_effect = capture_record

        # Execute with corrections
        corrections = {
            "certificate_holder_name": "John Q. Doe",  # Corrected name
            "expiration_date": "2027-06-30",  # Corrected date
        }

        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
            corrections=corrections,
        )

        # Assert corrections were applied
        assert captured_record is not None
        assert captured_record.certificate_holder_name == "John Q. Doe"
        assert captured_record.expiration_date == date(2027, 6, 30)

    @pytest.mark.asyncio
    async def test_corrections_add_missing_fields(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Corrections can add fields not in extracted_fields."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        captured_record = None

        async def capture_record(record):
            nonlocal captured_record
            captured_record = record
            record.id = 1
            return record

        mock_repository.insert_verified_record_idempotent.side_effect = capture_record

        # Execute with new field
        corrections = {
            "issuing_authority": "American Red Cross",  # Not in extracted_fields
        }

        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
            corrections=corrections,
        )

        # Assert new field was added
        assert captured_record is not None
        assert captured_record.issuing_authority == "American Red Cross"

    @pytest.mark.asyncio
    async def test_audit_log_records_corrections_made(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Audit log should indicate corrections were made."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        saved_record = VerifiedCertificateRecord(
            id=1,
            extraction_id=1,
            document_id=1,
            employee_id=1,
            created_at=datetime.now(timezone.utc),
        )
        mock_repository.insert_verified_record_idempotent.return_value = saved_record

        corrections = {"certificate_holder_name": "John Q. Doe"}

        # Execute
        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
            corrections=corrections,
        )

        # Assert audit log indicates corrections
        audit_log = mock_repository.create_audit_log.call_args[0][0]
        assert audit_log.details["corrections_made"] is True

    @pytest.mark.asyncio
    async def test_no_corrections_recorded_in_audit_log(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Audit log should indicate no corrections when none provided."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        saved_record = VerifiedCertificateRecord(
            id=1,
            extraction_id=1,
            document_id=1,
            employee_id=1,
            created_at=datetime.now(timezone.utc),
        )
        mock_repository.insert_verified_record_idempotent.return_value = saved_record

        # Execute without corrections
        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
        )

        # Assert audit log indicates no corrections
        audit_log = mock_repository.create_audit_log.call_args[0][0]
        assert audit_log.details["corrections_made"] is False


# ==================== Approval with Requirement Linking Tests ====================


class TestApprovalWithRequirementLinking:
    """Tests for linking requirement when approving."""

    @pytest.mark.asyncio
    async def test_approve_links_requirement(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Approval with requirement_id should link the requirement."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        saved_record = VerifiedCertificateRecord(
            id=99,
            extraction_id=1,
            document_id=1,
            employee_id=1,
            created_at=datetime.now(timezone.utc),
        )
        mock_repository.insert_verified_record_idempotent.return_value = saved_record

        # Execute with requirement_id
        requirement_id = 50

        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
            requirement_id=requirement_id,
        )

        # Assert requirement was linked
        mock_repository.link_requirement_if_unset.assert_called_once_with(
            requirement_id=requirement_id,
            verified_record_id=saved_record.id,
            expected_employee_id=sample_document.employee_id,
            expected_certificate_type_id=5,
        )

    @pytest.mark.asyncio
    async def test_approve_without_requirement_does_not_link(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Approval without requirement_id should not call link_requirement."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document
        # Auto-match must also return None for this test
        mock_repository.find_open_requirement_by_cert_type = AsyncMock(return_value=None)

        saved_record = VerifiedCertificateRecord(
            id=1,
            extraction_id=1,
            document_id=1,
            employee_id=1,
            created_at=datetime.now(timezone.utc),
        )
        mock_repository.insert_verified_record_idempotent.return_value = saved_record

        # Execute without requirement_id
        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
        )

        # Assert requirement linking was not called
        mock_repository.link_requirement_if_unset.assert_not_called()

    @pytest.mark.asyncio
    async def test_audit_log_records_requirement_linked(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Audit log should record which requirement was linked."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        saved_record = VerifiedCertificateRecord(
            id=1,
            extraction_id=1,
            document_id=1,
            employee_id=1,
            created_at=datetime.now(timezone.utc),
        )
        mock_repository.insert_verified_record_idempotent.return_value = saved_record

        requirement_id = 75

        # Execute
        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
            requirement_id=requirement_id,
        )

        # Assert audit log records requirement
        audit_log = mock_repository.create_audit_log.call_args[0][0]
        assert audit_log.details["requirement_linked"] == requirement_id


# ==================== Idempotent Approval Tests ====================


class TestIdempotentApproval:
    """Tests for idempotent approval behavior."""

    @pytest.mark.asyncio
    async def test_second_approval_returns_existing_record(
        self, review_service, mock_repository, reviewer, approved_extraction, existing_verified_record
    ):
        """Second approval on already-approved extraction should return existing record."""
        # Setup - extraction already approved
        mock_repository.get_extraction_by_id.return_value = approved_extraction
        mock_repository.get_verified_record_by_extraction_id.return_value = existing_verified_record

        # Execute
        result = await review_service.reviewer_approve(
            extraction_id=approved_extraction.id,
            reviewer=reviewer,
        )

        # Assert returns existing record without creating new one
        assert result.id == existing_verified_record.id
        assert result.certificate_holder_name == existing_verified_record.certificate_holder_name
        mock_repository.try_transition_extraction_review_state.assert_not_called()
        mock_repository.insert_verified_record_idempotent.assert_not_called()
        mock_repository.create_audit_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_idempotent_approval_different_reviewer(
        self, review_service, mock_repository, second_coordinator, approved_extraction, existing_verified_record
    ):
        """Different Coordinator on already-approved extraction should return existing record."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = approved_extraction
        mock_repository.get_verified_record_by_extraction_id.return_value = existing_verified_record

        # Execute with different Coordinator
        result = await review_service.reviewer_approve(
            extraction_id=approved_extraction.id,
            reviewer=second_coordinator,
        )

        # Assert returns existing record
        assert result.id == existing_verified_record.id
        mock_repository.try_transition_extraction_review_state.assert_not_called()


# ==================== Optimistic Lock Conflict Tests ====================


class TestOptimisticLockConflict:
    """Tests for optimistic locking and concurrency errors."""

    @pytest.mark.asyncio
    async def test_concurrent_approval_raises_concurrency_error(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Concurrent approval should raise ConcurrencyError."""
        # Setup - transition fails (another user modified it)
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document
        mock_repository.try_transition_extraction_review_state.return_value = False

        # Execute and assert
        with pytest.raises(ConcurrencyError) as exc_info:
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
            )

        assert "was modified by another user" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_version_mismatch_causes_conflict(
        self, review_service, mock_repository, reviewer, sample_document
    ):
        """Version mismatch should cause optimistic lock to fail."""
        # Setup - extraction with outdated version
        extraction = ExtractionRun(
            id=1,
            document_id=1,
            review_state=ReviewState.PENDING_REVIEW,
            extracted_fields={
                "certificate_holder_name": {"value": "Test User"},
                "certificate_type": {"value": "CPR/BLS"},
                "issue_date": {"value": "2026-01-15"},
            },
            needs_review=True,
            needs_review_reasons=[],
            review_state_version=5,  # Higher version
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_repository.get_extraction_by_id.return_value = extraction
        mock_repository.get_document_by_id.return_value = sample_document
        mock_repository.try_transition_extraction_review_state.return_value = False

        # Execute and assert
        with pytest.raises(ConcurrencyError):
            await review_service.reviewer_approve(
                extraction_id=extraction.id,
                reviewer=reviewer,
            )

        # Verify the version was passed correctly
        call_kwargs = mock_repository.try_transition_extraction_review_state.call_args[1]
        assert call_kwargs["expected_version"] == 5

    @pytest.mark.asyncio
    async def test_no_verified_record_created_on_conflict(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """No verified record should be created if lock fails."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document
        mock_repository.try_transition_extraction_review_state.return_value = False

        # Execute
        try:
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
            )
        except ConcurrencyError:
            pass

        # Assert no record was created
        mock_repository.insert_verified_record_idempotent.assert_not_called()
        mock_repository.create_audit_log.assert_not_called()


# ==================== Rejection Tests ====================


class TestRejectionFlow:
    """Tests for extraction rejection."""

    @pytest.mark.asyncio
    async def test_reject_transitions_to_rejected(
        self, review_service, mock_repository, reviewer, pending_extraction
    ):
        """Rejection should transition state to REJECTED."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.try_transition_extraction_review_state.return_value = True

        # Execute
        await review_service.reviewer_reject(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
            reason="Document is illegible",
        )

        # Assert state transition
        mock_repository.try_transition_extraction_review_state.assert_called_once_with(
            extraction_id=pending_extraction.id,
            expected_state=ReviewState.PENDING_REVIEW,
            expected_version=pending_extraction.review_state_version,
            new_state=ReviewState.REJECTED,
            reviewed_by_id=reviewer.id,
        )

    @pytest.mark.asyncio
    async def test_reject_creates_audit_log_with_reason(
        self, review_service, mock_repository, reviewer, pending_extraction
    ):
        """Rejection should create audit log with reason."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.try_transition_extraction_review_state.return_value = True

        reason = "Document quality too poor for extraction"

        # Execute
        await review_service.reviewer_reject(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
            reason=reason,
        )

        # Assert audit log
        mock_repository.create_audit_log.assert_called_once()
        audit_log = mock_repository.create_audit_log.call_args[0][0]
        assert audit_log.action == "extraction_rejected"
        assert audit_log.details["reason"] == reason

    @pytest.mark.asyncio
    async def test_reject_does_not_create_verified_record(
        self, review_service, mock_repository, reviewer, pending_extraction
    ):
        """Rejection should not create a VerifiedCertificateRecord."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.try_transition_extraction_review_state.return_value = True

        # Execute
        await review_service.reviewer_reject(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
            reason="Illegible",
        )

        # Assert no verified record
        mock_repository.insert_verified_record_idempotent.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_concurrent_raises_concurrency_error(
        self, review_service, mock_repository, reviewer, pending_extraction
    ):
        """Concurrent rejection should raise ConcurrencyError."""
        # Setup - transition fails
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.try_transition_extraction_review_state.return_value = False

        # Execute and assert
        with pytest.raises(ConcurrencyError) as exc_info:
            await review_service.reviewer_reject(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
                reason="Illegible",
            )

        assert "was modified by another user" in str(exc_info.value)


# ==================== State Transition Validation Tests ====================


class TestStateTransitionValidation:
    """Tests for invalid state transitions."""

    @pytest.mark.asyncio
    async def test_cannot_approve_already_approved(
        self, review_service, mock_repository, reviewer, approved_extraction
    ):
        """Cannot approve extraction that is already approved and has no record."""
        # Setup - approved but somehow no verified record
        mock_repository.get_extraction_by_id.return_value = approved_extraction
        mock_repository.get_verified_record_by_extraction_id.return_value = None

        # Execute and assert - should fail since state is not PENDING_REVIEW
        with pytest.raises(ReviewConflictError) as exc_info:
            await review_service.reviewer_approve(
                extraction_id=approved_extraction.id,
                reviewer=reviewer,
            )

        assert "cannot approve" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cannot_approve_rejected_extraction(
        self, review_service, mock_repository, reviewer, rejected_extraction
    ):
        """Cannot approve extraction that has been rejected."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = rejected_extraction

        # Execute and assert
        with pytest.raises(ReviewConflictError) as exc_info:
            await review_service.reviewer_approve(
                extraction_id=rejected_extraction.id,
                reviewer=reviewer,
            )

        assert "cannot approve" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cannot_reject_already_rejected(
        self, review_service, mock_repository, reviewer, rejected_extraction
    ):
        """Cannot reject extraction that is already rejected."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = rejected_extraction

        # Execute and assert
        with pytest.raises(ReviewConflictError) as exc_info:
            await review_service.reviewer_reject(
                extraction_id=rejected_extraction.id,
                reviewer=reviewer,
                reason="Another rejection reason",
            )

        assert "cannot reject" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cannot_reject_approved_extraction(
        self, review_service, mock_repository, reviewer, approved_extraction
    ):
        """Cannot reject extraction that has been approved."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = approved_extraction

        # Execute and assert
        with pytest.raises(ReviewConflictError) as exc_info:
            await review_service.reviewer_reject(
                extraction_id=approved_extraction.id,
                reviewer=reviewer,
                reason="Should not work",
            )

        assert "cannot reject" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_approve_nonexistent_extraction_raises(
        self, review_service, mock_repository, reviewer
    ):
        """Approving non-existent extraction should raise ReviewConflictError."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = None

        # Execute and assert
        with pytest.raises(ReviewConflictError) as exc_info:
            await review_service.reviewer_approve(
                extraction_id=999,
                reviewer=reviewer,
            )

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reject_nonexistent_extraction_raises(
        self, review_service, mock_repository, reviewer
    ):
        """Rejecting non-existent extraction should raise ReviewConflictError."""
        # Setup
        mock_repository.get_extraction_by_id.return_value = None

        # Execute and assert
        with pytest.raises(ReviewConflictError) as exc_info:
            await review_service.reviewer_reject(
                extraction_id=999,
                reviewer=reviewer,
                reason="Cannot reject non-existent",
            )

        assert "not found" in str(exc_info.value)


# ==================== Authorization Tests ====================


class TestAuthorizationEnforcement:
    """Tests verifying CRIT-03: only Coordinators can review extractions."""

    @pytest.mark.asyncio
    async def test_employee_cannot_approve(
        self, review_service, mock_repository, employee, pending_extraction, sample_document
    ):
        """CRIT-03: Employee role must be denied approval."""
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        with pytest.raises(PermissionError, match="Coordinators"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=employee,
            )

    @pytest.mark.asyncio
    async def test_employee_cannot_reject(
        self, review_service, mock_repository, employee, pending_extraction
    ):
        """CRIT-03: Employee role must be denied rejection."""
        mock_repository.get_extraction_by_id.return_value = pending_extraction

        with pytest.raises(PermissionError, match="Coordinators"):
            await review_service.reviewer_reject(
                extraction_id=pending_extraction.id,
                reviewer=employee,
                reason="Needs correction",
            )

    @pytest.mark.asyncio
    async def test_coordinator_can_approve_via_service(
        self, review_service, mock_repository, pending_extraction, sample_document
    ):
        """Coordinator can approve extractions (CRIT-03 positive path)."""
        coordinator = Employee(
            id=200,
            employee_number="C00001",
            first_name="Coord",
            last_name="User",
            email="coordinator@ci.laredo.tx.us",
            role=Role.COORDINATOR,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        saved_record = VerifiedCertificateRecord(
            id=1,
            extraction_id=1,
            document_id=1,
            employee_id=1,
            created_at=datetime.now(timezone.utc),
        )
        mock_repository.insert_verified_record_idempotent.return_value = saved_record

        result = await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=coordinator,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_coordinator_cannot_approve_own_manual_upload(
        self,
        review_service,
        mock_repository,
        reviewer,
        pending_extraction,
        sample_document,
    ):
        """Manual intake must not bypass separation of duties."""
        sample_document.employee_id = reviewer.id
        mock_repository.get_extraction_by_id.return_value = pending_extraction

        with pytest.raises(PermissionError, match="own certificate"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
            )

        mock_repository.try_transition_extraction_review_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_coordinator_cannot_reject_own_manual_upload(
        self,
        review_service,
        mock_repository,
        reviewer,
        pending_extraction,
        sample_document,
    ):
        """Self-review separation also applies to rejection."""
        sample_document.employee_id = reviewer.id
        mock_repository.get_extraction_by_id.return_value = pending_extraction

        with pytest.raises(PermissionError, match="own certificate"):
            await review_service.reviewer_reject(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
                reason="Certificate data cannot be verified",
            )

        mock_repository.try_transition_extraction_review_state.assert_not_called()


class TestApprovalValidation:
    """Reject invalid verified data and incompatible requirement links."""

    @pytest.mark.asyncio
    async def test_missing_required_field_does_not_claim_review(
        self, review_service, mock_repository, reviewer, pending_extraction
    ):
        pending_extraction.extracted_fields.pop("issue_date")
        mock_repository.get_extraction_by_id.return_value = pending_extraction

        with pytest.raises(ReviewConflictError, match="issue_date"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
            )

        mock_repository.try_transition_extraction_review_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_correction_is_rejected(
        self, review_service, mock_repository, reviewer, pending_extraction
    ):
        mock_repository.get_extraction_by_id.return_value = pending_extraction

        with pytest.raises(ReviewConflictError, match="Unknown correction field"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
                corrections={"internal_override": "true"},
            )

        mock_repository.try_transition_extraction_review_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_oversized_correction_is_rejected(
        self, review_service, mock_repository, reviewer, pending_extraction
    ):
        mock_repository.get_extraction_by_id.return_value = pending_extraction

        with pytest.raises(ReviewConflictError, match="exceeds 200 characters"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
                corrections={"certificate_holder_name": "x" * 201},
            )

        mock_repository.try_transition_extraction_review_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_requirement_for_other_employee_is_rejected(
        self,
        review_service,
        mock_repository,
        reviewer,
        pending_extraction,
    ):
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_requirement_by_id.side_effect = None
        mock_repository.get_requirement_by_id.return_value = RequirementAssignment(
            id=50,
            employee_id=999,
            certificate_type_id=5,
            due_date=date(2026, 12, 31),
            status=RequirementStatus.NOT_STARTED,
        )

        with pytest.raises(ReviewConflictError, match="different employee"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
                requirement_id=50,
            )

        mock_repository.try_transition_extraction_review_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_waived_requirement_is_rejected(
        self,
        review_service,
        mock_repository,
        reviewer,
        pending_extraction,
        sample_document,
    ):
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_requirement_by_id.side_effect = None
        mock_repository.get_requirement_by_id.return_value = RequirementAssignment(
            id=50,
            employee_id=sample_document.employee_id,
            certificate_type_id=5,
            due_date=date(2026, 12, 31),
            status=RequirementStatus.WAIVED,
            waived_at=datetime.now(timezone.utc),
            waived_by_id=reviewer.id,
            waiver_reason="Temporary exception",
        )

        with pytest.raises(ReviewConflictError, match="closed or waived"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
                requirement_id=50,
            )

        mock_repository.try_transition_extraction_review_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_certificate_type_requirement_is_rejected(
        self,
        review_service,
        mock_repository,
        reviewer,
        pending_extraction,
    ):
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_certificate_type_by_id.return_value = CertificateType(
            id=5,
            name="Commercial Driver License",
            description="CDL",
            validity_period_days=365,
        )

        with pytest.raises(ReviewConflictError, match="does not match"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
                requirement_id=50,
            )

        mock_repository.try_transition_extraction_review_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrent_requirement_link_is_not_a_successful_approval(
        self,
        review_service,
        mock_repository,
        reviewer,
        pending_extraction,
    ):
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.link_requirement_if_unset.return_value = False

        with pytest.raises(ConcurrencyError, match="modified concurrently"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
                requirement_id=50,
            )

        mock_repository.create_audit_log.assert_not_called()


# ==================== Field Parsing Tests ====================


class TestFieldParsing:
    """Tests for field value parsing in verified records."""

    @pytest.mark.asyncio
    async def test_date_parsing_valid_format(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Valid date strings should be parsed to date objects."""
        # Setup
        pending_extraction.extracted_fields = {
            "certificate_holder_name": {"value": "Test User"},
            "certificate_type": {"value": "CPR/BLS"},
            "issue_date": {"value": "2025-06-15"},
            "expiration_date": {"value": "2027-06-15"},
        }
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        captured_record = None

        async def capture_record(record):
            nonlocal captured_record
            captured_record = record
            record.id = 1
            return record

        mock_repository.insert_verified_record_idempotent.side_effect = capture_record

        # Execute
        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
        )

        # Assert dates are parsed
        assert captured_record.issue_date == date(2025, 6, 15)
        assert captured_record.expiration_date == date(2027, 6, 15)

    @pytest.mark.asyncio
    async def test_invalid_date_is_rejected(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Invalid dates must not silently become missing verified data."""
        # Setup
        pending_extraction.extracted_fields = {
            "certificate_holder_name": {"value": "Test User"},
            "certificate_type": {"value": "CPR/BLS"},
            "issue_date": {"value": "not-a-date"},
            "expiration_date": {"value": "13/45/9999"},
        }
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        with pytest.raises(ReviewConflictError, match="Issue date"):
            await review_service.reviewer_approve(
                extraction_id=pending_extraction.id,
                reviewer=reviewer,
            )

        mock_repository.try_transition_extraction_review_state.assert_not_called()
        mock_repository.insert_verified_record_idempotent.assert_not_called()

    @pytest.mark.asyncio
    async def test_training_hours_parsing(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Training hours should be parsed to float."""
        # Setup
        pending_extraction.extracted_fields = {
            "certificate_holder_name": {"value": "Test User"},
            "certificate_type": {"value": "CPR/BLS"},
            "issue_date": {"value": "2026-01-15"},
            "training_hours": {"value": "8.5"},
        }
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        captured_record = None

        async def capture_record(record):
            nonlocal captured_record
            captured_record = record
            record.id = 1
            return record

        mock_repository.insert_verified_record_idempotent.side_effect = capture_record

        # Execute
        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
        )

        # Assert training hours parsed
        assert captured_record.training_hours == 8.5

    @pytest.mark.asyncio
    async def test_invalid_training_hours_becomes_none(
        self, review_service, mock_repository, reviewer, pending_extraction, sample_document
    ):
        """Invalid training hours should become None."""
        # Setup
        pending_extraction.extracted_fields = {
            "certificate_holder_name": {"value": "Test User"},
            "certificate_type": {"value": "CPR/BLS"},
            "issue_date": {"value": "2026-01-15"},
            "training_hours": {"value": "eight hours"},
        }
        mock_repository.get_extraction_by_id.return_value = pending_extraction
        mock_repository.get_document_by_id.return_value = sample_document

        captured_record = None

        async def capture_record(record):
            nonlocal captured_record
            captured_record = record
            record.id = 1
            return record

        mock_repository.insert_verified_record_idempotent.side_effect = capture_record

        # Execute
        await review_service.reviewer_approve(
            extraction_id=pending_extraction.id,
            reviewer=reviewer,
        )

        # Assert invalid hours is None
        assert captured_record.training_hours is None


# ==================== Build Verified Fields Tests ====================


class TestBuildVerifiedFields:
    """Tests for _build_verified_fields logic."""

    def test_extracted_fields_used_when_no_corrections(self, review_service):
        """Extracted field values used when no corrections provided."""
        extracted = {
            "certificate_holder_name": {"value": "John Doe"},
            "certificate_type": {"value": "CPR"},
        }

        result = review_service._build_verified_fields(extracted, {})

        assert result["certificate_holder_name"] == "John Doe"
        assert result["certificate_type"] == "CPR"

    def test_corrections_override_extracted(self, review_service):
        """Corrections override extracted values."""
        extracted = {
            "certificate_holder_name": {"value": "John Doe"},
        }
        corrections = {
            "certificate_holder_name": "John Q. Doe",
        }

        result = review_service._build_verified_fields(extracted, corrections)

        assert result["certificate_holder_name"] == "John Q. Doe"

    def test_corrections_add_new_fields(self, review_service):
        """Corrections can add fields not in extracted."""
        extracted = {
            "certificate_holder_name": {"value": "John Doe"},
        }
        corrections = {
            "issuing_authority": "Red Cross",
        }

        result = review_service._build_verified_fields(extracted, corrections)

        assert result["certificate_holder_name"] == "John Doe"
        assert result["issuing_authority"] == "Red Cross"

    def test_handles_non_dict_field_data(self, review_service):
        """Handles extracted fields that aren't dicts."""
        extracted = {
            "certificate_holder_name": "Direct Value",  # Not a dict
        }

        result = review_service._build_verified_fields(extracted, {})

        assert result["certificate_holder_name"] is None  # Can't extract .get("value")

    def test_empty_extracted_fields(self, review_service):
        """Handles empty extracted fields with corrections."""
        extracted = {}
        corrections = {
            "certificate_holder_name": "Manual Entry",
        }

        result = review_service._build_verified_fields(extracted, corrections)

        assert result["certificate_holder_name"] == "Manual Entry"
