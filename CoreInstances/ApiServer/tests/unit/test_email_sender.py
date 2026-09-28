"""
Unit tests for shared email sending utility and email templates.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from src.shared.email_sender import send_email
from src.shared.email_templates import NAME_MISMATCH_REJECTION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SMTP_ENV = {
    "SMTP_HOST": "greenmail",
    "SMTP_PORT": "1025",
    "SMTP_USER": "",
    "SMTP_PASSWORD": "",
    "NOTIFICATION_FROM_EMAIL": "certs@ci.laredo.tx.us",
}


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# TestSendEmail
# ---------------------------------------------------------------------------

class TestSendEmail:
    """Tests for the send_email function."""

    @patch.dict("os.environ", SMTP_ENV, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_constructs_correct_mime_message(self, mock_send):
        """Verify From, To, Subject, and body are set correctly."""
        _run(send_email(to="emp@ci.laredo.tx.us", subject="Test", body="Hello"))

        mock_send.assert_called_once()
        message = mock_send.call_args[0][0]

        assert message["From"] == "certs@ci.laredo.tx.us"
        assert message["To"] == "emp@ci.laredo.tx.us"
        assert message["Subject"] == "Test"
        # Body is in the first (and only) attached part
        assert message.get_payload()[0].get_payload() == "Hello"

    @patch.dict("os.environ", SMTP_ENV, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_returns_true_on_success(self, mock_send):
        """send_email returns True when SMTP send succeeds."""
        result = _run(send_email(to="a@b.com", subject="s", body="b"))
        assert result is True

    @patch.dict("os.environ", SMTP_ENV, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock, side_effect=ConnectionRefusedError("no"))
    def test_returns_false_on_smtp_failure(self, mock_send):
        """send_email returns False (no exception raised) on SMTP failure."""
        result = _run(send_email(to="a@b.com", subject="s", body="b"))
        assert result is False

    @patch.dict("os.environ", {**SMTP_ENV, "SMTP_PORT": "587"}, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_start_tls_enabled_for_port_587(self, mock_send):
        """Port 587 should use start_tls=True."""
        _run(send_email(to="a@b.com", subject="s", body="b"))
        _, kwargs = mock_send.call_args
        assert kwargs["start_tls"] is True

    @patch.dict("os.environ", {**SMTP_ENV, "SMTP_PORT": "1025"}, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_start_tls_disabled_for_other_ports(self, mock_send):
        """Non-587 ports should use start_tls=False."""
        _run(send_email(to="a@b.com", subject="s", body="b"))
        _, kwargs = mock_send.call_args
        assert kwargs["start_tls"] is False

    @patch.dict("os.environ", SMTP_ENV, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_empty_smtp_user_passes_none(self, mock_send):
        """Empty SMTP_USER should pass username=None to aiosmtplib."""
        with patch.dict("os.environ", {"SMTP_USER": "", "SMTP_PASSWORD": ""}):
            _run(send_email(to="a@b.com", subject="s", body="b"))
        _, kwargs = mock_send.call_args
        assert kwargs["username"] is None
        assert kwargs["password"] is None

    @patch.dict("os.environ", {**SMTP_ENV, "SMTP_PORT": "587"}, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_tls_context_passed_for_starttls(self, mock_send):
        """Port 587 should pass SSLContext with CERT_REQUIRED."""
        import ssl
        _run(send_email(to="a@b.com", subject="s", body="b"))
        _, kwargs = mock_send.call_args
        assert isinstance(kwargs.get("tls_context"), ssl.SSLContext)
        assert kwargs["tls_context"].verify_mode == ssl.CERT_REQUIRED

    @patch.dict("os.environ", {**SMTP_ENV, "SMTP_PORT": "1025"}, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_no_tls_context_for_dev_port_1025(self, mock_send):
        """Dev port 1025 should not pass tls_context."""
        _run(send_email(to="a@b.com", subject="s", body="b"))
        _, kwargs = mock_send.call_args
        assert kwargs.get("tls_context") is None

    @patch.dict("os.environ", {**SMTP_ENV, "SMTP_PORT": "3025"}, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_no_tls_context_for_dev_port_3025(self, mock_send):
        """Dev port 3025 (GreenMail) should not pass tls_context."""
        _run(send_email(to="a@b.com", subject="s", body="b"))
        _, kwargs = mock_send.call_args
        assert kwargs["start_tls"] is False
        assert kwargs.get("tls_context") is None

    @patch.dict("os.environ", {**SMTP_ENV, "SMTP_PORT": "3025", "SMTP_USE_STARTTLS": "true"}, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_env_var_forces_starttls_on(self, mock_send):
        """SMTP_USE_STARTTLS=true forces STARTTLS even on non-587 ports."""
        _run(send_email(to="a@b.com", subject="s", body="b"))
        _, kwargs = mock_send.call_args
        assert kwargs["start_tls"] is True
        assert kwargs.get("tls_context") is not None

    @patch.dict("os.environ", {**SMTP_ENV, "SMTP_PORT": "587", "SMTP_USE_STARTTLS": "false"}, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_env_var_forces_starttls_off(self, mock_send):
        """SMTP_USE_STARTTLS=false disables STARTTLS even on port 587.
        This is an intentionally insecure configuration for testing only."""
        _run(send_email(to="a@b.com", subject="s", body="b"))
        _, kwargs = mock_send.call_args
        assert kwargs["start_tls"] is False
        assert kwargs.get("tls_context") is None

    @patch.dict("os.environ", {**SMTP_ENV, "SMTP_PORT": "587", "SMTP_USE_STARTTLS": "maybe"}, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_invalid_env_var_falls_through_to_port_detection(self, mock_send):
        """Invalid SMTP_USE_STARTTLS value falls through to port-based auto-detection."""
        _run(send_email(to="a@b.com", subject="s", body="b"))
        _, kwargs = mock_send.call_args
        assert kwargs["start_tls"] is True  # port 587 auto-detected

    @patch.dict("os.environ", {**SMTP_ENV, "SMTP_PORT": "587"}, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_tls_context_check_hostname_enabled(self, mock_send):
        """SSLContext should have check_hostname=True for MITM protection."""
        _run(send_email(to="a@b.com", subject="s", body="b"))
        _, kwargs = mock_send.call_args
        assert kwargs["tls_context"].check_hostname is True

    @patch.dict("os.environ", {**SMTP_ENV, "SMTP_PORT": "3025", "SMTP_USER": "user", "SMTP_PASSWORD": "pass"}, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    @patch("src.shared.email_sender.log")
    def test_plaintext_credentials_are_refused(self, mock_log, mock_send):
        """Credentials must never be sent over plaintext SMTP."""
        result = _run(send_email(to="a@b.com", subject="s", body="b"))
        assert result is False
        mock_send.assert_not_awaited()
        mock_log.error.assert_called_once()
        assert "credentials require starttls" in mock_log.error.call_args[0][0].lower()

    @patch.dict(
        "os.environ",
        {
            **SMTP_ENV,
            "SMTP_HOST": "mail.example.com",
            "SMTP_USER": "",
            "SMTP_PASSWORD": "",
        },
        clear=False,
    )
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_external_plaintext_server_is_refused(self, mock_send):
        """Employee email content must not leave over unencrypted SMTP."""
        result = _run(send_email(to="a@b.com", subject="s", body="b"))
        assert result is False
        mock_send.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestReplyHeaders
# ---------------------------------------------------------------------------

class TestReplyHeaders:
    """Tests for In-Reply-To and References header support."""

    @patch.dict("os.environ", SMTP_ENV, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_in_reply_to_header_set(self, mock_send):
        """In-Reply-To header should match the provided message ID."""
        msg_id = "<original-123@ci.laredo.tx.us>"
        _run(send_email(to="a@b.com", subject="Re: s", body="b", reply_to_message_id=msg_id))

        message = mock_send.call_args[0][0]
        assert message["In-Reply-To"] == msg_id

    @patch.dict("os.environ", SMTP_ENV, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_references_header_set(self, mock_send):
        """References header should match the provided message ID."""
        msg_id = "<original-456@ci.laredo.tx.us>"
        _run(send_email(to="a@b.com", subject="Re: s", body="b", reply_to_message_id=msg_id))

        message = mock_send.call_args[0][0]
        assert message["References"] == msg_id

    @patch.dict("os.environ", SMTP_ENV, clear=False)
    @patch("src.shared.email_sender.aiosmtplib.send", new_callable=AsyncMock)
    def test_no_reply_headers_when_none(self, mock_send):
        """When reply_to_message_id is None, no threading headers are set."""
        _run(send_email(to="a@b.com", subject="s", body="b"))

        message = mock_send.call_args[0][0]
        assert message["In-Reply-To"] is None
        assert message["References"] is None


# ---------------------------------------------------------------------------
# TestEmailTemplates
# ---------------------------------------------------------------------------

class TestEmailTemplates:
    """Tests for email template constants."""

    def test_name_mismatch_template_exists(self):
        """NAME_MISMATCH_REJECTION should be a non-empty string."""
        assert isinstance(NAME_MISMATCH_REJECTION, str)
        assert len(NAME_MISMATCH_REJECTION) > 0
        assert "does not appear to be yours" in NAME_MISMATCH_REJECTION
