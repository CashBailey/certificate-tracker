"""Tests that requirement deadlines stay separate from certificate validity."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.review import ReviewService
from src.shared.models import (
    CertificateDocument,
    CertificateType,
    Employee,
    ExtractionRun,
    IntakeChannel,
    RequirementAssignment,
    RequirementStatus,
    ReviewState,
    Role,
)
from src.shared.protocols import Repository


@pytest.fixture
def reviewer():
    now = datetime.now(timezone.utc)
    return Employee(
        id=100,
        employee_number="R00001",
        first_name="Review",
        last_name="Coordinator",
        email="reviewer@ci.laredo.tx.us",
        role=Role.COORDINATOR,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def pending_extraction():
    return ExtractionRun(
        id=1,
        document_id=1,
        review_state=ReviewState.PENDING_REVIEW,
        extracted_fields={
            "certificate_holder_name": {
                "value": "John Doe",
                "extraction_source": "ocr",
            },
            "certificate_type": {
                "value": "HazCom",
                "extraction_source": "ocr",
            },
            "issue_date": {
                "value": "2026-01-15",
                "extraction_source": "ocr",
            },
        },
        needs_review=False,
        needs_review_reasons=[],
        review_state_version=0,
    )


@pytest.fixture
def document():
    return CertificateDocument(
        id=1,
        employee_id=1,
        file_name="certificate.pdf",
        file_type="application/pdf",
        file_size_bytes=1024,
        storage_key="documents/1/abc123/certificate.pdf",
        uploaded_by_id=1,
        acting_as="self",
        intake_channel=IntakeChannel.MANUAL_UPLOAD,
        target_requirement_id=10,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def requirement():
    return RequirementAssignment(
        id=10,
        employee_id=1,
        certificate_type_id=5,
        due_date=date(2025, 6, 1),
        status=RequirementStatus.NOT_STARTED,
    )


@pytest.fixture
def repository(document, pending_extraction, requirement):
    repo = AsyncMock(spec=Repository)
    repo.get_extraction_by_id.return_value = pending_extraction
    repo.get_document_by_id.return_value = document
    repo.get_verified_record_by_extraction_id.return_value = None
    repo.try_transition_extraction_review_state.return_value = True

    async def save_record(record):
        record.id = 50
        return record

    repo.insert_verified_record_idempotent.side_effect = save_record
    repo.link_requirement_if_unset.return_value = True
    repo.find_open_requirement_by_cert_type.return_value = None
    repo.get_requirement_by_id.return_value = requirement
    repo.get_certificate_type_by_id.return_value = CertificateType(
        id=5,
        name="HazCom",
        description="Hazard Communication",
        validity_period_days=365,
    )
    repo.get_certificate_type_by_name.return_value = None
    return repo


@pytest.mark.asyncio
async def test_approval_derives_expiration_without_changing_requirement_due_date(
    repository, reviewer, requirement
):
    original_due_date = requirement.due_date

    record = await ReviewService(repository).reviewer_approve(1, reviewer)

    assert record.issue_date == date(2026, 1, 15)
    assert record.expiration_date == date(2027, 1, 15)
    assert requirement.due_date == original_due_date
    assert not hasattr(repository, "update_requirement_due_date")
    repository.link_requirement_if_unset.assert_awaited_once_with(
        requirement_id=10,
        verified_record_id=50,
        expected_employee_id=1,
        expected_certificate_type_id=5,
    )


@pytest.mark.asyncio
async def test_explicit_certificate_expiration_is_preserved(
    repository, reviewer, pending_extraction
):
    pending_extraction.extracted_fields["expiration_date"] = {
        "value": "2026-08-31",
        "extraction_source": "ocr",
    }

    record = await ReviewService(repository).reviewer_approve(1, reviewer)

    assert record.expiration_date == date(2026, 8, 31)


@pytest.mark.asyncio
async def test_missing_validity_leaves_certificate_expiration_empty(
    repository, reviewer
):
    repository.get_certificate_type_by_id.return_value.validity_period_days = None

    record = await ReviewService(repository).reviewer_approve(1, reviewer)

    assert record.expiration_date is None


@pytest.mark.asyncio
async def test_unreasonable_legacy_validity_is_not_used(
    repository, reviewer
):
    repository.get_certificate_type_by_id.return_value.validity_period_days = 36_501

    record = await ReviewService(repository).reviewer_approve(1, reviewer)

    assert record.expiration_date is None
