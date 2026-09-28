"""
City of Laredo - Extraction Worker

Handles document processing, template detection, and field extraction.
Pulls tasks from Redis queue and persists results to database.
"""

import asyncio
import json
import os
import signal
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import logging
import redis
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Configure logging
_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(format="%(message)s", stream=sys.stderr, level=_log_level)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger(__name__)

EXTRACTION_QUEUE = "extraction_tasks"
EXTRACTION_DLQ = "extraction_tasks:dead_letter"
EXTRACTION_PROCESSING_QUEUE_PREFIX = "extraction_tasks:processing"
EXTRACTION_ACTIVE_WORKERS_KEY = f"{EXTRACTION_QUEUE}:workers:active"
EXTRACTION_HEARTBEAT_KEY_PREFIX = f"{EXTRACTION_QUEUE}:workers:heartbeat"
EXTRACTION_RECOVERY_LOCK_KEY = f"{EXTRACTION_QUEUE}:recovery:lock"
EXTRACTION_MAX_RETRIES = int(os.getenv("EXTRACTION_MAX_RETRIES", "3"))
# Backoff before re-queueing a failed task. Without a delay, the BLMOVE claim
# loop re-processes the task within milliseconds, so a seconds-long DB/MinIO
# blip exhausts every retry and strands the document in 'Processing'.
EXTRACTION_RETRY_BACKOFF_MAX_SEC = int(os.getenv("EXTRACTION_RETRY_BACKOFF_MAX_SEC", "30"))
WORKER_HEARTBEAT_INTERVAL_SEC = float(os.getenv("WORKER_HEARTBEAT_INTERVAL_SEC", "10"))
WORKER_HEARTBEAT_TTL_SEC = int(os.getenv("WORKER_HEARTBEAT_TTL_SEC", "30"))
WORKER_RECOVERY_LOCK_TTL_SEC = int(os.getenv("WORKER_RECOVERY_LOCK_TTL_SEC", "15"))
WORKER_STALE_SCAN_INTERVAL_SEC = float(os.getenv("WORKER_STALE_SCAN_INTERVAL_SEC", "30"))
OCR_REQUEST_TIMEOUT_SECONDS = 60.0

ACK_AND_PUSH_LUA = """
local removed = redis.call('LREM', KEYS[1], 1, ARGV[1])
if removed > 0 then
  redis.call('RPUSH', KEYS[2], ARGV[2])
end
return removed
"""

# Graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global shutdown_requested
    log.info("Shutdown signal received", signal=signum)
    shutdown_requested = True


class ExtractionWorker:
    """Extraction worker that processes document extraction tasks."""

    def __init__(
        self,
        redis_url: str,
        database_url: str,
        templates_dir: str,
        worker_id: str | None = None,
    ):
        """
        Initialize the extraction worker.

        Args:
            redis_url: Redis connection URL
            database_url: Database connection URL
            templates_dir: Path to templates directory
        """
        self.redis_url = redis_url
        self.database_url = database_url
        self.templates_dir = templates_dir
        self.max_retries = EXTRACTION_MAX_RETRIES
        self.worker_id = worker_id or os.getenv("WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
        self.processing_queue = self._processing_queue_for_worker(self.worker_id)
        self.heartbeat_interval_sec = WORKER_HEARTBEAT_INTERVAL_SEC
        self.heartbeat_ttl_sec = WORKER_HEARTBEAT_TTL_SEC
        self.recovery_lock_ttl_sec = WORKER_RECOVERY_LOCK_TTL_SEC
        self.stale_scan_interval_sec = WORKER_STALE_SCAN_INTERVAL_SEC
        if self.heartbeat_ttl_sec <= self.heartbeat_interval_sec * 2:
            raise ValueError(
                "WORKER_HEARTBEAT_TTL_SEC must be greater than 2x WORKER_HEARTBEAT_INTERVAL_SEC"
            )

        # Redis client
        self.redis_client: Optional[redis.Redis] = None

        # Database engine and session factory
        self.engine = None
        self.async_session_factory = None

        # Pipeline will be initialized with templates
        self.pipeline = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._next_stale_recovery_at = time.monotonic() + self.stale_scan_interval_sec

    @staticmethod
    def _processing_queue_for_worker(worker_id: str) -> str:
        return f"{EXTRACTION_PROCESSING_QUEUE_PREFIX}:{worker_id}"

    @staticmethod
    def _heartbeat_key_for_worker(worker_id: str) -> str:
        return f"{EXTRACTION_HEARTBEAT_KEY_PREFIX}:{worker_id}"

    @staticmethod
    def _decode_member(member: bytes | str) -> str:
        if isinstance(member, bytes):
            return member.decode("utf-8")
        return member

    def _ensure_blmove_support(self) -> None:
        """Require Redis support for BLMOVE (Redis >= 6.2)."""
        try:
            info = self.redis_client.execute_command("COMMAND", "INFO", "BLMOVE")
        except redis.RedisError:
            info = None

        if info and isinstance(info, list) and info[0] is not None:
            return

        probe_src = "__laredo:probe:blmove:src"
        probe_dst = "__laredo:probe:blmove:dst"
        try:
            self.redis_client.execute_command(
                "BLMOVE",
                probe_src,
                probe_dst,
                "LEFT",
                "RIGHT",
                0.001,
            )
            return
        except redis.ResponseError as exc:
            message = str(exc).lower()
            if "unknown command" in message and "blmove" in message:
                raise RuntimeError(
                    "Redis server does not support BLMOVE; Redis >= 6.2 is required"
                ) from exc
            raise RuntimeError(f"BLMOVE capability check failed: {exc}") from exc

    def _register_worker_presence(self) -> None:
        """Refresh heartbeat and keep worker registered as active."""
        heartbeat_key = self._heartbeat_key_for_worker(self.worker_id)
        self.redis_client.setex(heartbeat_key, self.heartbeat_ttl_sec, "1")
        self.redis_client.sadd(EXTRACTION_ACTIVE_WORKERS_KEY, self.worker_id)

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(self.heartbeat_interval_sec):
            try:
                self._register_worker_presence()
            except Exception as exc:
                log.warning(
                    "Failed to refresh extraction worker heartbeat",
                    worker_id=self.worker_id,
                    error=str(exc),
                )

    def _start_heartbeat(self) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._register_worker_presence()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"extraction-heartbeat-{self.worker_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2)
        self._heartbeat_thread = None
        if not self.redis_client:
            return
        try:
            self.redis_client.delete(self._heartbeat_key_for_worker(self.worker_id))
            self.redis_client.srem(EXTRACTION_ACTIVE_WORKERS_KEY, self.worker_id)
        except Exception:
            # Best-effort cleanup only.
            pass

    def _acquire_recovery_lock(self) -> bool:
        acquired = self.redis_client.set(
            EXTRACTION_RECOVERY_LOCK_KEY,
            self.worker_id,
            nx=True,
            ex=self.recovery_lock_ttl_sec,
        )
        return bool(acquired)

    def _release_recovery_lock(self) -> None:
        try:
            owner = self.redis_client.get(EXTRACTION_RECOVERY_LOCK_KEY)
            if owner is None:
                return
            if self._decode_member(owner) == self.worker_id:
                self.redis_client.delete(EXTRACTION_RECOVERY_LOCK_KEY)
        except Exception:
            pass

    async def initialize(self):
        """Initialize connections and pipeline."""
        # Connect to Redis (with mTLS when TLS_ENABLED=true)
        from shared.tls import redis_tls_kwargs
        self.redis_client = redis.from_url(self.redis_url, **redis_tls_kwargs())
        self.redis_client.ping()
        self._ensure_blmove_support()
        log.info(
            "Connected to Redis",
            worker_id=self.worker_id,
            processing_queue=self.processing_queue,
        )

        # Connect to database (with mTLS when TLS_ENABLED=true)
        db_url = self.database_url
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        from shared.tls import build_ssl_context
        ssl_ctx = build_ssl_context()
        self.engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={"ssl": ssl_ctx} if ssl_ctx else {},
        )
        self.async_session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        log.info("Connected to database")

        # Initialize OCR client
        from .ocr_client import RedisOcrClient
        self.ocr_client = RedisOcrClient(
            self.redis_client,
            timeout=OCR_REQUEST_TIMEOUT_SECONDS,
        )
        log.info("OCR client initialized")

        # Initialize pipeline with OCR client
        from .pipeline import ExtractionPipeline
        self.pipeline = ExtractionPipeline(
            templates_dir=self.templates_dir,
            ocr_client=self.ocr_client,
        )
        log.info("Extraction pipeline initialized")

        self._start_heartbeat()
        # Recover own abandoned queue first, then stale workers.
        self.recover_inflight_tasks()
        self.recover_stale_worker_tasks()

    async def shutdown(self):
        """Cleanup resources."""
        self._stop_heartbeat()
        if self.engine:
            await self.engine.dispose()
        log.info("Worker shutdown complete")

    def _claim_task(self, timeout: int = 5) -> Optional[bytes]:
        """
        Atomically move one task from main queue to processing queue.
        """
        try:
            task = self.redis_client.execute_command(
                "BLMOVE",
                EXTRACTION_QUEUE,
                self.processing_queue,
                "LEFT",
                "RIGHT",
                timeout,
            )
            if isinstance(task, str):
                return task.encode("utf-8")
            return task
        except redis.ResponseError as exc:
            message = str(exc).lower()
            if "unknown command" in message and "blmove" in message:
                raise RuntimeError(
                    "Redis server does not support BLMOVE; Redis >= 6.2 is required"
                ) from exc
            raise

    def _ack_task(self, task_json: bytes) -> bool:
        """Acknowledge a task by removing it from processing queue."""
        removed = self.redis_client.lrem(self.processing_queue, 1, task_json)
        if removed == 0:
            log.warning(
                "Task not found in processing queue during ack",
                processing_queue=self.processing_queue,
                worker_id=self.worker_id,
            )
            return False
        return True

    def _ack_and_push(self, task_json: bytes, destination_queue: str, payload: str) -> bool:
        """
        Atomically ack a processing task and push replacement payload to destination queue.

        Returns True when task was present in processing queue and destination push occurred.
        """
        removed = self.redis_client.eval(
            ACK_AND_PUSH_LUA,
            2,
            self.processing_queue,
            destination_queue,
            task_json,
            payload,
        )
        return int(removed) > 0

    def recover_inflight_tasks(self, worker_id: str | None = None) -> int:
        """
        Move tasks from one worker-owned processing queue back to main queue.
        """
        owner_id = worker_id or self.worker_id
        processing_queue = self._processing_queue_for_worker(owner_id)
        recovered = 0
        while True:
            moved = self.redis_client.rpoplpush(
                processing_queue,
                EXTRACTION_QUEUE,
            )
            if not moved:
                break
            recovered += 1

        if recovered:
            log.warning(
                "Recovered extraction tasks from processing queue",
                recovered_count=recovered,
                owner_worker_id=owner_id,
                source_queue=processing_queue,
                destination_queue=EXTRACTION_QUEUE,
            )
        return recovered

    def recover_stale_worker_tasks(self) -> int:
        """
        Recover tasks from workers whose heartbeat has expired.
        """
        if not self._acquire_recovery_lock():
            return 0

        total_recovered = 0
        try:
            members = self.redis_client.smembers(EXTRACTION_ACTIVE_WORKERS_KEY)
            for member in list(members):
                candidate = self._decode_member(member)
                if candidate == self.worker_id:
                    continue
                if self.redis_client.exists(self._heartbeat_key_for_worker(candidate)):
                    continue
                recovered = self.recover_inflight_tasks(worker_id=candidate)
                total_recovered += recovered
                self.redis_client.srem(EXTRACTION_ACTIVE_WORKERS_KEY, candidate)
                log.warning(
                    "Recovered stale extraction worker queue",
                    stale_worker_id=candidate,
                    recovered_count=recovered,
                )
        finally:
            self._release_recovery_lock()

        return total_recovered

    def _maybe_recover_stale_workers(self) -> None:
        now = time.monotonic()
        if now < self._next_stale_recovery_at:
            return
        self._next_stale_recovery_at = now + self.stale_scan_interval_sec
        try:
            self.recover_stale_worker_tasks()
        except Exception as exc:
            log.warning(
                "Failed stale extraction worker recovery pass",
                worker_id=self.worker_id,
                error=str(exc),
            )

    async def _record_document_limit(self, document_id: int, reason: str) -> None:
        """Route a bounded-invalid document to human review without retry churn."""
        from shared.models import ReviewState
        from shared.repository import SqlRepository

        async with self.async_session_factory() as session:
            repo = SqlRepository(session)
            extraction = await repo.get_extraction_by_document_id(document_id)
            if not extraction or extraction.review_state != ReviewState.PROCESSING:
                return
            updated = await repo.update_extraction_results(
                extraction_id=extraction.id,
                extracted_fields={},
                needs_review=True,
                needs_review_reasons=[f"DOCUMENT_LIMIT_EXCEEDED: {reason[:300]}"],
                expected_state=ReviewState.PROCESSING,
                expected_version=extraction.review_state_version,
                new_state=ReviewState.PENDING_REVIEW,
            )
            if updated:
                await session.commit()
            else:
                await session.rollback()

    async def process_task(self, task_data: dict) -> bool:
        """
        Process a single extraction task.

        Args:
            task_data: Task data containing document_id

        Returns:
            True when task is fully handled (success or non-retriable skip),
            False when task should be retried.
        """
        document_id = task_data.get("document_id")
        if not document_id:
            log.error("Task missing document_id", task=task_data)
            return True

        log.info("Processing extraction task", document_id=document_id)

        try:
            async with self.async_session_factory() as session:
                from shared.repository import SqlRepository
                from shared.storage import MinioStorageClient
                from .name_matcher import check_name_mismatch

                repo = SqlRepository(session)
                storage = MinioStorageClient()

                # Get document record
                document = await repo.get_document_by_id(document_id)
                if not document:
                    log.error("Document not found", document_id=document_id)
                    return True

                # Get employee info for name matching
                employee = await repo.get_employee_by_id(document.employee_id)
                if not employee:
                    log.warning(
                        "Employee not found for document",
                        document_id=document_id,
                        employee_id=document.employee_id,
                    )

                # Get existing extraction record (created by API during upload)
                existing_extraction = await repo.get_extraction_by_document_id(document_id)
                if not existing_extraction:
                    log.error("Extraction record not found", document_id=document_id)
                    return True

                # SM-01: Only process extractions that are in Processing state
                from shared.models import ReviewState
                if existing_extraction.review_state != ReviewState.PROCESSING:
                    log.warning(
                        "Extraction not in Processing state, skipping",
                        document_id=document_id,
                        extraction_id=existing_extraction.id,
                        current_state=existing_extraction.review_state.value,
                    )
                    return True

                # Fetch file from storage
                file_bytes = await storage.get(document.storage_key)

                # Run extraction pipeline
                extraction = await self.pipeline.run_extraction(
                    document_id=document_id,
                    file_bytes=file_bytes,
                    file_type=document.file_type,
                )

                # Check for name mismatch between certificate holder and employee
                needs_review_reasons = list(extraction.needs_review_reasons)
                needs_review = extraction.needs_review
                name_mismatch_detected = False

                if employee:
                    mismatch_reason = check_name_mismatch(
                        extracted_fields=extraction.extracted_fields,
                        employee_first_name=employee.first_name,
                        employee_last_name=employee.last_name,
                    )
                    if mismatch_reason:
                        from shared.models import IntakeChannel
                        if document.intake_channel == IntakeChannel.MANUAL_UPLOAD:
                            # Coordinator uploaded manually — bypass name mismatch
                            log.info(
                                "Name mismatch bypassed (manual upload by Coordinator)",
                                document_id=document_id,
                                reason=mismatch_reason,
                            )
                        elif document.intake_channel == IntakeChannel.EMAIL:
                            # Email submission — auto-reject with reply email
                            log.warning(
                                "Name mismatch auto-rejected (email intake)",
                                document_id=document_id,
                                employee_id=employee.id,
                                reason=mismatch_reason,
                            )
                            name_mismatch_detected = True

                            email_msg = None
                            if document.source_email_message_id:
                                email_msg = await repo.get_email_intake_message_by_id(
                                    document.source_email_message_id
                                )

                            # Persist evidence and rejection in one optimistic
                            # update so a late worker cannot overwrite a review.
                            updated_extraction = await repo.update_extraction_results(
                                extraction_id=existing_extraction.id,
                                extracted_fields=extraction.extracted_fields,
                                needs_review=True,
                                needs_review_reasons=[f"NAME_MISMATCH_AUTO_REJECTED: {mismatch_reason}"],
                                template_id=extraction.template_id,
                                template_version=extraction.template_version,
                                template_match_evidence=extraction.template_match_evidence,
                                review_assist=extraction.review_assist,
                                field_evidence=extraction.field_evidence,
                                expected_state=ReviewState.PROCESSING,
                                expected_version=existing_extraction.review_state_version,
                                new_state=ReviewState.REJECTED,
                            )
                            if not updated_extraction:
                                await session.rollback()
                                log.info(
                                    "Discarded stale name-mismatch result",
                                    document_id=document_id,
                                    extraction_id=existing_extraction.id,
                                )
                                return True
                            await session.commit()

                            # Notify only after the rejection is durable.
                            if email_msg:
                                try:
                                    from shared.email_sender import send_email
                                    from shared.email_templates import NAME_MISMATCH_REJECTION
                                    await send_email(
                                        to=email_msg.from_address,
                                        subject="Re: " + (email_msg.subject or "Certificate Submission"),
                                        body=NAME_MISMATCH_REJECTION,
                                        reply_to_message_id=email_msg.message_id,
                                    )
                                except Exception as email_err:
                                    log.error(
                                        "Failed to send name mismatch rejection email",
                                        document_id=document_id,
                                        error=str(email_err),
                                    )
                            log.info(
                                "Extraction auto-rejected for name mismatch",
                                document_id=document_id,
                            )
                            return True
                        else:
                            # Unknown intake channel — flag for review
                            needs_review_reasons.append(f"NAME_MISMATCH: {mismatch_reason}")
                            needs_review = True
                            name_mismatch_detected = True
                            log.warning(
                                "Name mismatch detected",
                                document_id=document_id,
                                employee_id=employee.id,
                                reason=mismatch_reason,
                            )

                # Update existing extraction record with results
                updated_extraction = await repo.update_extraction_results(
                    extraction_id=existing_extraction.id,
                    extracted_fields=extraction.extracted_fields,
                    needs_review=needs_review,
                    needs_review_reasons=needs_review_reasons,
                    template_id=extraction.template_id,
                    template_version=extraction.template_version,
                    template_match_evidence=extraction.template_match_evidence,
                    review_assist=extraction.review_assist,
                    field_evidence=extraction.field_evidence,
                    expected_state=ReviewState.PROCESSING,
                    expected_version=existing_extraction.review_state_version,
                    new_state=ReviewState.PENDING_REVIEW,
                )

                if not updated_extraction:
                    await session.rollback()
                    log.info(
                        "Discarded stale extraction result",
                        document_id=document_id,
                        extraction_id=existing_extraction.id,
                    )
                    return True

                await session.commit()

                log.info(
                    "Extraction completed, transitioned to PendingReview",
                    document_id=document_id,
                    extraction_id=updated_extraction.id if updated_extraction else existing_extraction.id,
                    review_state=updated_extraction.review_state.value if updated_extraction else "unknown",
                    needs_review=needs_review,
                    template_id=extraction.template_id,
                    name_mismatch=name_mismatch_detected,
                )
                return True

        except Exception as e:
            from .pdf_text import DocumentLimitError

            if isinstance(e, DocumentLimitError):
                log.warning(
                    "Document exceeded extraction safety limit",
                    document_id=document_id,
                    reason=str(e),
                )
                try:
                    await self._record_document_limit(document_id, str(e))
                    return True
                except Exception as record_error:
                    log.error(
                        "Failed to persist document limit result",
                        document_id=document_id,
                        error=str(record_error),
                    )
                    task_data["last_error"] = "failed_to_persist_document_limit"
                    return False
            log.error(
                "Extraction failed",
                document_id=document_id,
                error=str(e),
                exc_info=True,
            )
            task_data["last_error"] = str(e)
            return False

    def _decode_task(self, task_json: bytes) -> tuple[dict | None, str | None]:
        """Decode task JSON and return (task_data, error_message)."""
        try:
            return json.loads(task_json.decode("utf-8")), None
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            return None, str(e)

    def _requeue_or_dead_letter(self, task_json: bytes, task_data: dict, error: str) -> None:
        """Retry task up to max_retries, then move to dead-letter queue."""
        retries = int(task_data.get("retries", 0))
        next_retries = retries + 1
        task_data["retries"] = next_retries
        task_data["last_error"] = error[:500]
        task_data["last_failed_at"] = datetime.now(timezone.utc).isoformat()

        if next_retries <= self.max_retries:
            # Exponential backoff (2,4,8,... capped) so transient outages don't
            # burn through all retries. The heartbeat runs in a separate thread,
            # so this blocking sleep does not stall stale-worker recovery.
            backoff = min(2 ** next_retries, EXTRACTION_RETRY_BACKOFF_MAX_SEC)
            if backoff > 0:
                time.sleep(backoff)
            moved = self._ack_and_push(
                task_json,
                EXTRACTION_QUEUE,
                json.dumps(task_data),
            )
            if moved:
                log.warning(
                    "Requeued extraction task after failure",
                    document_id=task_data.get("document_id"),
                    retry=next_retries,
                    max_retries=self.max_retries,
                    backoff_sec=backoff,
                )
            else:
                log.warning(
                    "Skipped extraction requeue because task was not found in processing queue",
                    document_id=task_data.get("document_id"),
                    retry=next_retries,
                    max_retries=self.max_retries,
                )
            return

        dlq_entry = {
            "task": task_data,
            "error": error[:500],
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        moved = self._ack_and_push(
            task_json,
            EXTRACTION_DLQ,
            json.dumps(dlq_entry),
        )
        if moved:
            log.error(
                "Moved extraction task to dead-letter queue",
                document_id=task_data.get("document_id"),
                retries=next_retries,
                max_retries=self.max_retries,
            )
        else:
            log.warning(
                "Skipped dead-letter push because extraction task was not found in processing queue",
                document_id=task_data.get("document_id"),
                retries=next_retries,
                max_retries=self.max_retries,
            )

    async def run(self):
        """Main worker loop."""
        log.info("Extraction Worker ready, waiting for tasks...")

        while not shutdown_requested:
            try:
                # Atomically claim one task into processing queue with timeout.
                self._maybe_recover_stale_workers()
                task_json = self._claim_task(timeout=5)

                if task_json:
                    task_data, decode_error = self._decode_task(task_json)
                    if not task_data:
                        log.error("Invalid extraction task payload", error=decode_error)
                        dlq_entry = {
                            "error": f"invalid_task_payload: {decode_error}",
                            "failed_at": datetime.now(timezone.utc).isoformat(),
                        }
                        moved = self._ack_and_push(
                            task_json,
                            EXTRACTION_DLQ,
                            json.dumps(dlq_entry),
                        )
                        if not moved:
                            log.warning(
                                "Skipped invalid-payload DLQ push because extraction task was not found in processing queue",
                                processing_queue=self.processing_queue,
                                worker_id=self.worker_id,
                            )
                        continue

                    should_ack = await self.process_task(task_data)
                    if not should_ack:
                        self._requeue_or_dead_letter(
                            task_json,
                            task_data,
                            task_data.get("last_error", "processing_failed"),
                        )
                    else:
                        self._ack_task(task_json)
                        log.debug(
                            "Extraction task handled",
                            document_id=task_data.get("document_id"),
                            retries=task_data.get("retries", 0),
                        )

            except redis.ConnectionError:
                log.warning("Redis connection lost, reconnecting...")
                await asyncio.sleep(5)
                try:
                    from shared.tls import redis_tls_kwargs
                    self.redis_client = redis.from_url(self.redis_url, **redis_tls_kwargs())
                    self.redis_client.ping()
                    self._ensure_blmove_support()
                    self._register_worker_presence()
                except Exception as e:
                    log.warning("Redis reconnection failed: %s", e)

            except Exception as e:
                log.error("Error in worker loop", error=str(e), exc_info=True)
                await asyncio.sleep(1)


async def async_main():
    """Async main function."""
    redis_url = os.getenv("REDIS_URL", "rediss://redis:6380/0")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    templates_dir = os.getenv("TEMPLATES_DIR", "/app/templates")

    import re as _re
    safe_redis_url = _re.sub(r':[^@/]+@', ':***@', redis_url)
    log.info(
        "Starting Extraction Worker",
        redis_url=safe_redis_url,
        templates_dir=templates_dir,
    )

    worker = ExtractionWorker(
        redis_url=redis_url,
        database_url=database_url,
        templates_dir=templates_dir,
    )

    try:
        await worker.initialize()
        await worker.run()
    finally:
        await worker.shutdown()


def main():
    """Main entry point."""
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        log.info("Extraction Worker interrupted")

    log.info("Extraction Worker shutting down")


if __name__ == "__main__":
    main()
