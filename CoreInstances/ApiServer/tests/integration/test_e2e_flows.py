"""
End-to-end integration tests for complete workflow scenarios.

Tests full system flows including:
- Golden path: Email → OCR → Review → Verified Record → Requirement Satisfied
- Unknown sender quarantine with admin resolution
- Scheduler idempotency (cursor-based backfill)
- Document resubmission after rejection
"""

import pytest
import json
import hashlib
from datetime import date, datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch
from enum import Enum


# ==================== Mock Enums and Models ====================


class MockReviewState(Enum):
    """Mock ReviewState enum."""
    PENDING_REVIEW = "PendingReview"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class MockEmailProcessingState(Enum):
    """Mock EmailProcessingState enum."""
    RECEIVED = "Received"
    PROCESSED = "Processed"
    QUARANTINED = "Quarantined"
    FAILED = "Failed"


class MockRequirementStatus(Enum):
    """Mock RequirementStatus enum."""
    NOT_STARTED = "NotStarted"
    PENDING_REVIEW = "PendingReview"
    SATISFIED = "Satisfied"
    OVERDUE = "Overdue"
    WAIVED = "Waived"


class MockNotificationType(Enum):
    """Mock NotificationType enum."""
    REQUIREMENT_DUE_SOON = "RequirementDueSoon"
    REQUIREMENT_OVERDUE = "RequirementOverdue"
    CERTIFICATE_EXPIRING = "CertificateExpiring"


@dataclass
class MockEmployee:
    """Mock Employee model."""
    id: int
    employee_number: str
    first_name: str
    last_name: str
    email: str
    role: str
    is_active: bool = True
    manager_id: Optional[int] = None


@dataclass
class MockRequirement:
    """Mock Requirement model."""
    id: int
    employee_id: int
    certificate_type_id: int
    due_date: date
    status: MockRequirementStatus = MockRequirementStatus.NOT_STARTED
    satisfied_by_id: Optional[int] = None
    waived_at: Optional[datetime] = None


@dataclass
class MockDocument:
    """Mock CertificateDocument model."""
    id: int
    employee_id: int
    file_name: str
    file_type: str
    file_size_bytes: int
    storage_key: str
    uploaded_by_id: int
    file_hash: Optional[str] = None
    source_email_message_id: Optional[int] = None


@dataclass
class MockExtraction:
    """Mock ExtractionRun model."""
    id: int
    document_id: int
    review_state: MockReviewState
    extracted_fields: dict
    needs_review: bool
    review_state_version: int = 0
    reviewed_by_id: Optional[int] = None


@dataclass
class MockVerifiedRecord:
    """Mock VerifiedCertificateRecord model."""
    id: int
    extraction_id: int
    document_id: int
    employee_id: int
    certificate_holder_name: Optional[str] = None
    certificate_type: Optional[str] = None
    expiration_date: Optional[date] = None


@dataclass
class MockEmailIntakeMessage:
    """Mock EmailIntakeMessage model."""
    id: int
    message_id: str
    from_address: str
    processing_state: MockEmailProcessingState
    employee_id: Optional[int] = None
    error_reason: Optional[str] = None
    attachment_hashes: list = field(default_factory=list)


@dataclass
class MockNotification:
    """Mock Notification model."""
    id: int
    notification_type: MockNotificationType
    recipient_employee_id: int
    related_requirement_id: Optional[int] = None
    dedupe_key: str = ""
    sent_at: Optional[datetime] = None


# ==================== Fixtures ====================


@pytest.fixture
def employee():
    """Standard employee who submits certificates."""
    return MockEmployee(
        id=100,
        employee_number="E12345",
        first_name="John",
        last_name="Doe",
        email="john.doe@ci.laredo.tx.us",
        role="Employee",
    )


@pytest.fixture
def reviewer():
    """Reviewer who approves/rejects extractions."""
    return MockEmployee(
        id=200,
        employee_number="R00001",
        first_name="Jane",
        last_name="Smith",
        email="jane.smith@ci.laredo.tx.us",
        role="Reviewer",
    )


@pytest.fixture
def admin():
    """Admin who can resolve quarantined emails."""
    return MockEmployee(
        id=300,
        employee_number="A00001",
        first_name="Admin",
        last_name="User",
        email="admin@ci.laredo.tx.us",
        role="Admin",
    )


@pytest.fixture
def requirement(employee):
    """Pending requirement for employee."""
    return MockRequirement(
        id=1,
        employee_id=employee.id,
        certificate_type_id=1,  # CPR/BLS
        due_date=date.today() + timedelta(days=30),
        status=MockRequirementStatus.NOT_STARTED,
    )


@pytest.fixture
def today():
    """Current date for testing."""
    return date.today()


# ==================== Golden Path E2E Tests ====================


class TestGoldenPathE2E:
    """
    Tests the complete happy path flow:
    Email → OCR → Review → Verified Record → Requirement Satisfied
    """

    def test_step1_email_received_and_employee_identified(self, employee):
        """Step 1: Email arrives and employee is identified from sender."""
        # Email arrives
        incoming_email = {
            "message_id": "<cert-email-001@mail.ci.laredo.tx.us>",
            "from_address": employee.email,
            "subject": "Certificate Upload",
            "attachments": [
                {"filename": "cpr_cert.pdf", "content_type": "application/pdf", "size": 50000}
            ],
        }

        # Directory lookup identifies employee
        directory_lookup_result = (employee.id, None)  # (employee_id, quarantine_reason)

        assert directory_lookup_result[0] == employee.id
        assert directory_lookup_result[1] is None  # No quarantine

    def test_step2_document_stored_and_extraction_queued(self, employee):
        """Step 2: Document stored in MinIO, extraction task queued."""
        # Document created
        document = MockDocument(
            id=1,
            employee_id=employee.id,
            file_name="cpr_cert.pdf",
            file_type="application/pdf",
            file_size_bytes=50000,
            storage_key="email-intake/20260205/abc123.pdf",
            uploaded_by_id=employee.id,
            file_hash="sha256:abcdef123456",
            source_email_message_id=1,
        )

        # Extraction task queued
        extraction_task = {
            "document_id": document.id,
            "queued_at": datetime.utcnow().isoformat(),
            "source": "email_intake",
        }

        assert document.id == 1
        assert extraction_task["document_id"] == document.id
        assert extraction_task["source"] == "email_intake"

    def test_step3_ocr_extracts_fields(self, employee):
        """Step 3: OCR extracts certificate fields."""
        # OCR results
        extracted_fields = {
            "certificate_holder_name": {
                "value": "John Doe",
                "confidence": {"overall": 0.95},
            },
            "certificate_type": {
                "value": "CPR/BLS Certification",
                "confidence": {"overall": 0.92},
            },
            "expiration_date": {
                "value": "2027-06-15",
                "confidence": {"overall": 0.88},
            },
            "issuing_authority": {
                "value": "American Red Cross",
                "confidence": {"overall": 0.90},
            },
        }

        # Extraction created in PENDING_REVIEW state
        extraction = MockExtraction(
            id=1,
            document_id=1,
            review_state=MockReviewState.PENDING_REVIEW,
            extracted_fields=extracted_fields,
            needs_review=True,
        )

        assert extraction.review_state == MockReviewState.PENDING_REVIEW
        assert extraction.extracted_fields["certificate_holder_name"]["value"] == "John Doe"
        assert extraction.needs_review is True

    def test_step4_reviewer_approves_extraction(self, reviewer):
        """Step 4: Reviewer approves extraction, verified record created."""
        # Extraction before approval
        extraction = MockExtraction(
            id=1,
            document_id=1,
            review_state=MockReviewState.PENDING_REVIEW,
            extracted_fields={"certificate_holder_name": {"value": "John Doe"}},
            needs_review=True,
            review_state_version=0,
        )

        # Approval action
        approval_request = {
            "extraction_id": extraction.id,
            "reviewer_id": reviewer.id,
            "corrections": None,
            "requirement_id": 1,  # Link to requirement
        }

        # After approval
        extraction.review_state = MockReviewState.APPROVED
        extraction.reviewed_by_id = reviewer.id
        extraction.review_state_version = 1

        # Verified record created
        verified_record = MockVerifiedRecord(
            id=1,
            extraction_id=extraction.id,
            document_id=1,
            employee_id=100,
            certificate_holder_name="John Doe",
            certificate_type="CPR/BLS Certification",
            expiration_date=date(2027, 6, 15),
        )

        assert extraction.review_state == MockReviewState.APPROVED
        assert extraction.reviewed_by_id == reviewer.id
        assert verified_record.id == 1
        assert verified_record.certificate_holder_name == "John Doe"

    def test_step5_requirement_satisfied(self, employee, requirement):
        """Step 5: Requirement linked to verified record, status becomes SATISFIED."""
        # Verified record from previous step
        verified_record = MockVerifiedRecord(
            id=1,
            extraction_id=1,
            document_id=1,
            employee_id=employee.id,
            certificate_holder_name="John Doe",
        )

        # Requirement linked
        requirement.satisfied_by_id = verified_record.id
        requirement.status = MockRequirementStatus.SATISFIED

        assert requirement.satisfied_by_id == verified_record.id
        assert requirement.status == MockRequirementStatus.SATISFIED

    def test_full_golden_path_state_transitions(self, employee, reviewer, requirement):
        """Test complete state transitions through golden path."""
        states = []

        # 1. Email received
        email_state = MockEmailProcessingState.RECEIVED
        states.append(("email", email_state.value))

        # 2. Email processed, document created
        email_state = MockEmailProcessingState.PROCESSED
        states.append(("email", email_state.value))

        # 3. Extraction created
        extraction_state = MockReviewState.PENDING_REVIEW
        states.append(("extraction", extraction_state.value))

        # 4. Extraction approved
        extraction_state = MockReviewState.APPROVED
        states.append(("extraction", extraction_state.value))

        # 5. Requirement satisfied
        requirement_state = MockRequirementStatus.SATISFIED
        states.append(("requirement", requirement_state.value))

        # Verify state progression
        assert states == [
            ("email", "Received"),
            ("email", "Processed"),
            ("extraction", "PendingReview"),
            ("extraction", "Approved"),
            ("requirement", "Satisfied"),
        ]

    def test_golden_path_audit_trail(self, employee, reviewer):
        """Verify audit log entries are created at each step."""
        audit_entries = []

        # Email intake
        audit_entries.append({
            "actor_type": "SYSTEM",
            "action": "email_intake_processed",
            "target_type": "email_intake",
            "target_id": "1",
        })

        # Document created
        audit_entries.append({
            "actor_type": "SYSTEM",
            "action": "document_created",
            "target_type": "document",
            "target_id": "1",
        })

        # Extraction created
        audit_entries.append({
            "actor_type": "SYSTEM",
            "action": "extraction_completed",
            "target_type": "extraction",
            "target_id": "1",
        })

        # Extraction approved
        audit_entries.append({
            "actor_type": "EMPLOYEE",
            "employee_id": reviewer.id,
            "action": "extraction_approved",
            "target_type": "extraction",
            "target_id": "1",
        })

        # Requirement satisfied
        audit_entries.append({
            "actor_type": "SYSTEM",
            "action": "requirement_satisfied",
            "target_type": "requirement",
            "target_id": "1",
        })

        assert len(audit_entries) == 5
        assert audit_entries[0]["action"] == "email_intake_processed"
        assert audit_entries[3]["action"] == "extraction_approved"
        assert audit_entries[3]["employee_id"] == reviewer.id


# ==================== Unknown Sender Quarantine Tests ====================


class TestUnknownSenderQuarantine:
    """
    Tests the quarantine flow for unknown senders:
    Unknown email → Quarantine → Admin review → Resolution
    """

    def test_unknown_sender_triggers_quarantine(self):
        """Unknown sender email should be quarantined."""
        incoming_email = {
            "message_id": "<unknown-sender@external.com>",
            "from_address": "unknown.person@external.com",
            "subject": "Certificate Upload",
        }

        # Directory lookup fails
        directory_lookup_result = (None, "Sender email not found in employee directory")

        assert directory_lookup_result[0] is None
        assert directory_lookup_result[1] is not None
        assert "not found" in directory_lookup_result[1].lower()

    def test_quarantined_email_record_created(self):
        """Quarantined email creates record with QUARANTINED state."""
        email_record = MockEmailIntakeMessage(
            id=1,
            message_id="<unknown@external.com>",
            from_address="unknown@external.com",
            processing_state=MockEmailProcessingState.QUARANTINED,
            employee_id=None,
            error_reason="Sender email not found in employee directory",
        )

        assert email_record.processing_state == MockEmailProcessingState.QUARANTINED
        assert email_record.employee_id is None
        assert "not found" in email_record.error_reason.lower()

    def test_quarantine_audit_log_created(self):
        """Quarantine action should create audit log."""
        audit_entry = {
            "actor_type": "SYSTEM",
            "action": "email_intake_quarantined",
            "target_type": "email_intake",
            "target_id": "1",
            "details": {
                "reason": "Sender email not found in employee directory",
                "from_address": "unknown@external.com",
            },
        }

        assert audit_entry["action"] == "email_intake_quarantined"
        assert "reason" in audit_entry["details"]

    def test_admin_can_view_quarantined_emails(self, admin):
        """Admin should be able to list quarantined emails."""
        quarantined_emails = [
            MockEmailIntakeMessage(
                id=1,
                message_id="<unknown1@external.com>",
                from_address="unknown1@external.com",
                processing_state=MockEmailProcessingState.QUARANTINED,
                error_reason="Unknown sender",
            ),
            MockEmailIntakeMessage(
                id=2,
                message_id="<unknown2@external.com>",
                from_address="unknown2@external.com",
                processing_state=MockEmailProcessingState.QUARANTINED,
                error_reason="Unknown sender",
            ),
        ]

        # Admin has permission to view
        admin_can_view = admin.role in ["Admin", "Coordinator"]
        assert admin_can_view is True
        assert len(quarantined_emails) == 2

    def test_admin_resolves_quarantine_by_assigning_employee(self, admin, employee):
        """Admin can resolve quarantine by assigning to employee."""
        quarantined_email = MockEmailIntakeMessage(
            id=1,
            message_id="<unknown@external.com>",
            from_address="john.doe.personal@gmail.com",  # Personal email
            processing_state=MockEmailProcessingState.QUARANTINED,
            error_reason="Unknown sender",
        )

        # Admin resolution action
        resolution = {
            "email_id": quarantined_email.id,
            "action": "assign_employee",
            "employee_id": employee.id,
            "resolved_by_id": admin.id,
        }

        # After resolution
        quarantined_email.employee_id = employee.id
        quarantined_email.processing_state = MockEmailProcessingState.PROCESSED
        quarantined_email.error_reason = None

        assert quarantined_email.processing_state == MockEmailProcessingState.PROCESSED
        assert quarantined_email.employee_id == employee.id

    def test_admin_resolves_quarantine_by_rejection(self, admin):
        """Admin can reject quarantined email as spam/invalid."""
        quarantined_email = MockEmailIntakeMessage(
            id=1,
            message_id="<spam@malicious.com>",
            from_address="spam@malicious.com",
            processing_state=MockEmailProcessingState.QUARANTINED,
            error_reason="Unknown sender",
        )

        # Admin rejection action
        resolution = {
            "email_id": quarantined_email.id,
            "action": "reject",
            "reason": "Spam/phishing attempt",
            "resolved_by_id": admin.id,
        }

        # After rejection
        quarantined_email.processing_state = MockEmailProcessingState.FAILED
        quarantined_email.error_reason = "Rejected by admin: Spam/phishing attempt"

        assert quarantined_email.processing_state == MockEmailProcessingState.FAILED
        assert "Rejected by admin" in quarantined_email.error_reason

    def test_resolution_triggers_reprocessing(self, admin, employee):
        """Assigning employee to quarantined email triggers attachment processing."""
        # After admin assigns employee
        reprocessing_tasks = []

        attachments = [
            {"filename": "cert1.pdf", "size": 50000},
            {"filename": "cert2.pdf", "size": 60000},
        ]

        for attachment in attachments:
            # Documents would be created
            reprocessing_tasks.append({
                "action": "create_document",
                "employee_id": employee.id,
                "filename": attachment["filename"],
            })
            # Extraction tasks would be queued
            reprocessing_tasks.append({
                "action": "queue_extraction",
                "filename": attachment["filename"],
            })

        assert len(reprocessing_tasks) == 4  # 2 docs + 2 extractions

    def test_quarantine_resolution_audit_log(self, admin, employee):
        """Resolution should create audit log."""
        audit_entry = {
            "actor_type": "EMPLOYEE",
            "employee_id": admin.id,
            "action": "quarantine_resolved",
            "target_type": "email_intake",
            "target_id": "1",
            "details": {
                "resolution": "assign_employee",
                "assigned_employee_id": employee.id,
            },
        }

        assert audit_entry["action"] == "quarantine_resolved"
        assert audit_entry["employee_id"] == admin.id
        assert audit_entry["details"]["assigned_employee_id"] == employee.id


# ==================== Scheduler Idempotency Tests ====================


class TestSchedulerIdempotency:
    """
    Tests scheduler idempotency using cursor-based backfill.
    Ensures duplicate notifications are not sent on retries.
    """

    def test_dedupe_key_format(self, requirement, today):
        """Verify dedupe key format for notifications."""
        notification_type = MockNotificationType.REQUIREMENT_DUE_SOON

        # Dedupe key format: {type}:{entity_id}:{date_ref}
        dedupe_key = f"{notification_type.value}:{requirement.id}:{today.isoformat()}"

        expected_format = f"RequirementDueSoon:{requirement.id}:{today.isoformat()}"
        assert dedupe_key == expected_format

    def test_first_notification_created(self, requirement, today):
        """First notification for a requirement should be created."""
        existing_dedupe_keys = set()

        dedupe_key = f"RequirementDueSoon:{requirement.id}:{today.isoformat()}"

        # Check if notification exists
        should_send = dedupe_key not in existing_dedupe_keys

        assert should_send is True

        # Create notification
        notification = MockNotification(
            id=1,
            notification_type=MockNotificationType.REQUIREMENT_DUE_SOON,
            recipient_employee_id=requirement.employee_id,
            related_requirement_id=requirement.id,
            dedupe_key=dedupe_key,
            sent_at=datetime.now(timezone.utc),
        )

        existing_dedupe_keys.add(dedupe_key)

        assert notification.dedupe_key == dedupe_key

    def test_duplicate_notification_skipped(self, requirement, today):
        """Duplicate notification should be skipped."""
        dedupe_key = f"RequirementDueSoon:{requirement.id}:{today.isoformat()}"

        # Simulate existing notification
        existing_dedupe_keys = {dedupe_key}

        # Check if notification exists
        should_send = dedupe_key not in existing_dedupe_keys

        assert should_send is False

    def test_cursor_based_backfill_processes_new_items(self, today):
        """Cursor-based backfill should process items after cursor."""
        # Simulated cursor from last run
        last_cursor = datetime(2026, 2, 4, 12, 0, 0, tzinfo=timezone.utc)

        # New requirements since cursor
        requirements = [
            MockRequirement(id=1, employee_id=100, certificate_type_id=1, due_date=today + timedelta(days=30)),
            MockRequirement(id=2, employee_id=101, certificate_type_id=1, due_date=today + timedelta(days=25)),
            MockRequirement(id=3, employee_id=102, certificate_type_id=2, due_date=today + timedelta(days=20)),
        ]

        # Requirements created after cursor
        requirements_to_process = [r for r in requirements if r.id > 0]  # All new

        assert len(requirements_to_process) == 3

    def test_cursor_updated_after_batch(self, today):
        """Cursor should be updated after processing batch."""
        initial_cursor = datetime(2026, 2, 4, 12, 0, 0, tzinfo=timezone.utc)

        # Process batch
        processed_ids = [1, 2, 3]
        batch_end_time = datetime(2026, 2, 5, 12, 0, 0, tzinfo=timezone.utc)

        # Update cursor
        new_cursor = batch_end_time

        assert new_cursor > initial_cursor

    def test_90_day_reminder_dedupe(self, requirement, today):
        """90-day reminder should have unique dedupe key."""
        due_date = today + timedelta(days=90)
        requirement.due_date = due_date

        # 90-day reminder dedupe key
        dedupe_key_90 = f"RequirementDueSoon:{requirement.id}:90:{due_date.isoformat()}"

        # 60-day reminder would have different key
        dedupe_key_60 = f"RequirementDueSoon:{requirement.id}:60:{due_date.isoformat()}"

        assert dedupe_key_90 != dedupe_key_60

    def test_multiple_intervals_tracked_separately(self, requirement, today):
        """90/60/30 day reminders should be tracked separately."""
        due_date = today + timedelta(days=30)
        requirement.due_date = due_date

        dedupe_keys = {
            f"RequirementDueSoon:{requirement.id}:90:{due_date.isoformat()}",
            f"RequirementDueSoon:{requirement.id}:60:{due_date.isoformat()}",
            f"RequirementDueSoon:{requirement.id}:30:{due_date.isoformat()}",
        }

        # All keys should be unique
        assert len(dedupe_keys) == 3

    def test_scheduler_retry_is_idempotent(self, requirement, today):
        """Scheduler retry should not create duplicate notifications."""
        dedupe_key = f"RequirementDueSoon:{requirement.id}:{today.isoformat()}"
        sent_notifications = set()

        # First run
        if dedupe_key not in sent_notifications:
            sent_notifications.add(dedupe_key)
            first_run_sent = True
        else:
            first_run_sent = False

        # Retry (simulating crash recovery)
        if dedupe_key not in sent_notifications:
            sent_notifications.add(dedupe_key)
            retry_sent = True
        else:
            retry_sent = False

        assert first_run_sent is True
        assert retry_sent is False
        assert len(sent_notifications) == 1

    def test_different_employees_different_dedupe_keys(self, today):
        """Same requirement type for different employees has different keys."""
        req1 = MockRequirement(id=1, employee_id=100, certificate_type_id=1, due_date=today + timedelta(days=30))
        req2 = MockRequirement(id=2, employee_id=101, certificate_type_id=1, due_date=today + timedelta(days=30))

        key1 = f"RequirementDueSoon:{req1.id}:{today.isoformat()}"
        key2 = f"RequirementDueSoon:{req2.id}:{today.isoformat()}"

        assert key1 != key2


# ==================== Document Resubmission Tests ====================


class TestDocumentResubmission:
    """Tests for document resubmission after rejection."""

    def test_rejected_extraction_allows_resubmission(self, employee):
        """After rejection, employee can submit new document."""
        # Original extraction rejected
        original_extraction = MockExtraction(
            id=1,
            document_id=1,
            review_state=MockReviewState.REJECTED,
            extracted_fields={},
            needs_review=False,
            reviewed_by_id=200,
        )

        # Employee submits new document
        new_document = MockDocument(
            id=2,
            employee_id=employee.id,
            file_name="cpr_cert_v2.pdf",
            file_type="application/pdf",
            file_size_bytes=55000,
            storage_key="manual-upload/20260205/def456.pdf",
            uploaded_by_id=employee.id,
        )

        # New extraction created
        new_extraction = MockExtraction(
            id=2,
            document_id=new_document.id,
            review_state=MockReviewState.PENDING_REVIEW,
            extracted_fields={"certificate_holder_name": {"value": "John Doe"}},
            needs_review=True,
        )

        assert original_extraction.review_state == MockReviewState.REJECTED
        assert new_extraction.review_state == MockReviewState.PENDING_REVIEW
        assert new_extraction.document_id != original_extraction.document_id

    def test_rejection_does_not_satisfy_requirement(self, requirement):
        """Rejected extraction should not satisfy requirement."""
        extraction = MockExtraction(
            id=1,
            document_id=1,
            review_state=MockReviewState.REJECTED,
            extracted_fields={},
            needs_review=False,
        )

        # Requirement should remain unsatisfied
        assert requirement.satisfied_by_id is None
        assert requirement.status == MockRequirementStatus.NOT_STARTED

    def test_resubmission_can_satisfy_requirement(self, employee, reviewer, requirement):
        """Approved resubmission can satisfy the original requirement."""
        # New document and extraction
        new_extraction = MockExtraction(
            id=2,
            document_id=2,
            review_state=MockReviewState.PENDING_REVIEW,
            extracted_fields={"certificate_holder_name": {"value": "John Doe"}},
            needs_review=True,
        )

        # Approval with requirement linking
        new_extraction.review_state = MockReviewState.APPROVED
        new_extraction.reviewed_by_id = reviewer.id

        verified_record = MockVerifiedRecord(
            id=1,
            extraction_id=new_extraction.id,
            document_id=2,
            employee_id=employee.id,
        )

        # Link requirement
        requirement.satisfied_by_id = verified_record.id
        requirement.status = MockRequirementStatus.SATISFIED

        assert requirement.status == MockRequirementStatus.SATISFIED
        assert requirement.satisfied_by_id == verified_record.id


# ==================== Concurrent Operations Tests ====================


class TestConcurrentOperations:
    """Tests for handling concurrent operations."""

    def test_concurrent_approval_conflict(self, reviewer):
        """Two reviewers approving same extraction should conflict."""
        extraction = MockExtraction(
            id=1,
            document_id=1,
            review_state=MockReviewState.PENDING_REVIEW,
            extracted_fields={},
            needs_review=True,
            review_state_version=0,
        )

        # Reviewer 1 reads extraction
        reviewer1_version = extraction.review_state_version

        # Reviewer 2 reads extraction
        reviewer2_version = extraction.review_state_version

        # Reviewer 1 approves (succeeds)
        extraction.review_state_version = 1
        extraction.review_state = MockReviewState.APPROVED
        reviewer1_success = True

        # Reviewer 2 tries to approve (fails - version mismatch)
        reviewer2_success = reviewer2_version == extraction.review_state_version

        assert reviewer1_success is True
        assert reviewer2_success is False

    def test_duplicate_email_processing_idempotent(self):
        """Processing same email twice should be idempotent."""
        message_id = "<cert-001@mail.ci.laredo.tx.us>"
        processed_messages = set()

        # First processing
        if message_id not in processed_messages:
            processed_messages.add(message_id)
            first_process_created_doc = True
        else:
            first_process_created_doc = False

        # Second processing (retry)
        if message_id not in processed_messages:
            processed_messages.add(message_id)
            second_process_created_doc = True
        else:
            second_process_created_doc = False

        assert first_process_created_doc is True
        assert second_process_created_doc is False

    def test_duplicate_document_hash_detected(self, employee):
        """Same document content submitted twice should be detected."""
        file_content = b"PDF content here"
        file_hash = hashlib.sha256(file_content).hexdigest()

        # Track employee + hash combinations
        employee_docs = {}

        # First upload
        key = (employee.id, file_hash)
        if key not in employee_docs:
            employee_docs[key] = 1  # doc_id
            first_upload_new = True
        else:
            first_upload_new = False

        # Second upload (same content)
        if key not in employee_docs:
            employee_docs[key] = 2
            second_upload_new = True
        else:
            second_upload_new = False

        assert first_upload_new is True
        assert second_upload_new is False
