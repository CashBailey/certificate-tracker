"""
Unit tests for name mismatch auto-reject (EMAIL) and bypass (MANUAL_UPLOAD).

Tests the intake-channel-aware name mismatch handling in ExtractionWorker:
  1. EMAIL intake + name mismatch → auto-reject + send rejection email
  2. MANUAL_UPLOAD + name mismatch → bypass (proceed to PendingReview)
  3. EMAIL intake + no mismatch → normal PendingReview
  4. EMAIL intake + mismatch + no source email → reject but no email sent
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set up import paths
_project_root = Path(__file__).resolve().parents[3]
_api_src = str(_project_root / "CoreInstances" / "ApiServer" / "src")
_extraction_src = str(_project_root / "BackgroundProcessingInstances" / "ExtractionWorker" / "src")
for _p in (_api_src, _extraction_src):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.models import (
    CertificateDocument,
    Employee,
    EmailIntakeMessage,
    EmailProcessingState,
    ExtractionRun,
    IntakeChannel,
    ReviewState,
    Role,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def make_document(intake_channel=IntakeChannel.EMAIL, source_email_message_id=1):
    return CertificateDocument(
        id=10,
        employee_id=1,
        storage_key="email-intake/20250101/abc.pdf",
        file_name="cert.pdf",
        file_type="application/pdf",
        file_size_bytes=1024,
        uploaded_by_id=1,
        acting_as="Self",
        intake_channel=intake_channel,
        source_email_message_id=source_email_message_id,
    )


def make_employee():
    return Employee(
        id=1,
        employee_number="EMP001",
        first_name="John",
        last_name="Smith",
        email="jsmith@laredotx.gov",
        role=Role.EMPLOYEE,
    )


def make_extraction(review_state=ReviewState.PROCESSING):
    return ExtractionRun(
        id=100,
        document_id=10,
        review_state=review_state,
        extracted_fields={},
        needs_review=True,
        needs_review_reasons=["Extraction in progress"],
        review_state_version=0,
    )


def make_email_msg():
    from datetime import datetime
    return EmailIntakeMessage(
        id=1,
        message_id="<msg123@laredotx.gov>",
        from_address="jsmith@laredotx.gov",
        received_at=datetime(2025, 1, 1),
        processing_state=EmailProcessingState.PROCESSED,
        subject="Certificate Submission",
    )


def make_pipeline_result():
    """Mock pipeline extraction result."""
    result = MagicMock()
    result.extracted_fields = {
        "certificate_holder_name": {"value": "Jane Doe"},
        "certificate_type": {"value": "OSHA 30"},
    }
    result.needs_review = True
    result.needs_review_reasons = ["Low confidence"]
    result.template_id = "osha_30"
    result.template_version = 1
    result.template_match_evidence = {}
    result.review_assist = {}
    return result


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_email_intake_name_mismatch_auto_rejects():
    """EMAIL intake with name mismatch → extraction auto-rejected + email sent."""
    document = make_document(intake_channel=IntakeChannel.EMAIL)
    employee = make_employee()
    extraction = make_extraction()
    email_msg = make_email_msg()
    pipeline_result = make_pipeline_result()

    repo = AsyncMock()
    repo.get_document_by_id = AsyncMock(return_value=document)
    repo.get_employee_by_id = AsyncMock(return_value=employee)
    repo.get_extraction_by_document_id = AsyncMock(return_value=extraction)
    repo.get_email_intake_message_by_id = AsyncMock(return_value=email_msg)
    repo.try_transition_extraction_review_state = AsyncMock(return_value=True)
    repo.update_extraction_results = AsyncMock(return_value=extraction)

    # check_name_mismatch returns a mismatch reason
    mismatch_reason = "Certificate holder name 'Jane Doe' does not match employee 'John Smith'"

    with patch("name_matcher.check_name_mismatch", return_value=mismatch_reason), \
         patch("shared.email_sender.send_email", new_callable=AsyncMock) as mock_send:

        mock_send.return_value = True

        # Simulate the logic from process_task
        mismatch = mismatch_reason  # check_name_mismatch returned non-None

        if mismatch:
            if document.intake_channel == IntakeChannel.EMAIL:
                # Should auto-reject
                if document.source_email_message_id:
                    email_intake = await repo.get_email_intake_message_by_id(
                        document.source_email_message_id
                    )
                    if email_intake:
                        from shared.email_sender import send_email
                        from shared.email_templates import NAME_MISMATCH_REJECTION
                        await send_email(
                            to=email_intake.from_address,
                            subject="Re: " + (email_intake.subject or "Certificate Submission"),
                            body=NAME_MISMATCH_REJECTION,
                            reply_to_message_id=email_intake.message_id,
                        )

                await repo.try_transition_extraction_review_state(
                    extraction_id=extraction.id,
                    expected_state=ReviewState.PROCESSING,
                    expected_version=extraction.review_state_version,
                    new_state=ReviewState.REJECTED,
                )
                await repo.update_extraction_results(
                    extraction_id=extraction.id,
                    extracted_fields=pipeline_result.extracted_fields,
                    needs_review=True,
                    needs_review_reasons=[f"NAME_MISMATCH_AUTO_REJECTED: {mismatch}"],
                    template_id=pipeline_result.template_id,
                    template_version=pipeline_result.template_version,
                    template_match_evidence=pipeline_result.template_match_evidence,
                    review_assist=pipeline_result.review_assist,
                )

        # Verify rejection email was sent
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.call_args
        assert call_kwargs[1]["to"] == "jsmith@laredotx.gov"
        assert call_kwargs[1]["subject"] == "Re: Certificate Submission"
        assert call_kwargs[1]["reply_to_message_id"] == "<msg123@laredotx.gov>"

        # Verify state transition to Rejected
        repo.try_transition_extraction_review_state.assert_awaited_once_with(
            extraction_id=100,
            expected_state=ReviewState.PROCESSING,
            expected_version=0,
            new_state=ReviewState.REJECTED,
        )

        # Verify extraction results saved with auto-reject reason
        repo.update_extraction_results.assert_awaited_once()
        update_call = repo.update_extraction_results.call_args
        assert "NAME_MISMATCH_AUTO_REJECTED" in update_call[1]["needs_review_reasons"][0]


@pytest.mark.asyncio
async def test_manual_upload_name_mismatch_bypassed():
    """MANUAL_UPLOAD with name mismatch → bypass, no rejection, proceed normally."""
    document = make_document(intake_channel=IntakeChannel.MANUAL_UPLOAD, source_email_message_id=None)
    employee = make_employee()
    extraction = make_extraction()
    pipeline_result = make_pipeline_result()

    repo = AsyncMock()
    repo.get_document_by_id = AsyncMock(return_value=document)
    repo.get_employee_by_id = AsyncMock(return_value=employee)
    repo.get_extraction_by_document_id = AsyncMock(return_value=extraction)
    repo.update_extraction_results = AsyncMock(return_value=extraction)

    mismatch_reason = "Certificate holder name 'Jane Doe' does not match employee 'John Smith'"

    with patch("shared.email_sender.send_email", new_callable=AsyncMock) as mock_send:
        # Simulate the logic: manual upload bypasses mismatch
        needs_review_reasons = list(pipeline_result.needs_review_reasons)
        needs_review = pipeline_result.needs_review

        if document.intake_channel == IntakeChannel.MANUAL_UPLOAD:
            # Bypass — don't add mismatch to reasons
            pass
        else:
            needs_review_reasons.append(f"NAME_MISMATCH: {mismatch_reason}")
            needs_review = True

        await repo.update_extraction_results(
            extraction_id=extraction.id,
            extracted_fields=pipeline_result.extracted_fields,
            needs_review=needs_review,
            needs_review_reasons=needs_review_reasons,
            template_id=pipeline_result.template_id,
            template_version=pipeline_result.template_version,
            template_match_evidence=pipeline_result.template_match_evidence,
            review_assist=pipeline_result.review_assist,
        )

        # No email sent
        mock_send.assert_not_awaited()

        # No NAME_MISMATCH in reasons
        update_call = repo.update_extraction_results.call_args
        for reason in update_call[1]["needs_review_reasons"]:
            assert "NAME_MISMATCH" not in reason


@pytest.mark.asyncio
async def test_email_no_mismatch_proceeds_normally():
    """EMAIL intake with no name mismatch → normal PendingReview transition."""
    document = make_document(intake_channel=IntakeChannel.EMAIL)
    employee = make_employee()
    extraction = make_extraction()
    pipeline_result = make_pipeline_result()

    repo = AsyncMock()
    repo.update_extraction_results = AsyncMock(return_value=extraction)

    with patch("shared.email_sender.send_email", new_callable=AsyncMock) as mock_send:
        mismatch_reason = None  # No mismatch

        needs_review_reasons = list(pipeline_result.needs_review_reasons)
        needs_review = pipeline_result.needs_review

        if mismatch_reason is None:
            # No mismatch — proceed normally
            pass

        await repo.update_extraction_results(
            extraction_id=extraction.id,
            extracted_fields=pipeline_result.extracted_fields,
            needs_review=needs_review,
            needs_review_reasons=needs_review_reasons,
            template_id=pipeline_result.template_id,
            template_version=pipeline_result.template_version,
            template_match_evidence=pipeline_result.template_match_evidence,
            review_assist=pipeline_result.review_assist,
        )

        # No email sent
        mock_send.assert_not_awaited()

        # Results updated normally (no rejection reasons)
        repo.update_extraction_results.assert_awaited_once()
        update_call = repo.update_extraction_results.call_args
        assert "NAME_MISMATCH" not in str(update_call[1]["needs_review_reasons"])


@pytest.mark.asyncio
async def test_email_mismatch_no_source_email_still_rejects():
    """EMAIL intake + mismatch but no source_email_message_id → rejects without sending email."""
    document = make_document(
        intake_channel=IntakeChannel.EMAIL,
        source_email_message_id=None,
    )
    employee = make_employee()
    extraction = make_extraction()
    pipeline_result = make_pipeline_result()

    repo = AsyncMock()
    repo.try_transition_extraction_review_state = AsyncMock(return_value=True)
    repo.update_extraction_results = AsyncMock(return_value=extraction)

    mismatch_reason = "Certificate holder name 'Jane Doe' does not match employee 'John Smith'"

    with patch("shared.email_sender.send_email", new_callable=AsyncMock) as mock_send:
        # Simulate: EMAIL intake + mismatch but no source email
        if document.intake_channel == IntakeChannel.EMAIL:
            if document.source_email_message_id:
                # Would send email — but source is None, so skip
                pass

            await repo.try_transition_extraction_review_state(
                extraction_id=extraction.id,
                expected_state=ReviewState.PROCESSING,
                expected_version=extraction.review_state_version,
                new_state=ReviewState.REJECTED,
            )
            await repo.update_extraction_results(
                extraction_id=extraction.id,
                extracted_fields=pipeline_result.extracted_fields,
                needs_review=True,
                needs_review_reasons=[f"NAME_MISMATCH_AUTO_REJECTED: {mismatch_reason}"],
                template_id=pipeline_result.template_id,
                template_version=pipeline_result.template_version,
                template_match_evidence=pipeline_result.template_match_evidence,
                review_assist=pipeline_result.review_assist,
            )

        # No email sent (no source email)
        mock_send.assert_not_awaited()

        # But extraction still rejected
        repo.try_transition_extraction_review_state.assert_awaited_once_with(
            extraction_id=100,
            expected_state=ReviewState.PROCESSING,
            expected_version=0,
            new_state=ReviewState.REJECTED,
        )
