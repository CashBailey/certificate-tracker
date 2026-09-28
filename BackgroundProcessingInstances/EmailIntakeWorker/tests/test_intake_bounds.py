"""Bounds and retry idempotency for email attachment storage."""

from unittest.mock import MagicMock, patch

from src.email_client import EmailAttachment
from src.worker import MAX_FILENAME_LENGTH, EmailIntakeWorker


def _worker() -> EmailIntakeWorker:
    with patch("src.worker.get_session_factory", MagicMock()):
        return EmailIntakeWorker(
            email_client=MagicMock(),
            directory_lookup=MagicMock(),
            minio_client=MagicMock(),
            redis_client=MagicMock(),
        )


def test_overlong_filename_is_rejected_before_storage():
    attachment = EmailAttachment(
        filename=f"{'x' * MAX_FILENAME_LENGTH}.pdf",
        content_type="application/pdf",
        payload=b"%PDF-1.4 minimal",
        size=16,
    )

    error = _worker()._validate_attachment(attachment)

    assert error == f"Filename exceeds {MAX_FILENAME_LENGTH} characters"


def test_storage_key_is_stable_for_retries():
    worker = _worker()

    first = worker._generate_storage_key("certificate.pdf", 42, "a" * 64)
    retried = worker._generate_storage_key("certificate.pdf", 42, "a" * 64)

    assert first == retried
    assert first.startswith("email-intake/")
    assert "/42/" not in first


def test_storage_key_is_scoped_by_employee_and_content():
    worker = _worker()

    original = worker._generate_storage_key("certificate.pdf", 42, "a" * 64)

    assert worker._generate_storage_key("certificate.pdf", 43, "a" * 64) != original
    assert worker._generate_storage_key("certificate.pdf", 42, "b" * 64) != original
