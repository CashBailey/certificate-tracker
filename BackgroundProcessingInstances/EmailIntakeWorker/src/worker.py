"""
Email Intake Worker main module.

Polls IMAP mailbox for incoming certificate documents and processes them
through the extraction pipeline.
"""

import asyncio
import hashlib
import json
import os
import signal
import time
from datetime import datetime, timezone
from typing import Optional

import magic
import redis

from minio import Minio

from shared.models import (
    CertificateDocument,
    EmailProcessingState,
    IntakeChannel,
)
from shared.orm_models import CertificateDocumentORM, EmailIntakeMessageORM, ExtractionRunORM

from .email_client import (
    ImapEmailClient,
    IncomingEmail,
    EmailAttachment,
    create_email_client_from_env,
)
from .directory_lookup import (
    DirectoryLookup,
    create_directory_lookup_from_env,
    get_session_factory,
)
from .malware_scanner import ClamAVScanner, create_scanner_from_env


# Configure secure logging with automatic redaction
from shared.logging_utils import configure_secure_logging, get_secure_logger

configure_secure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = get_secure_logger(__name__)


# Allowed file types for certificate documents
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
}

# Maximum file size (20MB) - standardized across frontend, API, and workers
MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_FILENAME_LENGTH = 500

# Redis queue for extraction tasks
EXTRACTION_QUEUE = "extraction_tasks"
RETRYABLE_ERROR_PREFIX = "RETRYABLE:"
TERMINAL_EMAIL_STATES = {
    EmailProcessingState.PROCESSED.value,
    EmailProcessingState.QUARANTINED.value,
}


class EmailIntakeWorker:
    """
    Worker that polls IMAP mailbox and processes certificate documents.
    """

    def __init__(
        self,
        email_client: ImapEmailClient,
        directory_lookup: DirectoryLookup,
        minio_client: Minio,
        redis_client: redis.Redis,
        poll_interval: int = 60,
        bucket_name: str = "documents",
        malware_scanner: Optional[ClamAVScanner] = None,
    ):
        """
        Initialize the Email Intake Worker.

        Args:
            email_client: IMAP client for email retrieval
            directory_lookup: Service for email-to-employee mapping
            minio_client: MinIO client for document storage
            redis_client: Redis client for task queue
            poll_interval: Seconds between mailbox polls
            bucket_name: MinIO bucket for storing documents
            malware_scanner: Optional ClamAV scanner for malware detection
        """
        self.email_client = email_client
        self.directory_lookup = directory_lookup
        self.minio_client = minio_client
        self.redis_client = redis_client
        self.poll_interval = poll_interval
        self.bucket_name = bucket_name
        self.malware_scanner = malware_scanner
        self._running = False
        self._session_factory = get_session_factory()

    def _generate_storage_key(
        self,
        filename: str,
        employee_id: int,
        file_hash: str,
    ) -> str:
        """Generate a retry-stable, non-enumerable storage key."""
        ext = os.path.splitext(filename)[1].lower() or ".pdf"
        if ext not in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            ext = ".bin"
        key_seed = f"{employee_id}:{file_hash}".encode()
        object_id = hashlib.sha256(key_seed).hexdigest()
        return f"email-intake/{object_id}{ext}"

    def _compute_file_hash(self, data: bytes) -> str:
        """
        Compute SHA-256 hash of file content for deduplication.

        Args:
            data: File bytes

        Returns:
            64-character hex string of SHA-256 hash
        """
        return hashlib.sha256(data).hexdigest()

    async def _check_duplicate_document(
        self,
        employee_id: int,
        file_hash: str,
    ) -> Optional[CertificateDocument]:
        """
        Check if a document with the same hash already exists for this employee.

        Args:
            employee_id: Employee ID
            file_hash: SHA-256 hash of file content

        Returns:
            Existing document if duplicate found, None otherwise
        """
        async with self._session_factory() as session:
            from sqlalchemy import select, and_
            stmt = select(CertificateDocumentORM).where(
                and_(
                    CertificateDocumentORM.employee_id == employee_id,
                    CertificateDocumentORM.file_hash == file_hash,
                    CertificateDocumentORM.deleted_at.is_(None),
                )
            )
            result = await session.execute(stmt)
            orm_obj = result.scalar_one_or_none()

            if orm_obj:
                return CertificateDocument(
                    id=orm_obj.id,
                    employee_id=orm_obj.employee_id,
                    storage_key=orm_obj.storage_key,
                    file_name=orm_obj.file_name,
                    file_type=orm_obj.file_type,
                    file_size_bytes=orm_obj.file_size_bytes,
                    uploaded_by_id=orm_obj.uploaded_by_id,
                    acting_as=orm_obj.acting_as,
                    intake_channel=IntakeChannel(orm_obj.intake_channel),
                    source_email_message_id=orm_obj.source_email_message_id,
                    file_hash=orm_obj.file_hash,
                    created_at=orm_obj.created_at,
                )
            return None

    def _validate_attachment(
        self,
        attachment: EmailAttachment,
    ) -> Optional[str]:
        """
        Validate attachment is acceptable for processing.

        Checks file size, content type, and scans for malware.

        Args:
            attachment: Attachment to validate

        Returns:
            Error message if invalid, None if valid
        """
        # Check file size
        if attachment.size > MAX_FILE_SIZE:
            return f"File too large: {attachment.size} bytes (max {MAX_FILE_SIZE})"
        if len(attachment.filename) > MAX_FILENAME_LENGTH:
            return f"Filename exceeds {MAX_FILENAME_LENGTH} characters"

        # Detect actual content type using magic
        try:
            detected_type = magic.from_buffer(attachment.payload, mime=True)
        except Exception:
            detected_type = attachment.content_type

        # Check content type
        if detected_type not in ALLOWED_CONTENT_TYPES:
            return f"Invalid file type: {detected_type}"

        # Malware scan if scanner is available
        if self.malware_scanner:
            scan_result = self.malware_scanner.scan_bytes(attachment.payload)
            if not scan_result.is_clean:
                if scan_result.virus_name:
                    logger.warning("Malware detected in email attachment: %s", scan_result.virus_name)
                    return f"Malware detected: {scan_result.virus_name}"
                # Scanner unreachable (not a positive detection) is transient:
                # tag it retryable so the email is left unread and re-scanned
                # next poll instead of being permanently quarantined.
                error_info = scan_result.error or "Unknown scan failure"
                logger.error("Malware scan unavailable for email attachment: %s", error_info)
                return f"{RETRYABLE_ERROR_PREFIX} Scan unavailable: {error_info}"
            elif scan_result.error:
                # Log warning but continue if fail-open resulted in is_clean=True
                logger.warning(f"Malware scan warning: {scan_result.error}")

        return None

    async def _store_document(
        self,
        attachment: EmailAttachment,
        employee_id: int,
        email_message_id: int,
    ) -> tuple[Optional[CertificateDocument], bool]:
        """
        Store document in MinIO and create database record.

        Performs deduplication check before storing - if a document with
        the same content hash already exists for this employee, returns
        the existing document instead.

        Args:
            attachment: Email attachment to store
            employee_id: Employee who sent the document
            email_message_id: Database ID of the email intake message

        Returns:
            Tuple of (CertificateDocument, is_duplicate)
            - CertificateDocument if successful, None on error
            - is_duplicate is True if existing document was returned
        """
        try:
            # Compute file hash for deduplication
            file_hash = self._compute_file_hash(attachment.payload)

            # Check for existing document with same hash
            existing_doc = await self._check_duplicate_document(employee_id, file_hash)
            if existing_doc:
                logger.info(
                    f"Duplicate document detected for employee {employee_id}, "
                    f"returning existing document {existing_doc.id}"
                )
                return existing_doc, True

            # Generate storage key
            storage_key = self._generate_storage_key(
                attachment.filename,
                employee_id,
                file_hash,
            )

            # Detect content type
            try:
                content_type = magic.from_buffer(attachment.payload, mime=True)
            except Exception:
                content_type = attachment.content_type

            # Ensure content type is valid
            if content_type not in ALLOWED_CONTENT_TYPES:
                content_type = "application/pdf"  # Default fallback

            # Upload to MinIO
            from io import BytesIO
            self.minio_client.put_object(
                self.bucket_name,
                storage_key,
                BytesIO(attachment.payload),
                length=attachment.size,
                content_type=content_type,
            )

            logger.info("Stored email document object")

            # Create database record with file hash
            async with self._session_factory() as session:
                doc_orm = CertificateDocumentORM(
                    employee_id=employee_id,
                    storage_key=storage_key,
                    file_name=attachment.filename,
                    file_type=content_type,
                    file_size_bytes=attachment.size,
                    uploaded_by_id=employee_id,  # Self-upload via email
                    acting_as="Self",
                    intake_channel="EMAIL",
                    source_email_message_id=email_message_id,
                    file_hash=file_hash,
                )
                session.add(doc_orm)
                await session.flush()

                # Database defaults force the only state email intake may create:
                # Processing with empty fields and review required. Column-level
                # grants deliberately prevent this parser-facing worker from
                # forging an Approved extraction.
                extraction_orm = ExtractionRunORM(document_id=doc_orm.id)
                session.add(extraction_orm)
                await session.commit()
                await session.refresh(doc_orm)

                return CertificateDocument(
                    id=doc_orm.id,
                    employee_id=doc_orm.employee_id,
                    storage_key=doc_orm.storage_key,
                    file_name=doc_orm.file_name,
                    file_type=doc_orm.file_type,
                    file_size_bytes=doc_orm.file_size_bytes,
                    uploaded_by_id=doc_orm.uploaded_by_id,
                    acting_as=doc_orm.acting_as,
                    intake_channel=IntakeChannel.EMAIL,
                    source_email_message_id=email_message_id,
                    file_hash=file_hash,
                    created_at=doc_orm.created_at,
                ), False

        except Exception as e:
            logger.error(f"Failed to store document: {e}")
            return None, False

    def _queue_extraction_task(self, document_id: int, retries: int = 3) -> bool:
        """Push document to extraction queue with retry for transient Redis errors."""
        task = {
            "document_id": document_id,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "source": "email_intake",
        }
        for attempt in range(1, retries + 1):
            try:
                self.redis_client.rpush(EXTRACTION_QUEUE, json.dumps(task))
                logger.info(f"Queued extraction task for document {document_id}")
                return True
            except redis.RedisError as exc:
                logger.warning(
                    f"Failed to queue extraction task for document {document_id} "
                    f"(attempt {attempt}/{retries}): {exc}"
                )
                if attempt < retries:
                    time.sleep(0.5 * attempt)

        return False

    async def _create_email_record(
        self,
        email: IncomingEmail,
        state: EmailProcessingState,
        employee_id: Optional[int] = None,
        error_reason: Optional[str] = None,
        attachment_hashes: Optional[list[str]] = None,
    ) -> int:
        """
        Create email intake message record in database.

        Args:
            email: The incoming email
            state: Processing state
            employee_id: Resolved employee ID (if known)
            error_reason: Error message if processing failed
            attachment_hashes: List of SHA-256 hashes of attachments (for dedupe)

        Returns the database ID of the created record.
        """
        async with self._session_factory() as session:
            orm_obj = EmailIntakeMessageORM(
                message_id=email.message_id,
                from_address=email.from_address,
                received_at=email.received_date,
                subject=email.subject[:500] if email.subject else None,
                attachment_count=len(email.attachments),
                processing_state=state.value,
                error_reason=error_reason[:500] if error_reason else None,
                employee_id=employee_id,
                attachment_hashes=attachment_hashes or [],
            )
            session.add(orm_obj)
            await session.commit()
            await session.refresh(orm_obj)
            return orm_obj.id

    async def _update_email_record(
        self,
        record_id: int,
        state: EmailProcessingState,
        error_reason: Optional[str] = None,
    ) -> None:
        """Update email intake message record."""
        async with self._session_factory() as session:
            from sqlalchemy import update
            stmt = update(EmailIntakeMessageORM).where(
                EmailIntakeMessageORM.id == record_id
            ).values(
                processing_state=state.value,
                error_reason=error_reason[:500] if error_reason else None,
            )
            await session.execute(stmt)
            await session.commit()

    async def _get_email_record_by_message_id(
        self,
        message_id: str,
    ) -> Optional[EmailIntakeMessageORM]:
        """Fetch existing email record by message ID if present."""
        async with self._session_factory() as session:
            from sqlalchemy import select
            stmt = select(EmailIntakeMessageORM).where(
                EmailIntakeMessageORM.message_id == message_id
            ).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def _check_duplicate_message(self, message_id: str) -> bool:
        """
        Check if message is in a terminal state and should be skipped.

        FAILED records are intentionally excluded so transient failures can be
        retried on the next poll.
        """
        existing = await self._get_email_record_by_message_id(message_id)
        return bool(existing and existing.processing_state in TERMINAL_EMAIL_STATES)

    async def _check_duplicate_message_attachment(
        self,
        message_id: str,
        attachment_hash: str,
        exclude_record_id: Optional[int] = None,
    ) -> bool:
        """
        Check if we've already processed this (message_id, attachment_hash) combo.

        Per WF-01 spec: dedupe key should be (message_id, attachment_hash).
        This prevents reprocessing the same attachment from the same email
        on retries, while still allowing different attachments from the same email.

        Args:
            message_id: Email message ID
            attachment_hash: SHA-256 hash of the attachment
            exclude_record_id: Record ID to exclude (the current email's own record)

        Returns:
            True if this combination has been processed before
        """
        async with self._session_factory() as session:
            from sqlalchemy import select
            # Check if any email_intake_message with this message_id
            # has this attachment_hash in its attachment_hashes array
            stmt = select(EmailIntakeMessageORM.id).where(
                EmailIntakeMessageORM.message_id == message_id,
                EmailIntakeMessageORM.processing_state.in_(tuple(TERMINAL_EMAIL_STATES)),
                # Use JSONB containment operator to check if hash is in array
                EmailIntakeMessageORM.attachment_hashes.contains([attachment_hash])
            )
            if exclude_record_id is not None:
                stmt = stmt.where(EmailIntakeMessageORM.id != exclude_record_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def _create_audit_log(
        self,
        action: str,
        target_type: str,
        target_id: str,
        details: Optional[dict] = None,
        outcome: Optional[str] = None,
    ) -> None:
        """
        Create an audit log entry for system actions.

        Routes through ``shared.audit.audit()`` so secret-key scrubbing and
        actor-type validation are applied uniformly with the other services
        (api, scheduler-worker). Sets ``source_service="email-intake-worker"``
        so the AuditPage service filter can attribute these rows.

        Args:
            action: Action being performed (e.g., "email_intake_processed")
            target_type: Type of target (e.g., "email_intake")
            target_id: ID of the target
            details: Optional additional details (secret keys are scrubbed)
            outcome: Optional outcome ("Success" / "Failure" / "Partial")
        """
        from shared.audit import audit
        from shared.repository import SqlRepository

        async with self._session_factory() as session:
            repo = SqlRepository(session)
            await audit(
                repository=repo,
                action=action,
                target_type=target_type,
                target_id=str(target_id),
                details=details,
                source_service="email-intake-worker",
                outcome=outcome,
            )
            await session.commit()

    async def process_email(self, email: IncomingEmail) -> None:
        """
        Process a single incoming email.

        Per WF-01: Uses composite dedupe key (message_id, attachment_hash) to handle
        email retries correctly. Each attachment is checked individually to allow
        partial reprocessing if new attachments are added to a retry.

        Args:
            email: Email to process
        """
        logger.info(
            "Processing email uid=%s with %d attachment(s)",
            email.uid,
            len(email.attachments),
        )

        # Pre-compute hashes for all attachments for dedupe tracking.
        attachment_hashes = [
            self._compute_file_hash(attachment.payload)
            for attachment in email.attachments
        ]

        existing_record = await self._get_email_record_by_message_id(email.message_id)

        # Message is in terminal state (already handled): keep inbox and DB consistent.
        if existing_record and existing_record.processing_state in TERMINAL_EMAIL_STATES:
            logger.info("Already processed email uid=%s; skipping", email.uid)
            self.email_client.mark_as_processed(email)
            return

        # Look up employee by email
        employee_id, quarantine_reason = await self.directory_lookup.lookup_or_quarantine(
            email.from_address
        )

        if quarantine_reason == "ignore":
            # Non-city, not in GAL, or distribution list — silently skip
            logger.info("Ignoring email uid=%s because sender is not eligible", email.uid)
            self.email_client.mark_as_processed(email)
            return

        if quarantine_reason:
            # Unknown sender - quarantine (reserved for future use)
            logger.warning(f"Quarantining email: {quarantine_reason}")
            if existing_record:
                email_record_id = existing_record.id
                await self._update_email_record(
                    email_record_id,
                    EmailProcessingState.QUARANTINED,
                    error_reason=quarantine_reason,
                )
            else:
                email_record_id = await self._create_email_record(
                    email,
                    EmailProcessingState.QUARANTINED,
                    error_reason=quarantine_reason,
                    attachment_hashes=attachment_hashes,
                )
            # Audit log for quarantined email
            await self._create_audit_log(
                action="email_intake_quarantined",
                target_type="email_intake",
                target_id=str(email_record_id),
                details={
                    "reason": quarantine_reason,
                    "attachment_count": len(email.attachments),
                },
            )
            self.email_client.mark_as_quarantined(email, quarantine_reason)
            return

        # Create or reuse a non-terminal record so retries can continue without
        # violating unique(message_id) constraints.
        if existing_record:
            email_record_id = existing_record.id
            await self._update_email_record(
                email_record_id,
                EmailProcessingState.FAILED,
                error_reason="Retry in progress",
            )
        else:
            email_record_id = await self._create_email_record(
                email,
                EmailProcessingState.FAILED,
                employee_id=employee_id,
                attachment_hashes=attachment_hashes,
            )

        # Process each attachment
        processed_count = 0
        duplicate_count = 0
        skipped_dedupe_count = 0
        errors: list[str] = []
        retryable_error_count = 0

        for i, attachment in enumerate(email.attachments):
            file_hash = attachment_hashes[i]
            attachment_label = f"attachment {i + 1}"

            # Per WF-01: Check composite dedupe (message_id, attachment_hash)
            # This handles retries of the same email with same attachments
            # Exclude current record to avoid self-match
            if await self._check_duplicate_message_attachment(
                email.message_id, file_hash, exclude_record_id=email_record_id
            ):
                logger.info(
                    "%s already processed for email uid=%s",
                    attachment_label,
                    email.uid,
                )
                skipped_dedupe_count += 1
                continue

            # Validate attachment
            validation_error = self._validate_attachment(attachment)
            if validation_error:
                logger.warning(
                    "Skipping %s: %s", attachment_label, validation_error,
                )
                # A retryable validation failure (e.g. scanner unreachable) must
                # keep the email unread for a later retry, not quarantine it.
                if validation_error.startswith(RETRYABLE_ERROR_PREFIX):
                    retryable_error_count += 1
                    errors.append(
                        f"{RETRYABLE_ERROR_PREFIX} {attachment_label}: {validation_error}"
                    )
                else:
                    errors.append(f"{attachment_label}: {validation_error}")
                continue

            # Store document (with employee+hash deduplication check)
            document, is_duplicate = await self._store_document(
                attachment,
                employee_id,
                email_record_id,
            )

            if not document:
                retryable_error_count += 1
                errors.append(
                    f"{RETRYABLE_ERROR_PREFIX} {attachment_label}: Storage failed"
                )
                continue

            if is_duplicate:
                duplicate_count += 1
                logger.info(
                    f"Duplicate document detected for employee {employee_id}, "
                    f"attempting extraction re-queue for document {document.id}"
                )

            if not self._queue_extraction_task(document.id):
                retryable_error_count += 1
                errors.append(
                    f"{RETRYABLE_ERROR_PREFIX} {attachment_label}: "
                    "Failed to queue extraction task"
                )
                continue

            processed_count += 1

        has_retriable_errors = retryable_error_count > 0

        # Transient infra failures: keep email unread for retry.
        if has_retriable_errors:
            await self._update_email_record(
                email_record_id,
                EmailProcessingState.FAILED,
                error_reason="; ".join(errors),
            )
            await self._create_audit_log(
                action="email_intake_retry_scheduled",
                target_type="email_intake",
                target_id=str(email_record_id),
                details={
                    "employee_id": employee_id,
                    "documents_processed": processed_count,
                    "documents_deduplicated": duplicate_count,
                    "attachments_skipped_dedupe": skipped_dedupe_count,
                    "retryable_errors": errors,
                },
            )
            logger.warning(
                f"Leaving email uid={email.uid} unread for retry: "
                f"{retryable_error_count} retryable error(s)"
            )
            return

        # Non-retriable total failure: quarantine.
        if errors and processed_count == 0 and skipped_dedupe_count == 0:
            await self._update_email_record(
                email_record_id,
                EmailProcessingState.FAILED,
                error_reason="; ".join(errors),
            )
            # Audit log for failed email intake
            await self._create_audit_log(
                action="email_intake_failed",
                target_type="email_intake",
                target_id=str(email_record_id),
                details={
                    "employee_id": employee_id,
                    "errors": errors,
                },
            )
            self.email_client.mark_as_quarantined(email, "All attachments failed")
        else:
            await self._update_email_record(
                email_record_id,
                EmailProcessingState.PROCESSED,
            )
            # Audit log for successful email intake
            await self._create_audit_log(
                action="email_intake_processed",
                target_type="email_intake",
                target_id=str(email_record_id),
                details={
                    "employee_id": employee_id,
                    "documents_processed": processed_count,
                    "documents_deduplicated": duplicate_count,
                    "attachments_skipped_dedupe": skipped_dedupe_count,
                    "errors": errors,
                    "attachment_count": len(email.attachments),
                },
            )
            # Mark as processed in IMAP
            self.email_client.mark_as_processed(email)
            logger.info(
                f"Processed email uid={email.uid}: "
                f"{processed_count} documents queued, {skipped_dedupe_count} skipped (dedupe)"
            )

    async def poll_once(self) -> int:
        """
        Poll mailbox once and process all new emails.

        Returns:
            Number of emails processed
        """
        count = 0
        try:
            for email in self.email_client.fetch_unread_emails():
                await self.process_email(email)
                count += 1
        except Exception as e:
            logger.error(f"Error during polling: {e}")
            raise

        return count

    async def run(self) -> None:
        """Run the worker loop."""
        self._running = True
        logger.info("Email Intake Worker starting...")

        # Exponential backoff state for reconnect failures
        _BACKOFF_BASE_SECONDS: float = 30.0
        _BACKOFF_MAX_SECONDS: float = 300.0
        consecutive_failures: int = 0

        # Connect to email server. The IMAP host may be unresolvable or down
        # at startup (mail server restarting, dev stack without greenmail), so
        # retry with the same capped backoff used for mid-run reconnects
        # instead of crashing into a container restart loop.
        while self._running:
            try:
                self.email_client.connect()
                consecutive_failures = 0
                break
            except Exception as e:
                consecutive_failures += 1
                backoff_seconds = min(
                    _BACKOFF_BASE_SECONDS * (2 ** (consecutive_failures - 1)),
                    _BACKOFF_MAX_SECONDS,
                )
                logger.error(
                    f"Initial IMAP connection failed ({e}). "
                    f"Retry #{consecutive_failures} in {backoff_seconds:.0f}s..."
                )
                await asyncio.sleep(backoff_seconds)

        try:
            while self._running:
                try:
                    processed = await self.poll_once()
                    if processed > 0:
                        logger.info(f"Processed {processed} emails")

                    # Successful poll — reset failure counter
                    consecutive_failures = 0

                except Exception as e:
                    logger.error(f"Error in poll cycle: {e}")
                    consecutive_failures += 1

                    # Compute backoff delay before reconnect attempt
                    backoff_seconds = min(
                        _BACKOFF_BASE_SECONDS * (2 ** (consecutive_failures - 1)),
                        _BACKOFF_MAX_SECONDS,
                    )
                    logger.warning(
                        f"Poll cycle failure #{consecutive_failures}. "
                        f"Waiting {backoff_seconds:.0f}s before reconnect..."
                    )
                    await asyncio.sleep(backoff_seconds)

                    # Reconnect on error
                    try:
                        self.email_client.disconnect()
                        self.email_client.connect()
                        logger.info("Reconnected to IMAP server successfully")
                    except Exception as reconnect_error:
                        logger.error(f"Failed to reconnect: {reconnect_error}")
                    continue

                # Wait before next poll, sending NOOP keepalives to
                # prevent the IMAP server from dropping idle connections.
                keepalive_interval = 15  # seconds
                elapsed = 0
                while elapsed < self.poll_interval and self._running:
                    wait = min(keepalive_interval, self.poll_interval - elapsed)
                    await asyncio.sleep(wait)
                    elapsed += wait
                    if elapsed < self.poll_interval and self._running:
                        try:
                            self.email_client.noop()
                        except Exception:
                            break  # connection lost; next poll will reconnect

        finally:
            self.email_client.disconnect()
            logger.info("Email Intake Worker stopped")

    def stop(self) -> None:
        """Signal the worker to stop."""
        logger.info("Stopping Email Intake Worker...")
        self._running = False


def create_worker_from_env() -> EmailIntakeWorker:
    """Create worker instance from environment variables."""
    # Email client
    email_client = create_email_client_from_env()

    # Directory lookup
    directory_lookup = create_directory_lookup_from_env()

    # MinIO client (with mTLS when TLS_ENABLED=true)
    minio_endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000")
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY")
    if not minio_access_key or not minio_secret_key:
        raise RuntimeError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY environment variables are required")

    minio_secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"
    if minio_secure and os.environ.get("TLS_ENABLED", "false").lower() == "true":
        import urllib3 as _urllib3
        ca_cert = os.environ.get("TLS_CA_CERT", "/tls/ca.crt")
        client_cert = os.environ.get("TLS_CLIENT_CERT", "/tls/client.crt")
        client_key = os.environ.get("TLS_CLIENT_KEY", "/tls/client.key")
        _http_client = _urllib3.PoolManager(
            cert_reqs="CERT_REQUIRED",
            ca_certs=ca_cert,
            cert_file=client_cert,
            key_file=client_key,
        )
        minio_client = Minio(
            minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=True,
            http_client=_http_client,
        )
    else:
        minio_client = Minio(
            minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure,
        )

    # Redis client (with mTLS when TLS_ENABLED=true)
    from shared.tls import redis_tls_kwargs
    redis_client = redis.from_url(
        os.environ.get("REDIS_URL", "rediss://redis:6380/0"),
        **redis_tls_kwargs(),
    )

    # Poll interval
    poll_interval = int(os.environ.get("EMAIL_POLL_INTERVAL_SECONDS", "60"))

    # Bucket name
    bucket_name = os.environ.get("MINIO_BUCKET", "documents")

    # Malware scanner (optional)
    malware_scanner = create_scanner_from_env()
    if malware_scanner:
        logger.info("ClamAV malware scanning enabled")
    else:
        logger.info("ClamAV malware scanning disabled")

    return EmailIntakeWorker(
        email_client=email_client,
        directory_lookup=directory_lookup,
        minio_client=minio_client,
        redis_client=redis_client,
        poll_interval=poll_interval,
        bucket_name=bucket_name,
        malware_scanner=malware_scanner,
    )


def main():
    """Main entry point."""
    worker = create_worker_from_env()

    # Handle shutdown signals
    def signal_handler(signum, frame):
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the worker
    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
