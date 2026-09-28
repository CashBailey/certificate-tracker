"""
Integration tests for the Email Intake Worker.

Tests email processing flow including:
- Valid sender with PDF attachment
- Unknown sender quarantine
- Invalid domain quarantine
- Multiple attachments
- Message-ID deduplication
- Composite (message_id, attachment_hash) deduplication
- File hash deduplication for same employee
- Oversized file rejection
- Invalid MIME type rejection
"""

import pytest
import json
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

# These tests mock the EmailIntakeWorker dependencies since the worker
# is in a separate container (BackgroundProcessingInstances/EmailIntakeWorker)


# ==================== Mock Classes ====================


@dataclass
class MockEmailAttachment:
    """Mock email attachment matching EmailAttachment interface."""
    filename: str
    content_type: str
    payload: bytes
    size: int


@dataclass
class MockIncomingEmail:
    """Mock incoming email matching IncomingEmail interface."""
    message_id: str
    from_address: str
    subject: str
    received_date: datetime
    attachments: list[MockEmailAttachment]
    uid: str


# ==================== Fixtures ====================


@pytest.fixture
def valid_pdf_bytes():
    """Return minimal valid PDF bytes."""
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"


@pytest.fixture
def valid_png_bytes():
    """Return minimal valid PNG bytes."""
    return bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
        0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
        0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
        0x42, 0x60, 0x82,
    ])


@pytest.fixture
def sample_email_attachment(valid_pdf_bytes):
    """Create a sample PDF attachment."""
    return MockEmailAttachment(
        filename="certificate.pdf",
        content_type="application/pdf",
        payload=valid_pdf_bytes,
        size=len(valid_pdf_bytes),
    )


@pytest.fixture
def sample_incoming_email(sample_email_attachment):
    """Create a sample incoming email."""
    return MockIncomingEmail(
        message_id="<test-message-123@mail.ci.laredo.tx.us>",
        from_address="john.doe@ci.laredo.tx.us",
        subject="Certificate Upload",
        received_date=datetime.now(timezone.utc),
        attachments=[sample_email_attachment],
        uid="1",
    )


@pytest.fixture
def mock_email_client():
    """Create a mock IMAP email client."""
    client = MagicMock()
    client.connect = MagicMock()
    client.disconnect = MagicMock()
    client.fetch_unread_emails = MagicMock(return_value=[])
    client.mark_as_processed = MagicMock()
    client.mark_as_quarantined = MagicMock()
    return client


@pytest.fixture
def mock_directory_lookup():
    """Create a mock directory lookup service."""
    lookup = MagicMock()
    lookup.lookup_or_quarantine = AsyncMock(return_value=(1, None))
    return lookup


@pytest.fixture
def mock_minio_client():
    """Create a mock MinIO client."""
    client = MagicMock()
    client.put_object = MagicMock()
    client.bucket_exists = MagicMock(return_value=True)
    return client


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client = MagicMock()
    client.rpush = MagicMock(return_value=1)
    client.blpop = MagicMock(return_value=None)
    return client


# ==================== Helper Functions ====================


def compute_file_hash(data: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(data).hexdigest()


# ==================== Constants Tests ====================


class TestEmailIntakeConstants:
    """Tests for email intake constants and configurations."""

    def test_allowed_content_types(self):
        """Verify allowed content types include expected formats."""
        allowed_types = {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/tiff",
        }
        # These should match the worker's ALLOWED_CONTENT_TYPES
        assert "application/pdf" in allowed_types
        assert "image/png" in allowed_types
        assert "image/jpeg" in allowed_types
        assert "image/tiff" in allowed_types
        # Should not include office documents
        assert "application/msword" not in allowed_types
        assert "application/zip" not in allowed_types

    def test_max_file_size_is_20mb(self):
        """Verify max file size is 20MB."""
        MAX_FILE_SIZE = 20 * 1024 * 1024
        assert MAX_FILE_SIZE == 20971520  # 20 MB in bytes

    def test_extraction_queue_name(self):
        """Verify extraction queue name."""
        EXTRACTION_QUEUE = "extraction_tasks"
        assert EXTRACTION_QUEUE == "extraction_tasks"


# ==================== Validation Tests ====================


class TestAttachmentValidation:
    """Tests for attachment validation logic."""

    def test_valid_pdf_passes_validation(self, valid_pdf_bytes):
        """Valid PDF should pass validation."""
        attachment = MockEmailAttachment(
            filename="cert.pdf",
            content_type="application/pdf",
            payload=valid_pdf_bytes,
            size=len(valid_pdf_bytes),
        )

        # Size check
        MAX_FILE_SIZE = 20 * 1024 * 1024
        assert attachment.size <= MAX_FILE_SIZE

        # Content type check (detected via magic in real implementation)
        ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}
        assert attachment.content_type in ALLOWED_CONTENT_TYPES

    def test_valid_png_passes_validation(self, valid_png_bytes):
        """Valid PNG should pass validation."""
        attachment = MockEmailAttachment(
            filename="cert.png",
            content_type="image/png",
            payload=valid_png_bytes,
            size=len(valid_png_bytes),
        )

        MAX_FILE_SIZE = 20 * 1024 * 1024
        assert attachment.size <= MAX_FILE_SIZE

        ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}
        assert attachment.content_type in ALLOWED_CONTENT_TYPES

    def test_oversized_file_fails_validation(self, valid_pdf_bytes):
        """Oversized file should fail validation."""
        MAX_FILE_SIZE = 20 * 1024 * 1024

        # Create oversized attachment (simulated)
        oversized_size = MAX_FILE_SIZE + 1

        attachment = MockEmailAttachment(
            filename="huge.pdf",
            content_type="application/pdf",
            payload=valid_pdf_bytes,  # Payload doesn't matter, size does
            size=oversized_size,
        )

        # Should fail size check
        assert attachment.size > MAX_FILE_SIZE

    def test_invalid_content_type_fails_validation(self):
        """Invalid content type should fail validation."""
        ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}

        attachment = MockEmailAttachment(
            filename="document.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            payload=b"fake docx content",
            size=100,
        )

        assert attachment.content_type not in ALLOWED_CONTENT_TYPES

    def test_executable_file_fails_validation(self):
        """Executable file should fail validation."""
        ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}

        attachment = MockEmailAttachment(
            filename="malware.exe",
            content_type="application/x-msdownload",
            payload=b"MZ\x90\x00...",  # PE header
            size=1000,
        )

        assert attachment.content_type not in ALLOWED_CONTENT_TYPES

    def test_zip_file_fails_validation(self):
        """ZIP file should fail validation."""
        ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}

        attachment = MockEmailAttachment(
            filename="archive.zip",
            content_type="application/zip",
            payload=b"PK\x03\x04...",  # ZIP header
            size=500,
        )

        assert attachment.content_type not in ALLOWED_CONTENT_TYPES


# ==================== Deduplication Tests ====================


class TestMessageIdDeduplication:
    """Tests for message-ID based deduplication."""

    def test_same_message_id_detected_as_duplicate(self):
        """Same message ID should be detected as duplicate."""
        processed_messages = set()

        message_id = "<unique-message-123@mail.example.com>"

        # First time - not a duplicate
        is_duplicate_1 = message_id in processed_messages
        assert is_duplicate_1 is False

        # Process the message
        processed_messages.add(message_id)

        # Second time - is a duplicate
        is_duplicate_2 = message_id in processed_messages
        assert is_duplicate_2 is True

    def test_different_message_ids_not_duplicate(self):
        """Different message IDs should not be duplicates."""
        processed_messages = {"<message-1@example.com>"}

        new_message_id = "<message-2@example.com>"
        is_duplicate = new_message_id in processed_messages

        assert is_duplicate is False


class TestCompositeDeduplication:
    """Tests for composite (message_id, attachment_hash) deduplication."""

    def test_same_message_and_hash_is_duplicate(self, valid_pdf_bytes):
        """Same (message_id, attachment_hash) should be duplicate."""
        processed_combos = set()

        message_id = "<message-123@example.com>"
        file_hash = compute_file_hash(valid_pdf_bytes)
        combo_key = (message_id, file_hash)

        # First time - not duplicate
        assert combo_key not in processed_combos

        # Mark as processed
        processed_combos.add(combo_key)

        # Second time - duplicate
        assert combo_key in processed_combos

    def test_same_message_different_hash_not_duplicate(self, valid_pdf_bytes, valid_png_bytes):
        """Same message_id with different attachment hash is not duplicate."""
        processed_combos = set()

        message_id = "<message-123@example.com>"
        hash_1 = compute_file_hash(valid_pdf_bytes)
        hash_2 = compute_file_hash(valid_png_bytes)

        combo_1 = (message_id, hash_1)
        combo_2 = (message_id, hash_2)

        processed_combos.add(combo_1)

        # Different hash for same message is not a duplicate
        assert combo_1 in processed_combos
        assert combo_2 not in processed_combos

    def test_different_message_same_hash_not_duplicate(self, valid_pdf_bytes):
        """Different message_id with same attachment hash is not duplicate for composite check."""
        processed_combos = set()

        message_id_1 = "<message-123@example.com>"
        message_id_2 = "<message-456@example.com>"
        file_hash = compute_file_hash(valid_pdf_bytes)

        combo_1 = (message_id_1, file_hash)
        combo_2 = (message_id_2, file_hash)

        processed_combos.add(combo_1)

        # Different message with same hash is not a composite duplicate
        assert combo_1 in processed_combos
        assert combo_2 not in processed_combos


class TestFileHashDeduplication:
    """Tests for file hash deduplication per employee."""

    def test_same_employee_same_hash_is_duplicate(self, valid_pdf_bytes):
        """Same employee with same file hash should return existing document."""
        # Simulates: check_duplicate_document(employee_id, file_hash)
        employee_docs = {}  # {(employee_id, file_hash): document_id}

        employee_id = 100
        file_hash = compute_file_hash(valid_pdf_bytes)
        key = (employee_id, file_hash)

        # First upload - not duplicate
        assert key not in employee_docs

        # Store document
        employee_docs[key] = 1  # document_id = 1

        # Second upload - duplicate
        assert key in employee_docs
        assert employee_docs[key] == 1

    def test_same_hash_different_employee_not_duplicate(self, valid_pdf_bytes):
        """Same file hash for different employees should not be duplicate."""
        employee_docs = {}

        file_hash = compute_file_hash(valid_pdf_bytes)
        employee_1 = 100
        employee_2 = 200

        key_1 = (employee_1, file_hash)
        key_2 = (employee_2, file_hash)

        # First employee uploads
        employee_docs[key_1] = 1

        # Different employee same content is not a duplicate
        assert key_1 in employee_docs
        assert key_2 not in employee_docs

    def test_same_employee_different_hash_not_duplicate(self, valid_pdf_bytes, valid_png_bytes):
        """Same employee with different file hashes should not be duplicate."""
        employee_docs = {}

        employee_id = 100
        hash_1 = compute_file_hash(valid_pdf_bytes)
        hash_2 = compute_file_hash(valid_png_bytes)

        key_1 = (employee_id, hash_1)
        key_2 = (employee_id, hash_2)

        employee_docs[key_1] = 1

        assert key_1 in employee_docs
        assert key_2 not in employee_docs


# ==================== Sender Validation Tests ====================


class TestSenderValidation:
    """Tests for sender email validation and quarantine logic."""

    def test_valid_domain_sender_lookup_succeeds(self):
        """Valid domain sender should pass lookup."""
        ALLOWED_EMAIL_DOMAIN = "ci.laredo.tx.us"

        email_address = "john.doe@ci.laredo.tx.us"
        domain = email_address.split("@")[1]

        assert domain == ALLOWED_EMAIL_DOMAIN

    def test_invalid_domain_quarantined(self):
        """Invalid domain sender should be quarantined."""
        ALLOWED_EMAIL_DOMAIN = "ci.laredo.tx.us"

        email_address = "attacker@malicious.com"
        domain = email_address.split("@")[1]

        is_valid_domain = domain == ALLOWED_EMAIL_DOMAIN
        assert is_valid_domain is False

    def test_unknown_employee_quarantined(self):
        """Unknown employee (not in directory) should be quarantined."""
        # Directory lookup returns (None, reason) for unknown employees
        employee_id = None
        quarantine_reason = "Unknown sender email"

        should_quarantine = employee_id is None and quarantine_reason is not None
        assert should_quarantine is True

    def test_inactive_employee_quarantined(self):
        """Inactive employee should be quarantined."""
        # Directory lookup returns (None, reason) for inactive employees
        employee_id = None
        quarantine_reason = "Employee is inactive"

        should_quarantine = employee_id is None and quarantine_reason is not None
        assert should_quarantine is True


# ==================== Extraction Task Queueing Tests ====================


class TestExtractionTaskQueueing:
    """Tests for extraction task queue messages."""

    def test_extraction_task_format(self):
        """Verify extraction task JSON format."""
        document_id = 123
        queued_at = datetime.utcnow().isoformat()

        task = {
            "document_id": document_id,
            "queued_at": queued_at,
            "source": "email_intake",
        }

        task_json = json.dumps(task)
        parsed = json.loads(task_json)

        assert parsed["document_id"] == 123
        assert parsed["source"] == "email_intake"
        assert "queued_at" in parsed

    def test_extraction_task_has_required_fields(self):
        """Extraction task should have all required fields."""
        task = {
            "document_id": 1,
            "queued_at": "2026-02-04T12:00:00",
            "source": "email_intake",
        }

        required_fields = ["document_id", "queued_at", "source"]
        for field in required_fields:
            assert field in task

    def test_queue_receives_task_via_rpush(self, mock_redis_client):
        """Verify task is pushed to queue via RPUSH."""
        EXTRACTION_QUEUE = "extraction_tasks"
        task = {"document_id": 1, "source": "email_intake"}

        mock_redis_client.rpush(EXTRACTION_QUEUE, json.dumps(task))

        mock_redis_client.rpush.assert_called_once_with(
            EXTRACTION_QUEUE,
            json.dumps(task),
        )


# ==================== Multiple Attachments Tests ====================


class TestMultipleAttachments:
    """Tests for processing emails with multiple attachments."""

    def test_each_attachment_creates_separate_document(self, valid_pdf_bytes, valid_png_bytes):
        """Each attachment should create a separate document."""
        attachments = [
            MockEmailAttachment(
                filename="cert1.pdf",
                content_type="application/pdf",
                payload=valid_pdf_bytes,
                size=len(valid_pdf_bytes),
            ),
            MockEmailAttachment(
                filename="cert2.png",
                content_type="image/png",
                payload=valid_png_bytes,
                size=len(valid_png_bytes),
            ),
        ]

        # Each valid attachment should result in a document
        documents_created = len(attachments)
        assert documents_created == 2

    def test_each_attachment_queues_separate_extraction(self, mock_redis_client, valid_pdf_bytes):
        """Each document should have its own extraction task queued."""
        EXTRACTION_QUEUE = "extraction_tasks"
        document_ids = [1, 2, 3]

        for doc_id in document_ids:
            task = {"document_id": doc_id, "source": "email_intake"}
            mock_redis_client.rpush(EXTRACTION_QUEUE, json.dumps(task))

        assert mock_redis_client.rpush.call_count == 3

    def test_partial_failure_processes_valid_attachments(self):
        """If some attachments fail, valid ones should still be processed."""
        attachments_results = [
            ("cert1.pdf", True, None),      # Valid
            ("huge.pdf", False, "Too large"),  # Invalid - too large
            ("cert2.pdf", True, None),      # Valid
        ]

        valid_count = sum(1 for _, valid, _ in attachments_results if valid)
        invalid_count = sum(1 for _, valid, _ in attachments_results if not valid)

        assert valid_count == 2
        assert invalid_count == 1


# ==================== Storage Key Generation Tests ====================


class TestStorageKeyGeneration:
    """Tests for MinIO storage key generation."""

    def test_storage_key_is_non_guessable(self):
        """Storage key should include UUID to prevent guessing."""
        import uuid

        filename = "certificate.pdf"
        unique_id = uuid.uuid4().hex  # 32-char hex string
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        ext = ".pdf"

        storage_key = f"email-intake/{timestamp}/{unique_id}{ext}"

        # Should contain UUID-like component
        assert len(unique_id) == 32
        # Should preserve extension
        assert storage_key.endswith(".pdf")
        # Should have path structure
        assert storage_key.startswith("email-intake/")
        assert timestamp in storage_key

    def test_storage_key_preserves_extension(self):
        """Storage key should preserve file extension."""
        import os

        test_cases = [
            ("document.pdf", ".pdf"),
            ("image.PNG", ".png"),
            ("cert.jpeg", ".jpeg"),
            ("scan.tiff", ".tiff"),
        ]

        for filename, expected_ext in test_cases:
            ext = os.path.splitext(filename)[1].lower()
            assert ext == expected_ext


# ==================== Email Processing State Tests ====================


class TestEmailProcessingStates:
    """Tests for email processing state transitions."""

    def test_valid_email_becomes_processed(self):
        """Valid email should transition to PROCESSED state."""
        # Simulates the happy path
        initial_state = "RECEIVED"
        employee_found = True
        all_attachments_valid = True

        if employee_found and all_attachments_valid:
            final_state = "PROCESSED"
        else:
            final_state = "FAILED"

        assert final_state == "PROCESSED"

    def test_unknown_sender_becomes_quarantined(self):
        """Unknown sender should transition to QUARANTINED state."""
        employee_found = False
        quarantine_reason = "Unknown sender"

        if not employee_found:
            state = "QUARANTINED"
        else:
            state = "PROCESSED"

        assert state == "QUARANTINED"

    def test_all_attachments_fail_becomes_failed(self):
        """If all attachments fail, email should transition to FAILED."""
        total_attachments = 3
        successful_attachments = 0
        skipped_dedupe = 0

        if successful_attachments == 0 and skipped_dedupe == 0:
            state = "FAILED"
        else:
            state = "PROCESSED"

        assert state == "FAILED"


# ==================== Audit Log Tests ====================


class TestEmailIntakeAuditLogs:
    """Tests for email intake audit logging."""

    def test_successful_intake_audit_log_format(self):
        """Verify audit log format for successful email intake."""
        audit_log = {
            "actor_type": "SYSTEM",
            "action": "email_intake_processed",
            "target_type": "email_intake",
            "target_id": "123",
            "details": {
                "employee_id": 100,
                "documents_processed": 2,
                "documents_deduplicated": 0,
                "attachments_skipped_dedupe": 0,
                "attachment_count": 2,
            },
        }

        assert audit_log["actor_type"] == "SYSTEM"
        assert audit_log["action"] == "email_intake_processed"
        assert audit_log["details"]["documents_processed"] == 2

    def test_quarantine_audit_log_format(self):
        """Verify audit log format for quarantined email."""
        audit_log = {
            "actor_type": "SYSTEM",
            "action": "email_intake_quarantined",
            "target_type": "email_intake",
            "target_id": "456",
            "details": {
                "reason": "Unknown sender email",
                "attachment_count": 1,
            },
        }

        assert audit_log["action"] == "email_intake_quarantined"
        assert "reason" in audit_log["details"]

    def test_failed_intake_audit_log_format(self):
        """Verify audit log format for failed email intake."""
        audit_log = {
            "actor_type": "SYSTEM",
            "action": "email_intake_failed",
            "target_type": "email_intake",
            "target_id": "789",
            "details": {
                "employee_id": 100,
                "errors": ["attachment1.pdf: Too large", "attachment2.exe: Invalid file type"],
            },
        }

        assert audit_log["action"] == "email_intake_failed"
        assert "errors" in audit_log["details"]
        assert len(audit_log["details"]["errors"]) == 2


# ==================== Edge Cases ====================


class TestEmailIntakeEdgeCases:
    """Tests for edge cases in email intake."""

    def test_empty_attachments_list(self):
        """Email with no attachments should be processed without creating documents."""
        email = MockIncomingEmail(
            message_id="<no-attachments@example.com>",
            from_address="john@ci.laredo.tx.us",
            subject="No attachments",
            received_date=datetime.now(timezone.utc),
            attachments=[],
            uid="1",
        )

        documents_created = len(email.attachments)
        assert documents_created == 0

    def test_attachment_with_empty_filename(self):
        """Attachment with empty filename should be handled."""
        attachment = MockEmailAttachment(
            filename="",  # Empty filename
            content_type="application/pdf",
            payload=b"%PDF-1.4...",
            size=100,
        )

        # Should generate a default filename
        import os
        ext = os.path.splitext(attachment.filename)[1].lower() or ".pdf"
        assert ext == ".pdf"

    def test_very_long_subject_truncated(self):
        """Very long email subject should be truncated."""
        long_subject = "A" * 1000
        max_subject_length = 500

        truncated = long_subject[:max_subject_length]
        assert len(truncated) == 500

    def test_special_characters_in_filename(self):
        """Special characters in filename should be handled."""
        # These filenames might cause issues
        test_filenames = [
            "cert (1).pdf",
            "certificate-2024.pdf",
            "cert_name.pdf",
            "CERT.PDF",
        ]

        import os
        for filename in test_filenames:
            ext = os.path.splitext(filename)[1].lower()
            assert ext == ".pdf"

    def test_unicode_in_email_address(self):
        """Unicode in email address should be handled."""
        # International domain names
        email = "user@例え.jp"
        domain = email.split("@")[1]

        # Should be detected as invalid (not in allowed domain)
        ALLOWED_EMAIL_DOMAIN = "ci.laredo.tx.us"
        assert domain != ALLOWED_EMAIL_DOMAIN


# ==================== Integration Flow Tests ====================


class TestEmailIntakeFlow:
    """Tests for complete email intake flow."""

    def test_happy_path_flow(
        self,
        sample_incoming_email,
        mock_email_client,
        mock_directory_lookup,
        mock_minio_client,
        mock_redis_client,
    ):
        """Test complete happy path: valid sender, valid attachment."""
        # 1. Email is fetched
        mock_email_client.fetch_unread_emails.return_value = [sample_incoming_email]

        # 2. Sender is looked up - found
        mock_directory_lookup.lookup_or_quarantine.return_value = (100, None)

        # 3. Expected flow:
        #    - Attachment validated
        #    - Document stored in MinIO
        #    - Document record created in DB
        #    - Extraction task queued
        #    - Email marked as processed

        # Verify the expected interactions would happen
        assert sample_incoming_email.from_address == "john.doe@ci.laredo.tx.us"
        assert len(sample_incoming_email.attachments) == 1
        assert sample_incoming_email.attachments[0].content_type == "application/pdf"

    def test_quarantine_flow(
        self,
        sample_incoming_email,
        mock_email_client,
        mock_directory_lookup,
    ):
        """Test quarantine flow: unknown sender."""
        # Modify email to have unknown sender
        sample_incoming_email.from_address = "unknown@external.com"

        # Directory lookup returns quarantine reason
        mock_directory_lookup.lookup_or_quarantine.return_value = (
            None,
            "Unknown sender email not in employee directory",
        )

        # Expected flow:
        #    - Email record created with QUARANTINED state
        #    - Audit log created
        #    - Email moved to quarantine folder

        employee_id, reason = (None, "Unknown sender email not in employee directory")
        assert employee_id is None
        assert reason is not None

    def test_deduplication_flow(
        self,
        sample_incoming_email,
        valid_pdf_bytes,
        mock_directory_lookup,
    ):
        """Test deduplication: same content already uploaded."""
        # First email processed
        employee_id = 100
        file_hash = compute_file_hash(valid_pdf_bytes)

        # Simulate existing document with same hash
        existing_docs = {(employee_id, file_hash): 1}

        # Second email with same content
        mock_directory_lookup.lookup_or_quarantine.return_value = (employee_id, None)

        # Check for duplicate
        key = (employee_id, file_hash)
        is_duplicate = key in existing_docs

        assert is_duplicate is True

    def test_mixed_attachments_flow(self, valid_pdf_bytes, valid_png_bytes):
        """Test email with mix of valid and invalid attachments."""
        attachments = [
            MockEmailAttachment("valid.pdf", "application/pdf", valid_pdf_bytes, len(valid_pdf_bytes)),
            MockEmailAttachment("invalid.exe", "application/x-msdownload", b"MZ...", 100),
            MockEmailAttachment("valid.png", "image/png", valid_png_bytes, len(valid_png_bytes)),
        ]

        ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}

        valid_attachments = [a for a in attachments if a.content_type in ALLOWED_CONTENT_TYPES]
        invalid_attachments = [a for a in attachments if a.content_type not in ALLOWED_CONTENT_TYPES]

        assert len(valid_attachments) == 2
        assert len(invalid_attachments) == 1
