"""
Reviewer approval must persist per-field provenance on the verified record.

Provenance is a domain invariant: the verified record has to record, per field,
whether the value was extracted, confirmed, corrected, or manually entered, plus
the original machine value and the source method (template vs generic).
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from src.review import ReviewService
from src.shared.models import (
    CertificateDocument,
    Employee,
    ExtractionRun,
    IntakeChannel,
    ReviewState,
    Role,
    VerifiedCertificateRecord,
)


def _reviewer() -> Employee:
    return Employee(
        id=100, employee_number="R1", first_name="Rev", last_name="Coord",
        email="rev@ci.laredo.tx.us", role=Role.COORDINATOR, is_active=True,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )


def _document() -> CertificateDocument:
    return CertificateDocument(
        id=1, employee_id=1, file_name="c.pdf", file_type="application/pdf",
        file_size_bytes=10, storage_key="k", uploaded_by_id=1, acting_as="self",
        intake_channel=IntakeChannel.MANUAL_UPLOAD, created_at=datetime.now(timezone.utc),
        target_requirement_id=None,
    )


def _extraction(template_id=None) -> ExtractionRun:
    return ExtractionRun(
        id=1, document_id=1, review_state=ReviewState.PENDING_REVIEW,
        extracted_fields={
            "certificate_holder_name": {"value": "John Doe"},
            "certificate_type": {"value": "HazCom"},
            "issue_date": {"value": "2026-01-15"},
        },
        needs_review=False, needs_review_reasons=[], review_state_version=0,
        template_id=template_id,
    )


def _service_capturing_record():
    repo = AsyncMock()
    repo.get_extraction_by_id = AsyncMock(return_value=_extraction(template_id="tmpl-cpr"))
    repo.get_document_by_id = AsyncMock(return_value=_document())
    repo.get_verified_record_by_extraction_id = AsyncMock(return_value=None)
    repo.try_transition_extraction_review_state = AsyncMock(return_value=True)
    repo.find_open_requirement_by_cert_type = AsyncMock(return_value=None)
    repo.get_certificate_type_by_name = AsyncMock(return_value=None)
    captured = {}

    async def _capture(record: VerifiedCertificateRecord):
        captured["record"] = record
        record.id = 50
        return record

    repo.insert_verified_record_idempotent = AsyncMock(side_effect=_capture)
    repo.create_audit_log = AsyncMock()
    return ReviewService(repo), captured


@pytest.mark.asyncio
async def test_provenance_records_extracted_and_corrected_fields():
    service, captured = _service_capturing_record()

    await service.reviewer_approve(
        extraction_id=1,
        reviewer=_reviewer(),
        corrections={"certificate_type": "Hazard Communication"},
    )

    prov = captured["record"].field_provenance
    assert prov is not None

    # Uncorrected field: extracted, from a template.
    assert prov["certificate_holder_name"]["entry_mode"] == "extracted"
    assert prov["certificate_holder_name"]["original_value"] == "John Doe"
    assert prov["certificate_holder_name"]["source_method"] == "template"

    # Corrected field keeps the original machine value.
    assert prov["certificate_type"]["entry_mode"] == "corrected"
    assert prov["certificate_type"]["original_value"] == "HazCom"


@pytest.mark.asyncio
async def test_provenance_marks_manual_and_confirmed_and_generic_source():
    service, captured = _service_capturing_record()
    service.repository.get_extraction_by_id = AsyncMock(return_value=_extraction(template_id=None))

    await service.reviewer_approve(
        extraction_id=1,
        reviewer=_reviewer(),
        corrections={
            "certificate_holder_name": "John Doe",   # unchanged -> confirmed
            "license_class": "CDL-A",                 # not extracted -> manual
        },
    )

    prov = captured["record"].field_provenance
    assert prov["certificate_holder_name"]["entry_mode"] == "confirmed"
    assert prov["certificate_holder_name"]["source_method"] == "generic"
    assert prov["license_class"]["entry_mode"] == "manual"
    assert prov["license_class"]["original_value"] is None
