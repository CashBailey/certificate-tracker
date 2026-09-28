"""
IMAP email client for the Email Intake Worker.

Handles connection to IMAP mailbox and retrieval of emails with attachments.
"""

import logging
import os
import ssl
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Optional

from imap_tools import MailBox, AND, MailMessage
from imap_tools.mailbox import MailBoxUnencrypted


logger = logging.getLogger(__name__)

MAX_MESSAGE_SIZE = 25 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_ATTACHMENT_COUNT = 10
MAX_MESSAGE_ID_LENGTH = 255
MAX_FROM_ADDRESS_LENGTH = 255


@dataclass
class EmailAttachment:
    """Represents an email attachment."""
    filename: str
    content_type: str
    payload: bytes
    size: int


@dataclass
class IncomingEmail:
    """Represents an incoming email with attachments."""
    message_id: str
    from_address: str
    subject: str
    received_date: datetime
    attachments: list[EmailAttachment]
    uid: str  # IMAP UID for marking as processed


class ImapEmailClient:
    """IMAP client for polling email inbox."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
        inbox_folder: str = "INBOX",
        processed_folder: str = "Processed",
    ):
        """
        Initialize IMAP client.

        Args:
            host: IMAP server hostname
            port: IMAP server port
            username: IMAP username
            password: IMAP password
            use_ssl: Whether to use SSL/TLS
            inbox_folder: Folder to poll for new emails
            processed_folder: Folder to move processed emails to
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.inbox_folder = inbox_folder
        self.processed_folder = processed_folder
        self._mailbox: Optional[MailBox] = None

    def connect(self) -> None:
        """Connect to the IMAP server."""
        try:
            if self.use_ssl:
                ctx = ssl.create_default_context()
                self._mailbox = MailBox(self.host, self.port, ssl_context=ctx)
            else:
                self._mailbox = MailBoxUnencrypted(self.host, self.port)

            self._mailbox.login(self.username, self.password, self.inbox_folder)
            logger.info(f"Connected to IMAP server {self.host}")

            # Ensure processed folder exists
            self._ensure_folder_exists(self.processed_folder)

        except Exception as e:
            logger.error(f"Failed to connect to IMAP server: {e}")
            raise

    def noop(self) -> None:
        """Send IMAP NOOP to keep the connection alive."""
        if self._mailbox:
            self._mailbox.client.noop()

    def disconnect(self) -> None:
        """Disconnect from the IMAP server."""
        if self._mailbox:
            try:
                self._mailbox.logout()
                logger.info("Disconnected from IMAP server")
            except Exception as e:
                logger.warning(f"Error disconnecting from IMAP: {e}")
            finally:
                self._mailbox = None

    def _ensure_folder_exists(self, folder_name: str) -> None:
        """Create folder if it doesn't exist."""
        if not self._mailbox:
            return

        try:
            folders = self._mailbox.folder.list()
            folder_names = [f.name for f in folders]
            if folder_name not in folder_names:
                self._mailbox.folder.create(folder_name)
                logger.info(f"Created folder: {folder_name}")
        except Exception as e:
            logger.warning(f"Could not ensure folder exists: {e}")

    def fetch_unread_emails(
        self,
        limit: int = 50,
    ) -> Iterator[IncomingEmail]:
        """
        Fetch unread emails from inbox.

        Args:
            limit: Maximum number of emails to fetch

        Yields:
            IncomingEmail objects for each unread email with attachments
        """
        if not self._mailbox:
            raise RuntimeError("Not connected to IMAP server")

        # UIDs of attachment-less emails to mark \Seen after the fetch completes.
        # Flagging is deferred (not done mid-fetch) to avoid desyncing the IMAP
        # FETCH response stream. Without this, attachment-less mail stays unread
        # forever and, once `limit` such emails accumulate, starves the poll of
        # all real submissions.
        skipped_uids: list[str] = []
        quarantined_uids: list[str] = []

        try:
            # Quarantine oversized messages from headers-only fetches so MIME
            # payloads never need to be materialized in worker memory.
            oversized = self._mailbox.fetch(
                AND(seen=False, size_gt=MAX_MESSAGE_SIZE - 1),
                limit=limit,
                mark_seen=False,
                headers_only=True,
            )
            oversized_uids = [message.uid for message in oversized if message.uid]
            if oversized_uids:
                self._move_to_quarantine(oversized_uids, "message exceeds size limit")

            # Fetch unread messages with attachments
            messages = self._mailbox.fetch(
                AND(seen=False, size_lt=MAX_MESSAGE_SIZE),
                limit=limit,
                mark_seen=False,  # Don't mark as seen until processed
            )

            for msg in messages:
                # Skip emails without attachments
                if not msg.attachments:
                    logger.debug("Skipping attachment-less email uid=%s", msg.uid)
                    if msg.uid:
                        skipped_uids.append(msg.uid)
                    continue

                total_attachment_bytes = sum(len(att.payload) for att in msg.attachments)
                if (
                    len(msg.attachments) > MAX_ATTACHMENT_COUNT
                    or total_attachment_bytes > MAX_ATTACHMENT_BYTES
                    or len(msg.from_ or "") > MAX_FROM_ADDRESS_LENGTH
                ):
                    if msg.uid:
                        quarantined_uids.append(msg.uid)
                    continue

                # Convert attachments
                attachments = []
                for att in msg.attachments:
                    attachments.append(EmailAttachment(
                        filename=att.filename or "unnamed",
                        content_type=att.content_type or "application/octet-stream",
                        payload=att.payload,
                        size=len(att.payload),
                    ))

                message_id = self._safe_message_id(msg)

                yield IncomingEmail(
                    message_id=message_id,
                    from_address=msg.from_ or "",
                    subject=msg.subject or "(No subject)",
                    received_date=msg.date or datetime.now(),
                    attachments=attachments,
                    uid=msg.uid,
                )

            # Mark attachment-less mail seen so it stops matching seen=False.
            if skipped_uids:
                try:
                    self._mailbox.flag(skipped_uids, ['\\Seen'], True)
                    logger.info(f"Marked {len(skipped_uids)} attachment-less email(s) as seen")
                except Exception as flag_error:
                    logger.warning(f"Could not mark attachment-less emails seen: {flag_error}")

            if quarantined_uids:
                self._move_to_quarantine(
                    quarantined_uids,
                    "attachment count, payload size, or sender metadata exceeds limit",
                )

        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            raise

    @staticmethod
    def _safe_message_id(message: MailMessage) -> str:
        """Return a stable database-safe message identifier."""
        header = message.headers.get("message-id")
        value = header[0] if isinstance(header, list) and header else header
        value = str(value).strip() if value else ""
        if value and len(value) <= MAX_MESSAGE_ID_LENGTH:
            return value
        logger.warning(
            "Email uid=%s has a missing or oversized Message-ID; using IMAP UID",
            message.uid,
        )
        return f"imap-uid:{message.uid}"[:MAX_MESSAGE_ID_LENGTH]

    def _move_to_quarantine(self, uids: list[str], reason: str) -> None:
        """Move bounded-invalid messages after a fetch stream is exhausted."""
        if not self._mailbox or not uids:
            return
        quarantine_folder = "Quarantine"
        self._ensure_folder_exists(quarantine_folder)
        try:
            self._mailbox.move(uids, quarantine_folder)
            logger.warning("Quarantined %d email(s): %s", len(uids), reason)
        except Exception as exc:
            logger.error("Could not quarantine bounded-invalid email(s): %s", exc)
            try:
                self._mailbox.flag(uids, ["\\Seen"], True)
            except Exception as flag_error:
                logger.error("Could not mark bounded-invalid email(s) seen: %s", flag_error)

    def mark_as_processed(self, email: IncomingEmail) -> None:
        """
        Mark email as processed by moving to processed folder.

        Args:
            email: The email to mark as processed
        """
        if not self._mailbox:
            raise RuntimeError("Not connected to IMAP server")

        try:
            # Move to processed folder
            self._mailbox.move([email.uid], self.processed_folder)
            logger.debug("Moved email uid=%s to processed folder", email.uid)
        except Exception as e:
            logger.warning(f"Could not move email to processed folder: {e}")
            # Fallback: just mark as seen
            try:
                self._mailbox.flag([email.uid], ['\\Seen'], True)
            except Exception as e2:
                logger.error(f"Could not mark email as seen: {e2}")

    def mark_as_quarantined(self, email: IncomingEmail, reason: str) -> None:
        """
        Mark email as quarantined (for emails that couldn't be processed).

        Args:
            email: The email to quarantine
            reason: Reason for quarantine
        """
        if not self._mailbox:
            raise RuntimeError("Not connected to IMAP server")

        # Ensure quarantine folder exists
        quarantine_folder = "Quarantine"
        self._ensure_folder_exists(quarantine_folder)

        try:
            self._mailbox.move([email.uid], quarantine_folder)
            logger.warning("Quarantined email uid=%s: %s", email.uid, reason)
        except Exception as e:
            logger.error(f"Could not quarantine email: {e}")
            # Mark as seen to avoid reprocessing
            try:
                self._mailbox.flag([email.uid], ['\\Seen'], True)
            except Exception as e2:
                logger.error(f"Could not mark quarantined email as seen: {e2}")


def create_email_client_from_env() -> ImapEmailClient:
    """Create an IMAP client from environment variables."""
    return ImapEmailClient(
        host=os.environ.get("IMAP_HOST", "localhost"),
        port=int(os.environ.get("IMAP_PORT", "993")),
        username=os.environ.get("IMAP_USER", ""),
        password=os.environ.get("IMAP_PASSWORD", ""),
        use_ssl=os.environ.get("IMAP_USE_SSL", "true").lower() == "true",
        inbox_folder=os.environ.get("IMAP_INBOX_FOLDER", "INBOX"),
        processed_folder=os.environ.get("IMAP_PROCESSED_FOLDER", "Processed"),
    )
