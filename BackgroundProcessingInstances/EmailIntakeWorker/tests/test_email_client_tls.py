"""Unit tests for IMAP TLS context in email_client.py."""

import ssl
from unittest.mock import patch, MagicMock

from src.email_client import ImapEmailClient


class TestImapTlsContext:
    """Tests for IMAP SSL context handling."""

    # B1: use_ssl=True passes ssl_context with CERT_REQUIRED
    @patch("src.email_client.MailBox")
    def test_ssl_connect_passes_verified_ssl_context(self, mock_mailbox_cls):
        """use_ssl=True should pass ssl_context with CERT_REQUIRED to MailBox."""
        mock_mailbox = MagicMock()
        mock_mailbox_cls.return_value = mock_mailbox
        mock_mailbox.folder.list.return_value = []

        client = ImapEmailClient(
            host="imap.example.com", port=993,
            username="user", password="pass",
            use_ssl=True,
        )
        client.connect()

        call_args = mock_mailbox_cls.call_args
        ctx = call_args.kwargs.get("ssl_context")
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    # B1b: check_hostname is True
    @patch("src.email_client.MailBox")
    def test_ssl_context_check_hostname_enabled(self, mock_mailbox_cls):
        """use_ssl=True should produce ssl_context with check_hostname=True."""
        mock_mailbox = MagicMock()
        mock_mailbox_cls.return_value = mock_mailbox
        mock_mailbox.folder.list.return_value = []

        client = ImapEmailClient(
            host="imap.example.com", port=993,
            username="user", password="pass",
            use_ssl=True,
        )
        client.connect()

        call_args = mock_mailbox_cls.call_args
        ctx = call_args.kwargs.get("ssl_context")
        assert ctx.check_hostname is True

    # B3: use_ssl=False uses MailBoxUnencrypted, no ssl_context
    @patch("src.email_client.MailBoxUnencrypted")
    def test_no_ssl_uses_unencrypted(self, mock_unenc_cls):
        """use_ssl=False should use MailBoxUnencrypted with no ssl_context."""
        mock_mailbox = MagicMock()
        mock_unenc_cls.return_value = mock_mailbox
        mock_mailbox.folder.list.return_value = []

        client = ImapEmailClient(
            host="greenmail", port=3143,
            username="user", password="pass",
            use_ssl=False,
        )
        client.connect()

        mock_unenc_cls.assert_called_once_with("greenmail", 3143)
        call_args = mock_unenc_cls.call_args
        assert "ssl_context" not in (call_args.kwargs or {})
