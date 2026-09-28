"""Transient malware-scan failures must be retryable, not terminal quarantine."""

from unittest.mock import MagicMock, patch

from src.malware_scanner import ScanResult
from src.worker import RETRYABLE_ERROR_PREFIX, EmailIntakeWorker
from src.email_client import EmailAttachment


def _worker(scanner):
    with patch("src.worker.get_session_factory", MagicMock()):
        return EmailIntakeWorker(
            email_client=MagicMock(),
            directory_lookup=MagicMock(),
            minio_client=MagicMock(),
            redis_client=MagicMock(),
            malware_scanner=scanner,
        )


def _pdf_attachment():
    return EmailAttachment(
        filename="cert.pdf",
        content_type="application/pdf",
        payload=b"%PDF-1.4 minimal",
        size=16,
    )


def test_scanner_unavailable_is_retryable():
    scanner = MagicMock()
    scanner.scan_bytes.return_value = ScanResult(
        is_clean=False, virus_name=None, error="Connection refused"
    )
    worker = _worker(scanner)

    with patch("src.worker.magic.from_buffer", return_value="application/pdf"):
        result = worker._validate_attachment(_pdf_attachment())

    assert result is not None
    assert result.startswith(RETRYABLE_ERROR_PREFIX)
    assert "Scan unavailable" in result


def test_malware_detection_is_terminal_not_retryable():
    scanner = MagicMock()
    scanner.scan_bytes.return_value = ScanResult(
        is_clean=False, virus_name="Eicar-Test-Signature", error=None
    )
    worker = _worker(scanner)

    with patch("src.worker.magic.from_buffer", return_value="application/pdf"):
        result = worker._validate_attachment(_pdf_attachment())

    assert result is not None
    assert not result.startswith(RETRYABLE_ERROR_PREFIX)
    assert "Malware detected" in result


def test_clean_attachment_passes():
    scanner = MagicMock()
    scanner.scan_bytes.return_value = ScanResult(is_clean=True)
    worker = _worker(scanner)

    with patch("src.worker.magic.from_buffer", return_value="application/pdf"):
        assert worker._validate_attachment(_pdf_attachment()) is None
