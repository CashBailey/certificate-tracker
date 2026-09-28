"""
City of Laredo - OCR Engine Worker

Handles OCR processing using Tesseract.
Processes requests from Redis queue and returns results.
"""

import base64
import hashlib
import importlib.util
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from datetime import datetime, timezone

import redis
import structlog

_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(format="%(message)s", stream=sys.stderr, level=_log_level)

try:
    from .ocr_service import (
        TesseractOcrService,
        deserialize_ocr_request,
        serialize_ocr_result,
    )
except ImportError:
    from ocr_service import (
        TesseractOcrService,
        deserialize_ocr_request,
        serialize_ocr_result,
    )

# Optional EasyOCR + Ensemble support. The standard image intentionally omits
# the unbounded GPU stack; custom images may supply it explicitly.
EASYOCR_AVAILABLE = importlib.util.find_spec("easyocr") is not None
if EASYOCR_AVAILABLE:
    try:
        try:
            from .easyocr_service import EasyOcrService
            from .ensemble_ocr import EnsembleOcrEngine
        except ImportError:
            from easyocr_service import EasyOcrService
            from ensemble_ocr import EnsembleOcrEngine
    except ImportError:
        EASYOCR_AVAILABLE = False

# Configure logging
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

OCR_QUEUE = "ocr_tasks"
OCR_DLQ = "ocr_tasks:dead_letter"
OCR_PROCESSING_QUEUE_PREFIX = "ocr_tasks:processing"
OCR_ACTIVE_WORKERS_KEY = f"{OCR_QUEUE}:workers:active"
OCR_HEARTBEAT_KEY_PREFIX = f"{OCR_QUEUE}:workers:heartbeat"
OCR_RECOVERY_LOCK_KEY = f"{OCR_QUEUE}:recovery:lock"
OCR_MAX_RETRIES = int(os.getenv("OCR_MAX_RETRIES", "3"))
# Backoff before re-queueing a failed OCR task; see the extraction worker for
# rationale. Heartbeat runs in a separate thread, so a blocking sleep is safe.
OCR_RETRY_BACKOFF_MAX_SEC = int(os.getenv("OCR_RETRY_BACKOFF_MAX_SEC", "30"))
WORKER_HEARTBEAT_INTERVAL_SEC = float(os.getenv("WORKER_HEARTBEAT_INTERVAL_SEC", "10"))
WORKER_HEARTBEAT_TTL_SEC = int(os.getenv("WORKER_HEARTBEAT_TTL_SEC", "30"))
WORKER_RECOVERY_LOCK_TTL_SEC = int(os.getenv("WORKER_RECOVERY_LOCK_TTL_SEC", "15"))
WORKER_STALE_SCAN_INTERVAL_SEC = float(os.getenv("WORKER_STALE_SCAN_INTERVAL_SEC", "30"))

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


class OcrWorker:
    """OCR worker that processes OCR tasks from Redis."""

    def __init__(
        self,
        redis_url: str,
        tesseract_lang: str = "eng",
        tesseract_config: str = "",
        worker_id: str | None = None,
    ):
        """
        Initialize OCR worker.

        Args:
            redis_url: Redis connection URL
            tesseract_lang: Tesseract language(s)
            tesseract_config: Additional Tesseract config
        """
        self.redis_url = redis_url
        self.redis_client = None
        self.max_retries = OCR_MAX_RETRIES
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
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._next_stale_recovery_at = time.monotonic() + self.stale_scan_interval_sec

        tesseract = TesseractOcrService(
            lang=tesseract_lang,
            config=tesseract_config,
        )

        # EasyOCR has no enforceable per-call timeout in this worker. Keep the
        # bounded Tesseract path as the default; GPU ensemble is explicit opt-in.
        enable_easyocr = os.getenv("OCR_ENABLE_EASYOCR", "false").lower() == "true"
        if enable_easyocr and not EASYOCR_AVAILABLE:
            log.warning("EasyOCR requested but not installed; using bounded Tesseract only")
        if EASYOCR_AVAILABLE and enable_easyocr:
            try:
                easyocr_svc = EasyOcrService(lang="en", gpu=True)
                self.ocr_service = EnsembleOcrEngine(tesseract, easyocr_svc)
                log.info("Using ensemble OCR engine (Tesseract + EasyOCR)")
            except Exception as e:
                log.warning("EasyOCR init failed, using Tesseract only", error=str(e))
                self.ocr_service = tesseract
        else:
            self.ocr_service = tesseract

    @staticmethod
    def _processing_queue_for_worker(worker_id: str) -> str:
        return f"{OCR_PROCESSING_QUEUE_PREFIX}:{worker_id}"

    @staticmethod
    def _heartbeat_key_for_worker(worker_id: str) -> str:
        return f"{OCR_HEARTBEAT_KEY_PREFIX}:{worker_id}"

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
        heartbeat_key = self._heartbeat_key_for_worker(self.worker_id)
        self.redis_client.setex(heartbeat_key, self.heartbeat_ttl_sec, "1")
        self.redis_client.sadd(OCR_ACTIVE_WORKERS_KEY, self.worker_id)

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(self.heartbeat_interval_sec):
            try:
                self._register_worker_presence()
            except Exception as exc:
                log.warning(
                    "Failed to refresh OCR worker heartbeat",
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
            name=f"ocr-heartbeat-{self.worker_id}",
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
            self.redis_client.srem(OCR_ACTIVE_WORKERS_KEY, self.worker_id)
        except Exception:
            pass

    def _acquire_recovery_lock(self) -> bool:
        acquired = self.redis_client.set(
            OCR_RECOVERY_LOCK_KEY,
            self.worker_id,
            nx=True,
            ex=self.recovery_lock_ttl_sec,
        )
        return bool(acquired)

    def _release_recovery_lock(self) -> None:
        try:
            owner = self.redis_client.get(OCR_RECOVERY_LOCK_KEY)
            if owner is None:
                return
            if self._decode_member(owner) == self.worker_id:
                self.redis_client.delete(OCR_RECOVERY_LOCK_KEY)
        except Exception:
            pass

    def connect(self):
        """Connect to Redis."""
        from shared.tls import redis_tls_kwargs
        self.redis_client = redis.from_url(self.redis_url, **redis_tls_kwargs())
        self.redis_client.ping()
        self._ensure_blmove_support()
        log.info(
            "Connected to Redis",
            worker_id=self.worker_id,
            processing_queue=self.processing_queue,
        )
        self._start_heartbeat()
        self.recover_inflight_tasks()
        self.recover_stale_worker_tasks()

    def _claim_task(self, timeout: int = 5) -> bytes | None:
        """Atomically move one task from OCR queue to processing queue."""
        try:
            task = self.redis_client.execute_command(
                "BLMOVE",
                OCR_QUEUE,
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

    def _ack_task(self, task_data: bytes) -> bool:
        """Acknowledge an OCR task by removing it from processing queue."""
        removed = self.redis_client.lrem(self.processing_queue, 1, task_data)
        if removed == 0:
            log.warning(
                "Task not found in OCR processing queue during ack",
                processing_queue=self.processing_queue,
                worker_id=self.worker_id,
            )
            return False
        return True

    def _ack_and_push(self, task_data: bytes, destination_queue: str, payload: bytes | str) -> bool:
        """
        Atomically ack a processing OCR task and push replacement payload to destination queue.
        """
        removed = self.redis_client.eval(
            ACK_AND_PUSH_LUA,
            2,
            self.processing_queue,
            destination_queue,
            task_data,
            payload,
        )
        return int(removed) > 0

    def recover_inflight_tasks(self, worker_id: str | None = None) -> int:
        """Move tasks from one worker-owned processing queue back to OCR queue."""
        owner_id = worker_id or self.worker_id
        processing_queue = self._processing_queue_for_worker(owner_id)
        recovered = 0
        while True:
            moved = self.redis_client.rpoplpush(
                processing_queue,
                OCR_QUEUE,
            )
            if not moved:
                break
            recovered += 1

        if recovered:
            log.warning(
                "Recovered OCR tasks from processing queue",
                recovered_count=recovered,
                owner_worker_id=owner_id,
                source_queue=processing_queue,
                destination_queue=OCR_QUEUE,
            )
        return recovered

    def recover_stale_worker_tasks(self) -> int:
        """Recover tasks from stale OCR workers whose heartbeat has expired."""
        if not self._acquire_recovery_lock():
            return 0

        total_recovered = 0
        try:
            members = self.redis_client.smembers(OCR_ACTIVE_WORKERS_KEY)
            for member in list(members):
                candidate = self._decode_member(member)
                if candidate == self.worker_id:
                    continue
                if self.redis_client.exists(self._heartbeat_key_for_worker(candidate)):
                    continue
                recovered = self.recover_inflight_tasks(worker_id=candidate)
                total_recovered += recovered
                self.redis_client.srem(OCR_ACTIVE_WORKERS_KEY, candidate)
                log.warning(
                    "Recovered stale OCR worker queue",
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
                "Failed stale OCR worker recovery pass",
                worker_id=self.worker_id,
                error=str(exc),
            )

    def process_task(self, task_data: bytes) -> bool:
        """
        Process a single OCR task.

        Args:
            task_data: Serialized OCR request

        Returns:
            True when task is handled (success or permanent malformed payload),
            False when task should be retried.
        """
        try:
            # Deserialize request
            request_id, page_image, bbox_norm = deserialize_ocr_request(task_data)

            log.info(
                "Processing OCR task",
                request_id=request_id,
                page_num=page_image.page_num,
                bbox=bbox_norm,
            )

            # Perform OCR
            text_spans = self.ocr_service.ocr_region(page_image, bbox_norm)

            log.info(
                "OCR completed",
                request_id=request_id,
                spans_found=len(text_spans),
            )

            # Serialize and push result
            result_data = serialize_ocr_result(request_id, text_spans)
            result_key = f"ocr_results:{request_id}"

            # Push to result key with expiration (5 minutes)
            self.redis_client.setex(result_key, 300, result_data)

            log.info(
                "OCR result published",
                request_id=request_id,
                result_key=result_key,
            )
            return True

        except (KeyError, ValueError, json.JSONDecodeError) as e:
            # Permanent payload issues should not be retried endlessly.
            log.error("Invalid OCR task payload", error=str(e), exc_info=True)
            return True
        except Exception as e:
            log.error("OCR processing failed", error=str(e), exc_info=True)
            return False

    def _requeue_or_dead_letter(self, task_data: bytes, error: str) -> None:
        """Retry OCR task up to max_retries, then move to dead-letter queue."""
        try:
            parsed = json.loads(task_data.decode("utf-8"))
        except Exception:
            dlq_entry = {
                "error": error[:500],
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "task_sha256": hashlib.sha256(task_data).hexdigest(),
                "task_prefix_b64": base64.b64encode(task_data[:4096]).decode("ascii"),
                "task_bytes": len(task_data),
            }
            moved = self._ack_and_push(task_data, OCR_DLQ, json.dumps(dlq_entry))
            if not moved:
                log.warning(
                    "Skipped OCR DLQ push because task was not found in processing queue",
                    processing_queue=self.processing_queue,
                    worker_id=self.worker_id,
                )
            return

        retries = int(parsed.get("retries", 0)) + 1
        parsed["retries"] = retries
        parsed["last_error"] = error[:500]
        parsed["last_failed_at"] = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(parsed).encode("utf-8")

        if retries <= self.max_retries:
            backoff = min(2 ** retries, OCR_RETRY_BACKOFF_MAX_SEC)
            if backoff > 0:
                time.sleep(backoff)
            moved = self._ack_and_push(task_data, OCR_QUEUE, encoded)
            if moved:
                log.warning(
                    "Requeued OCR task after failure",
                    request_id=parsed.get("request_id"),
                    retry=retries,
                    max_retries=self.max_retries,
                    backoff_sec=backoff,
                )
            else:
                log.warning(
                    "Skipped OCR requeue because task was not found in processing queue",
                    request_id=parsed.get("request_id"),
                    retry=retries,
                    max_retries=self.max_retries,
                )
            return

        image_b64 = parsed.pop("image_b64", "")
        dlq_entry = {
            "task": parsed,
            "image_b64_sha256": hashlib.sha256(image_b64.encode()).hexdigest(),
            "image_b64_chars": len(image_b64),
            "error": error[:500],
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        moved = self._ack_and_push(task_data, OCR_DLQ, json.dumps(dlq_entry))
        if moved:
            log.error(
                "Moved OCR task to dead-letter queue",
                request_id=parsed.get("request_id"),
                retries=retries,
                max_retries=self.max_retries,
            )
        else:
            log.warning(
                "Skipped OCR dead-letter push because task was not found in processing queue",
                request_id=parsed.get("request_id"),
                retries=retries,
                max_retries=self.max_retries,
            )

    def run(self):
        """Main worker loop."""
        log.info("OCR Engine ready, waiting for tasks...")

        while not shutdown_requested:
            try:
                # Atomically claim one OCR task into processing queue with timeout.
                self._maybe_recover_stale_workers()
                task_data = self._claim_task(timeout=5)

                if task_data:
                    ok = self.process_task(task_data)
                    if not ok:
                        self._requeue_or_dead_letter(task_data, "ocr_processing_failed")
                    else:
                        self._ack_task(task_data)

            except redis.ConnectionError:
                log.warning("Redis connection lost, reconnecting...")
                time.sleep(5)
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
                time.sleep(1)

    def shutdown(self):
        self._stop_heartbeat()


def main():
    """Main entry point."""
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    redis_url = os.getenv("REDIS_URL", "rediss://redis:6380/0")
    tesseract_lang = os.getenv("TESSERACT_LANG", "eng+spa")

    import re as _re
    safe_url = _re.sub(r':[^@/]+@', ':***@', redis_url)
    log.info(
        "Starting OCR Engine Worker",
        redis_url=safe_url,
        tesseract_lang=tesseract_lang,
    )

    worker = OcrWorker(
        redis_url=redis_url,
        tesseract_lang=tesseract_lang,
    )

    try:
        worker.connect()
        worker.run()
    except Exception as e:
        log.error("Failed to start worker", error=str(e))
        sys.exit(1)
    finally:
        worker.shutdown()

    log.info("OCR Engine shutting down")


if __name__ == "__main__":
    main()
