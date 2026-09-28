"""
City of Laredo - Scheduler & Notification Worker

Handles scheduled notification generation and email delivery.
"""

import asyncio
import os
import re
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import redis
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from .notifications import NotificationGenerator
from .digest_builder import build_digest_email
from shared.audit import audit
from shared.email_sender import send_email as _shared_send_email
from shared.models import AlertConfiguration
from shared.orm_models import AlertConfigurationORM

# Configure secure logging with redaction
from shared.logging_utils import configure_secure_logging, REDACTION_PATTERNS

# Set up base logging with redaction first
configure_secure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))

CENTRAL_TIMEZONE = ZoneInfo("America/Chicago")


def current_central_date(now: datetime | None = None) -> date:
    """Return the business date in America/Chicago."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(CENTRAL_TIMEZONE).date()


def delivery_time(send_hour: int, send_minute: int) -> tuple[int, int]:
    """Digest delivery time, 15 minutes after generation.

    The hour wraps modulo 24 so a send time of 23:45-23:59 rolls to 00:0x the
    next day instead of producing hour=24, which CronTrigger rejects (that
    crash-loops the scheduler worker at startup).
    """
    delivery_minute = (send_minute + 15) % 60
    delivery_hour = (send_hour + ((send_minute + 15) // 60)) % 24
    return delivery_hour, delivery_minute


def redact_sensitive_data(_, __, event_dict):
    """Structlog processor to redact sensitive data from log events."""
    # Pre-compile patterns for this processor
    compiled_patterns = [
        (re.compile(pattern, re.IGNORECASE), replacement)
        for pattern, replacement in REDACTION_PATTERNS.items()
    ]

    def redact_value(value):
        if isinstance(value, str):
            for pattern, replacement in compiled_patterns:
                value = pattern.sub(replacement, value)
        return value

    # Redact all string values in the event dict
    for key, value in event_dict.items():
        event_dict[key] = redact_value(value)

    return event_dict


# Configure structlog with redaction processor
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_sensitive_data,  # Add redaction before rendering
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger(__name__)


class SchedulerWorker:
    """Scheduler worker for notification generation and delivery."""

    def __init__(self, database_url: str):
        """
        Initialize scheduler worker.

        Args:
            database_url: Database connection URL
        """
        # Ensure asyncpg driver
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        from shared.tls import build_ssl_context
        ssl_ctx = build_ssl_context()
        self.engine = create_async_engine(
            database_url,
            echo=False,
            connect_args={"ssl": ssl_ctx} if ssl_ctx else {},
        )
        self.async_session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def _load_alert_config(self, session: AsyncSession) -> AlertConfiguration:
        """Load alert configuration from DB, falling back to defaults if missing."""
        try:
            stmt = select(AlertConfigurationORM).where(AlertConfigurationORM.id == 1)
            result = await session.execute(stmt)
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                config = AlertConfiguration(
                    id=orm_obj.id,
                    requirement_reminder_days=list(orm_obj.requirement_reminder_days),
                    certificate_reminder_days=list(orm_obj.certificate_reminder_days),
                    daily_overdue_enabled=orm_obj.daily_overdue_enabled,
                    global_send_hour=orm_obj.global_send_hour,
                    global_send_minute=orm_obj.global_send_minute,
                    updated_at=orm_obj.updated_at,
                    updated_by_id=orm_obj.updated_by_id,
                )
                log.info(
                    "Loaded alert configuration from DB",
                    requirement_days=config.requirement_reminder_days,
                    certificate_days=config.certificate_reminder_days,
                    daily_overdue=config.daily_overdue_enabled,
                    send_hour=config.global_send_hour,
                    send_minute=config.global_send_minute,
                )
                return config
        except Exception as e:
            log.error("Failed to load alert configuration", error=str(e))
            raise

        # Fallback defaults matching previous hardcoded values
        return AlertConfiguration(
            id=1,
            requirement_reminder_days=[90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1],
            certificate_reminder_days=[90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1],
            daily_overdue_enabled=True,
            global_send_hour=6,
            global_send_minute=0,
        )

    async def generate_notifications_daily(self):
        """Generate daily notifications for requirements and certificates."""
        log.info("Running daily notification generation")

        try:
            async with self.async_session_factory() as session:
                from shared.repository import SqlRepository

                repo = SqlRepository(session)

                # Load managed config from DB
                config = await self._load_alert_config(session)

                generator = NotificationGenerator(
                    repo,
                    due_reminder_days=config.requirement_reminder_days,
                    expiration_reminder_days=config.certificate_reminder_days,
                    daily_overdue_enabled=config.daily_overdue_enabled,
                )

                current_date = current_central_date()
                count = await generator.generate_notifications_daily(current_date)

                await session.commit()

                log.info(
                    "Daily notifications generated",
                    count=count,
                    date=current_date.isoformat(),
                )

        except Exception as e:
            log.error("Failed to generate notifications", error=str(e), exc_info=True)
            raise

    async def process_notification_queue(self):
        """Process pending notifications and send digest emails."""
        log.info("Processing notification queue (digest mode)")

        try:
            async with self.async_session_factory() as session:
                from shared.repository import SqlRepository

                repo = SqlRepository(session)

                # Fetch undelivered notifications (high limit for digest batching)
                notifications = await repo.list_undelivered_notifications(limit=5000)

                if not notifications:
                    log.info("No pending notifications")
                    return

                # Group by recipient
                by_recipient: dict[int, list] = {}
                for n in notifications:
                    by_recipient.setdefault(n.recipient_employee_id, []).append(n)

                log.info("Building digests", recipient_count=len(by_recipient),
                         total_notifications=len(notifications))

                # For each recipient, build and send one digest email
                sent_count = 0
                failed_count = 0
                for employee_id, batch in by_recipient.items():
                    try:
                        employee = await repo.get_employee_by_id(employee_id)
                        if not employee:
                            log.warning("Recipient not found",
                                        employee_id=employee_id)
                            continue

                        # Skip employees with no email address
                        if not employee.email or not employee.email.strip():
                            log.warning("Skipping digest: no email",
                                        employee_id=employee_id)
                            continue

                        # Skip deactivated employees but mark their notifications
                        # delivered so they don't accumulate. The Coordinator's
                        # copies are separate rows with a different
                        # recipient_employee_id, so they are NOT affected.
                        if not employee.is_active:
                            log.info("Skipping digest for deactivated employee",
                                     employee_id=employee_id,
                                     notifications_cleared=len(batch))
                            await repo.mark_notifications_delivered_batch(
                                [n.id for n in batch])
                            await session.commit()
                            continue

                        # Detect coordinator by role, not by subject string
                        is_coordinator = employee.role == "Coordinator"

                        # Single-notification pass-through: use original subject/body
                        if len(batch) == 1:
                            subject = batch[0].subject
                            body = batch[0].body
                        else:
                            subject, body = build_digest_email(
                                batch,
                                employee_name=f"{employee.first_name} {employee.last_name}",
                                is_coordinator=is_coordinator,
                            )

                        success = await self._send_email(
                            to_email=employee.email,
                            subject=subject,
                            body=body,
                        )

                        if success:
                            await repo.mark_notifications_delivered_batch(
                                [n.id for n in batch])
                            await session.commit()
                            sent_count += 1
                            log.info("Digest sent",
                                     employee_id=employee_id,
                                     notification_count=len(batch),
                                     is_coordinator=is_coordinator)
                        else:
                            failed_count += 1

                        # Rate limiting: 500ms between sends
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        failed_count += 1
                        log.error("Failed to send digest",
                                  employee_id=employee_id,
                                  error=str(e), exc_info=True)

                log.info("Digest cycle complete",
                         digests_sent=sent_count,
                         digests_failed=failed_count,
                         total_notifications=len(notifications),
                         recipients_total=len(by_recipient))

                # Per-batch audit summary so admins can confirm deliveries
                # via the audit log (per-notification rows would be too noisy
                # at this volume). target_id is a synthesized cycle marker.
                # Use the shared audit() helper so secret-key scrubbing and
                # actor-type validation are applied uniformly.
                cycle_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                await audit(
                    repository=repo,
                    action="notification_batch_sent",
                    target_type="notification_batch",
                    target_id=cycle_id,
                    details={
                        "digests_sent": sent_count,
                        "digests_failed": failed_count,
                        "total_notifications": len(notifications),
                        "recipients_total": len(by_recipient),
                    },
                    source_service="scheduler-worker",
                    outcome="Success" if failed_count == 0 else "Partial",
                )
                await session.commit()

                # Warn if we hit the fetch limit (some recipients may be deferred)
                if len(notifications) >= 5000:
                    log.warning("Notification fetch limit reached, some recipients "
                                "may be deferred to next cycle")

        except Exception as e:
            log.error("Failed to process notification queue",
                      error=str(e), exc_info=True)
            raise

    async def _send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
    ) -> bool:
        """Send email via the shared email sender."""
        return await _shared_send_email(to=to_email, subject=subject, body=body)

    async def shutdown(self):
        """Cleanup resources."""
        await self.engine.dispose()


async def async_main():
    """Async main function."""
    log.info("Starting Scheduler & Notification Worker")

    # Configuration from environment (DATABASE_URL required)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL environment variable is required")
        sys.exit(1)
    redis_url = os.getenv("REDIS_URL", "rediss://redis:6380/0")

    # Verify Redis connection
    try:
        from shared.tls import redis_tls_kwargs
        r = redis.from_url(redis_url, **redis_tls_kwargs())
        r.ping()
        log.info("Connected to Redis")
    except Exception as e:
        log.error("Failed to connect to Redis", error=str(e))
        sys.exit(1)

    # Create worker (SMTP config is read from env vars by shared.email_sender)
    worker = SchedulerWorker(database_url=database_url)

    # Load send time from DB config (fallback: 06:00)
    async with worker.async_session_factory() as session:
        alert_config = await worker._load_alert_config(session)
    send_hour = alert_config.global_send_hour
    send_minute = alert_config.global_send_minute
    # Delivery runs 15 minutes after generation.
    delivery_hour, delivery_minute = delivery_time(send_hour, send_minute)

    # Create scheduler
    scheduler = AsyncIOScheduler(timezone=CENTRAL_TIMEZONE)

    # Schedule daily notification generation at configured send time
    scheduler.add_job(
        worker.generate_notifications_daily,
        CronTrigger(
            hour=send_hour,
            minute=send_minute,
            timezone=CENTRAL_TIMEZONE,
        ),
        id="generate_notifications_daily",
        name="Generate Daily Notifications",
    )

    # Send daily notification digests 15 min after generation
    scheduler.add_job(
        worker.process_notification_queue,
        CronTrigger(
            hour=delivery_hour,
            minute=delivery_minute,
            timezone=CENTRAL_TIMEZONE,
        ),
        id="process_notification_queue",
        name="Send Daily Notification Digests",
    )

    log.info("Scheduler configured, starting...",
             generation_time=f"{send_hour:02d}:{send_minute:02d}",
             delivery_time=f"{delivery_hour:02d}:{delivery_minute:02d}")

    try:
        scheduler.start()
        # Keep running
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler shutting down")
        scheduler.shutdown()
        await worker.shutdown()


def main():
    """Main entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        log.info("Scheduler interrupted")


if __name__ == "__main__":
    main()
