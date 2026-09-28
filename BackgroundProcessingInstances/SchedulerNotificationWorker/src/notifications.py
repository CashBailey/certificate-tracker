"""
Notification generation for the City of Laredo Certificate Management System.

Handles daily notification generation for requirements and certificates.
Reminder intervals are loaded from DB (notifications.alert_configuration).
Also sends notifications to Coordinator per OPS-02.
"""

from datetime import date, timedelta
from typing import Optional

from shared.models import (
    JobCursor,
    NotificationEvent,
    NotificationType,
    RequirementAssignment,
    Role,
    VerifiedCertificateRecord,
)
from shared.protocols import Repository


# Fallback defaults used when no DB config is available.
# Production values are loaded from notifications.alert_configuration table.
_DEFAULT_REQUIREMENT_REMINDER_DAYS = [90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1]
_DEFAULT_CERTIFICATE_REMINDER_DAYS = [90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1]


def make_dedupe_key(
    notification_type: NotificationType,
    entity_id: int,
    date_ref: date,
) -> str:
    """
    Create deterministic dedupe key for notification.

    Args:
        notification_type: Type of notification
        entity_id: ID of related entity (requirement or certificate)
        date_ref: Reference date for the notification

    Returns:
        Dedupe key string
    """
    return f"{notification_type.value}:{entity_id}:{date_ref.isoformat()}"


class NotificationGenerator:
    """Generates notifications for requirements and certificates."""

    def __init__(
        self,
        repository: Repository,
        due_reminder_days: list[int] = None,
        expiration_reminder_days: list[int] = None,
        daily_overdue_enabled: bool = True,
    ):
        """
        Initialize notification generator.

        Args:
            repository: Repository instance
            due_reminder_days: Days before due date to send reminders
            expiration_reminder_days: Days before expiration to send reminders
            daily_overdue_enabled: Whether to generate daily overdue notifications
        """
        self.repository = repository
        self.due_reminder_days = due_reminder_days or _DEFAULT_REQUIREMENT_REMINDER_DAYS
        self.expiration_reminder_days = expiration_reminder_days or _DEFAULT_CERTIFICATE_REMINDER_DAYS
        self.daily_overdue_enabled = daily_overdue_enabled
        # Caches to avoid repeated queries
        self._coordinator_id_cache: Optional[int] = None
        self._coordinator_cache_loaded: bool = False
        self._employee_name_cache: dict[int, str] = {}
        self._cert_type_name_cache: dict[int, str] = {}

    async def _get_coordinator_id(self) -> Optional[int]:
        """
        Get the Coordinator employee ID for notifications.

        Per OPS-02: Coordinator always receives notifications so they can act and report.
        Returns the first active Coordinator found, or None if no Coordinator exists.
        Caches the result to avoid repeated queries.
        """
        if self._coordinator_cache_loaded:
            return self._coordinator_id_cache

        # Query for employees with Coordinator role
        coordinators = await self.repository.get_employees_by_role(Role.COORDINATOR.value)

        if coordinators:
            self._coordinator_id_cache = coordinators[0].id
        else:
            self._coordinator_id_cache = None

        self._coordinator_cache_loaded = True
        return self._coordinator_id_cache

    def _reset_caches(self):
        """Reset all caches (useful for testing and at start of daily run)."""
        self._coordinator_id_cache = None
        self._coordinator_cache_loaded = False
        self._employee_name_cache.clear()
        self._cert_type_name_cache.clear()

    async def _get_employee_name(self, employee_id: int) -> str:
        """Get employee display name by ID, with caching."""
        if employee_id in self._employee_name_cache:
            return self._employee_name_cache[employee_id]

        employee = await self.repository.get_employee_by_id(employee_id)
        if employee:
            name = f"{employee.first_name} {employee.last_name}".strip()
        else:
            name = f"Employee #{employee_id}"

        self._employee_name_cache[employee_id] = name
        return name

    async def _get_cert_type_name(self, certificate_type_id: int) -> str:
        """Get certificate type name by ID, with caching."""
        if certificate_type_id in self._cert_type_name_cache:
            return self._cert_type_name_cache[certificate_type_id]

        cert_type = await self.repository.get_certificate_type_by_id(certificate_type_id)
        if cert_type:
            name = cert_type.name
        else:
            name = "certificate"

        self._cert_type_name_cache[certificate_type_id] = name
        return name

    async def generate_notifications_daily(self, current_date: date) -> int:
        """
        Generate all daily notifications for requirements and certificates.

        Uses cursor-locked resilient job pattern:
        1. Get last processed date from cursor
        2. Backfill any missed dates
        3. Process current date
        4. Advance cursor

        Args:
            current_date: Current date to process

        Returns:
            Number of notifications created
        """
        # Reset all caches at start of each daily run
        self._reset_caches()

        # Get cursor
        cursor = await self.repository.get_job_cursor("daily_notifications")
        last_date = cursor.last_success_date if cursor else current_date - timedelta(days=1)

        total_created = 0

        # Backfill any missed dates
        process_date = last_date + timedelta(days=1)
        while process_date <= current_date:
            created = await self._generate_for_date(process_date)
            total_created += created
            process_date += timedelta(days=1)

        # Update cursor
        await self.repository.upsert_job_cursor(JobCursor(
            job_name="daily_notifications",
            last_success_date=current_date,
        ))

        return total_created

    async def _generate_for_date(self, process_date: date) -> int:
        """Generate notifications for a specific date."""
        count = 0

        # Requirement notifications
        count += await self._generate_requirement_notifications(process_date)

        # Certificate lifecycle notifications
        count += await self._generate_certificate_notifications(process_date)

        return count

    async def _generate_requirement_notifications(self, process_date: date) -> int:
        """
        Generate notifications for requirements at 90/60/30 day intervals.

        Per spec: Notifications are sent at specific intervals before due date.
        Per OPS-02: Notifications go to BOTH employee AND Coordinator.
        """
        count = 0

        # Due today (day 0) - requirement is due right now. Use DUE_SOON with
        # days_until_due=0 so the message reads "due today", not "due tomorrow".
        requirements = await self.repository.list_requirements_due_between(
            process_date, process_date
        )
        for req in requirements:
            if req.satisfied_by_id is None and req.waived_at is None:
                created = await self._create_requirement_notification(
                    req, NotificationType.REQUIREMENT_DUE_SOON, process_date,
                    days_until_due=0
                )
                count += created

        # Due tomorrow - last-day reminder
        due_tomorrow = process_date + timedelta(days=1)
        requirements = await self.repository.list_requirements_due_between(
            due_tomorrow, due_tomorrow
        )
        for req in requirements:
            if req.satisfied_by_id is None and req.waived_at is None:
                created = await self._create_requirement_notification(
                    req, NotificationType.REQUIREMENT_DUE_TOMORROW, process_date
                )
                count += created

        # Due soon at each reminder interval (90, 60, 30 days)
        for days_ahead in self.due_reminder_days:
            # Day 1 has a dedicated notification type above. Emitting both
            # types creates two user-visible events for the same deadline.
            if days_ahead == 1:
                continue
            target_date = process_date + timedelta(days=days_ahead)
            requirements = await self.repository.list_requirements_due_between(
                target_date, target_date
            )
            for req in requirements:
                if req.satisfied_by_id is None and req.waived_at is None:
                    created = await self._create_requirement_notification(
                        req, NotificationType.REQUIREMENT_DUE_SOON, process_date,
                        days_until_due=days_ahead
                    )
                    count += created

        # Overdue - daily check for ALL overdue requirements until satisfied
        if self.daily_overdue_enabled:
            overdue_start = process_date - timedelta(days=3650)  # Look back 10 years (effectively unlimited)
            overdue_end = process_date - timedelta(days=1)
            requirements = await self.repository.list_requirements_due_between(
                overdue_start, overdue_end
            )
            for req in requirements:
                if req.satisfied_by_id is None and req.waived_at is None:
                    created = await self._create_requirement_notification(
                        req, NotificationType.REQUIREMENT_OVERDUE, process_date
                    )
                    count += created

        return count

    async def _generate_certificate_notifications(self, process_date: date) -> int:
        """
        Generate notifications for certificate lifecycle at 90/60/30 day intervals.

        Per spec: Notifications are sent at specific intervals before expiration.
        Per OPS-02: Notifications go to BOTH employee AND Coordinator.
        """
        count = 0

        # Expiring soon at each reminder interval (90, 60, 30 days)
        for days_ahead in self.expiration_reminder_days:
            target_date = process_date + timedelta(days=days_ahead)
            records = await self.repository.list_verified_records_expiring_between(
                target_date, target_date
            )
            for record in records:
                created = await self._create_certificate_notification(
                    record, NotificationType.CERTIFICATE_EXPIRING_SOON, process_date,
                    days_until_expiration=days_ahead
                )
                count += created

        # Expired - daily check for recently expired certificates. A cert whose
        # expiration_date == process_date is still valid *today* (status logic
        # uses current_date > expiration_date), so the EXPIRED window must end
        # the day before, mirroring the requirement-overdue window.
        if self.daily_overdue_enabled:
            expired_start = process_date - timedelta(days=7)  # Look back 7 days
            expired_end = process_date - timedelta(days=1)
            records = await self.repository.list_verified_records_expiring_between(
                expired_start, expired_end
            )
            for record in records:
                created = await self._create_certificate_notification(
                    record, NotificationType.CERTIFICATE_EXPIRED, process_date
                )
                count += created

        return count

    async def _create_requirement_notification(
        self,
        requirement: RequirementAssignment,
        notification_type: NotificationType,
        process_date: date,
        days_until_due: Optional[int] = None,
    ) -> int:
        """
        Create requirement notifications for both employee and Coordinator.

        Per OPS-02: Coordinator always receives notifications.

        Returns:
            Number of notifications created (0, 1, or 2)
        """
        count = 0

        # Include days_until_due in dedupe key for interval-specific notifications.
        # Use `is not None` so the day-0 "due today" notification (days_until_due=0)
        # gets its own suffix and never collides with the days_until_due=None passes.
        dedupe_suffix = f":{days_until_due}" if days_until_due is not None else ""
        base_dedupe_key = make_dedupe_key(
            notification_type, requirement.id, process_date
        ) + dedupe_suffix

        # Resolve names for enriched messages
        employee_name = await self._get_employee_name(requirement.employee_id)
        cert_type_name = await self._get_cert_type_name(requirement.certificate_type_id)

        # Build notification content
        subject, body = self._build_requirement_message(
            requirement, notification_type, days_until_due,
            cert_type_name=cert_type_name,
        )

        # 1. Create notification for the employee
        # effective_date is the due date - the logical trigger date for reporting
        employee_notification = NotificationEvent(
            id=0,
            notification_type=notification_type,
            recipient_employee_id=requirement.employee_id,
            subject=subject,
            body=body,
            dedupe_key=base_dedupe_key,
            related_requirement_id=requirement.id,
            effective_date=requirement.due_date,
        )

        if await self.repository.insert_notification_if_absent(employee_notification):
            count += 1

        # 2. Create notification for Coordinator (if exists and is different from employee)
        coordinator_id = await self._get_coordinator_id()
        if coordinator_id and coordinator_id != requirement.employee_id:
            # Build Coordinator-specific message
            coord_subject, coord_body = self._build_requirement_message_for_coordinator(
                requirement, notification_type, days_until_due,
                employee_name=employee_name,
                cert_type_name=cert_type_name,
            )

            coordinator_notification = NotificationEvent(
                id=0,
                notification_type=notification_type,
                recipient_employee_id=coordinator_id,
                subject=coord_subject,
                body=coord_body,
                dedupe_key=f"{base_dedupe_key}:coordinator",
                related_requirement_id=requirement.id,
                effective_date=requirement.due_date,
            )

            if await self.repository.insert_notification_if_absent(coordinator_notification):
                count += 1

        return count

    async def _create_certificate_notification(
        self,
        record: VerifiedCertificateRecord,
        notification_type: NotificationType,
        process_date: date,
        days_until_expiration: Optional[int] = None,
    ) -> int:
        """
        Create certificate notifications for both employee and Coordinator.

        Per OPS-02: Coordinator always receives notifications.

        Returns:
            Number of notifications created (0, 1, or 2)
        """
        count = 0

        # Include days_until_expiration in dedupe key for interval-specific notifications
        dedupe_suffix = f":{days_until_expiration}" if days_until_expiration else ""
        base_dedupe_key = make_dedupe_key(
            notification_type, record.id, process_date
        ) + dedupe_suffix

        # Resolve employee name for coordinator message
        employee_name = await self._get_employee_name(record.employee_id)

        # Build notification content
        subject, body = self._build_certificate_message(
            record, notification_type, days_until_expiration
        )

        # 1. Create notification for the employee
        # effective_date is the expiration date - the logical trigger date for reporting
        employee_notification = NotificationEvent(
            id=0,
            notification_type=notification_type,
            recipient_employee_id=record.employee_id,
            subject=subject,
            body=body,
            dedupe_key=base_dedupe_key,
            related_certificate_id=record.id,
            effective_date=record.expiration_date,
        )

        if await self.repository.insert_notification_if_absent(employee_notification):
            count += 1

        # 2. Create notification for Coordinator (if exists and is different from employee)
        coordinator_id = await self._get_coordinator_id()
        if coordinator_id and coordinator_id != record.employee_id:
            # Build Coordinator-specific message
            coord_subject, coord_body = self._build_certificate_message_for_coordinator(
                record, notification_type, days_until_expiration,
                employee_name=employee_name,
            )

            coordinator_notification = NotificationEvent(
                id=0,
                notification_type=notification_type,
                recipient_employee_id=coordinator_id,
                subject=coord_subject,
                body=coord_body,
                dedupe_key=f"{base_dedupe_key}:coordinator",
                related_certificate_id=record.id,
                effective_date=record.expiration_date,
            )

            if await self.repository.insert_notification_if_absent(coordinator_notification):
                count += 1

        return count

    def _build_requirement_message(
        self,
        requirement: RequirementAssignment,
        notification_type: NotificationType,
        days_until_due: Optional[int] = None,
        cert_type_name: str = "certificate",
    ) -> tuple[str, str]:
        """Build subject and body for requirement notification (employee version)."""
        if notification_type == NotificationType.REQUIREMENT_DUE_TOMORROW:
            subject = f"Requirement Due Tomorrow: {cert_type_name}"
            body = (
                f"Your {cert_type_name} requirement is due tomorrow ({requirement.due_date}).\n"
                f"Please upload your certificate document as soon as possible."
            )
        elif notification_type == NotificationType.REQUIREMENT_DUE_SOON:
            if days_until_due == 0:
                subject = f"Requirement Due Today: {cert_type_name}"
                body = (
                    f"Your {cert_type_name} requirement is due today ({requirement.due_date}).\n"
                    f"Please upload your certificate document today to stay compliant."
                )
            else:
                days_text = f" ({days_until_due} days)" if days_until_due else ""
                subject = f"Upcoming Requirement: {cert_type_name} Due {requirement.due_date}{days_text}"
                body = (
                    f"You have a {cert_type_name} requirement due on {requirement.due_date}.\n"
                )
                if days_until_due:
                    body += f"This is your {days_until_due}-day reminder.\n"
                body += f"Please ensure you submit your {cert_type_name} document before the deadline."
        elif notification_type == NotificationType.REQUIREMENT_OVERDUE:
            subject = f"OVERDUE: {cert_type_name} Requirement Past Due"
            body = (
                f"Your {cert_type_name} requirement was due on {requirement.due_date} and is now overdue.\n"
                f"Please contact your manager and submit your certificate immediately."
            )
        else:
            subject = f"{cert_type_name} Requirement Update"
            body = f"There is an update regarding your {cert_type_name} requirement."

        return subject, body

    def _build_requirement_message_for_coordinator(
        self,
        requirement: RequirementAssignment,
        notification_type: NotificationType,
        days_until_due: Optional[int] = None,
        employee_name: str = "Unknown Employee",
        cert_type_name: str = "certificate",
    ) -> tuple[str, str]:
        """Build subject and body for requirement notification (Coordinator version)."""
        if notification_type == NotificationType.REQUIREMENT_DUE_TOMORROW:
            subject = f"[Coordinator] {cert_type_name} Due Tomorrow - {employee_name}"
            body = (
                f"{employee_name} has a {cert_type_name} requirement due tomorrow ({requirement.due_date}).\n"
                f"Please follow up to ensure compliance."
            )
        elif notification_type == NotificationType.REQUIREMENT_DUE_SOON:
            if days_until_due == 0:
                subject = f"[Coordinator] {cert_type_name} Due Today - {employee_name}"
                body = (
                    f"{employee_name} has a {cert_type_name} requirement due today ({requirement.due_date}).\n"
                    f"Please follow up to ensure compliance."
                )
            else:
                days_text = f" ({days_until_due} days)" if days_until_due else ""
                subject = f"[Coordinator] Upcoming {cert_type_name} - {employee_name}{days_text}"
                body = (
                    f"{employee_name} has a {cert_type_name} requirement due on {requirement.due_date}.\n"
                )
                if days_until_due:
                    body += f"This is the {days_until_due}-day reminder.\n"
                body += "Please monitor for compliance."
        elif notification_type == NotificationType.REQUIREMENT_OVERDUE:
            subject = f"[Coordinator] OVERDUE {cert_type_name} - {employee_name}"
            body = (
                f"{employee_name} has an overdue {cert_type_name} requirement (was due {requirement.due_date}).\n"
                f"Immediate follow-up required for compliance."
            )
        else:
            subject = f"[Coordinator] {cert_type_name} Update - {employee_name}"
            body = f"There is an update regarding a {cert_type_name} requirement for {employee_name}."

        return subject, body

    def _build_certificate_message(
        self,
        record: VerifiedCertificateRecord,
        notification_type: NotificationType,
        days_until_expiration: Optional[int] = None,
    ) -> tuple[str, str]:
        """Build subject and body for certificate notification (employee version)."""
        cert_name = record.certificate_type or "Certificate"

        if notification_type == NotificationType.CERTIFICATE_EXPIRING_SOON:
            days_text = f" ({days_until_expiration} days)" if days_until_expiration else ""
            subject = f"Certificate Expiring Soon: {cert_name}{days_text}"
            body = f"Your {cert_name} will expire on {record.expiration_date}.\n"
            if days_until_expiration:
                body += f"This is your {days_until_expiration}-day reminder.\n"
            body += "Please begin the renewal process to maintain compliance."
        elif notification_type == NotificationType.CERTIFICATE_EXPIRED:
            subject = f"EXPIRED: {cert_name} Has Expired"
            body = (
                f"Your {cert_name} expired on {record.expiration_date}.\n"
                f"Please contact your manager and begin the renewal process immediately."
            )
        else:
            subject = f"Certificate Update: {cert_name}"
            body = f"There is an update regarding your {cert_name}."

        return subject, body

    def _build_certificate_message_for_coordinator(
        self,
        record: VerifiedCertificateRecord,
        notification_type: NotificationType,
        days_until_expiration: Optional[int] = None,
        employee_name: str = "Unknown Employee",
    ) -> tuple[str, str]:
        """Build subject and body for certificate notification (Coordinator version)."""
        cert_name = record.certificate_type or "Certificate"

        if notification_type == NotificationType.CERTIFICATE_EXPIRING_SOON:
            days_text = f" ({days_until_expiration} days)" if days_until_expiration else ""
            subject = f"[Coordinator] Certificate Expiring - {employee_name}{days_text}"
            body = (
                f"{employee_name}'s {cert_name} will expire on {record.expiration_date}.\n"
            )
            if days_until_expiration:
                body += f"This is the {days_until_expiration}-day reminder.\n"
            body += "Please monitor for renewal compliance."
        elif notification_type == NotificationType.CERTIFICATE_EXPIRED:
            subject = f"[Coordinator] EXPIRED Certificate - {employee_name}"
            body = (
                f"{employee_name}'s {cert_name} expired on {record.expiration_date}.\n"
                f"Immediate follow-up required for compliance."
            )
        else:
            subject = f"[Coordinator] Certificate Update - {employee_name}"
            body = f"There is an update regarding {employee_name}'s {cert_name}."

        return subject, body
