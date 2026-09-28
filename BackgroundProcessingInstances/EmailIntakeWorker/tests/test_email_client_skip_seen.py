"""Attachment-less emails must be flagged \\Seen so they stop clogging the poll."""

from unittest.mock import MagicMock

from src.email_client import MAX_MESSAGE_ID_LENGTH, ImapEmailClient


def _msg(uid, subject, attachments):
    msg = MagicMock()
    msg.uid = uid
    msg.subject = subject
    msg.attachments = attachments
    msg.headers = {"message-id": [f"<{uid}@test>"]}
    msg.from_ = "employee@ci.laredo.tx.us"
    msg.date = None
    return msg


def _attachment():
    att = MagicMock()
    att.filename = "cert.pdf"
    att.content_type = "application/pdf"
    att.payload = b"%PDF-1.4 fake"
    return att


def _client_with_messages(messages):
    client = ImapEmailClient(host="h", port=143, username="u", password="p", use_ssl=False)
    mailbox = MagicMock()
    mailbox.fetch.side_effect = [iter([]), iter(messages)]
    client._mailbox = mailbox
    return client, mailbox


def test_attachmentless_emails_are_flagged_seen_after_fetch():
    messages = [
        _msg("101", "No attachment", []),
        _msg("102", "Has cert", [_attachment()]),
        _msg("103", "Also empty", []),
    ]
    client, mailbox = _client_with_messages(messages)

    yielded = list(client.fetch_unread_emails())

    # Only the email with an attachment is yielded for processing.
    assert [e.uid for e in yielded] == ["102"]
    # Both attachment-less UIDs are marked seen exactly once, in one call.
    mailbox.flag.assert_called_once_with(["101", "103"], ["\\Seen"], True)


def test_no_flag_call_when_every_email_has_attachments():
    messages = [_msg("201", "Cert", [_attachment()])]
    client, mailbox = _client_with_messages(messages)

    list(client.fetch_unread_emails())

    mailbox.flag.assert_not_called()


def test_flag_failure_does_not_break_polling():
    messages = [_msg("301", "Empty", [])]
    client, mailbox = _client_with_messages(messages)
    mailbox.flag.side_effect = RuntimeError("IMAP hiccup")

    # Should not raise despite the flag failure.
    assert list(client.fetch_unread_emails()) == []


def test_oversized_messages_are_quarantined_without_fetching_bodies():
    oversized = _msg("401", "Huge", [])
    client, mailbox = _client_with_messages([])
    mailbox.fetch.side_effect = [iter([oversized]), iter([])]

    assert list(client.fetch_unread_emails()) == []

    assert mailbox.fetch.call_args_list[0].kwargs["headers_only"] is True
    mailbox.move.assert_called_once_with(["401"], "Quarantine")


def test_oversized_message_id_uses_bounded_uid_fallback():
    message = _msg("501", "Certificate", [_attachment()])
    message.headers = {"message-id": ["<" + "x" * MAX_MESSAGE_ID_LENGTH + ">"]}
    client, _ = _client_with_messages([message])

    yielded = list(client.fetch_unread_emails())

    assert yielded[0].message_id == "imap-uid:501"


def test_attachment_payload_total_is_quarantined():
    message = _msg("601", "Too much", [_attachment(), _attachment()])
    for attachment in message.attachments:
        attachment.payload = b"x" * (11 * 1024 * 1024)
    client, mailbox = _client_with_messages([message])

    assert list(client.fetch_unread_emails()) == []

    mailbox.move.assert_called_once_with(["601"], "Quarantine")
