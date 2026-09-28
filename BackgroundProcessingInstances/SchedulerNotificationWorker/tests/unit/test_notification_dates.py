"""Notification date-boundary + wording correctness (day-0 due, expired window)."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from notifications import NotificationGenerator
    from shared.models import NotificationType, RequirementAssignment, RequirementStatus
except Exception:  # needs the `shared` package baked into the worker image
    NotificationGenerator = None

pytestmark = pytest.mark.skipif(
    NotificationGenerator is None,
    reason="run inside the scheduler-worker image (needs shared.models)",
)


def _gen(repo):
    return NotificationGenerator(repo, daily_overdue_enabled=True)


def _requirement(due: date):
    return RequirementAssignment(
        id=7, employee_id=1, certificate_type_id=5, due_date=due,
        status=RequirementStatus.NOT_STARTED, satisfied_by_id=None, waived_at=None,
    )


def test_due_today_message_says_today_not_tomorrow():
    gen = _gen(MagicMock())
    subject, body = gen._build_requirement_message(
        _requirement(date(2026, 7, 12)),
        NotificationType.REQUIREMENT_DUE_SOON,
        days_until_due=0,
        cert_type_name="CPR",
    )
    assert "today" in subject.lower()
    assert "tomorrow" not in body.lower()


def test_coordinator_due_today_message_says_today():
    gen = _gen(MagicMock())
    subject, body = gen._build_requirement_message_for_coordinator(
        _requirement(date(2026, 7, 12)),
        NotificationType.REQUIREMENT_DUE_SOON,
        days_until_due=0,
        employee_name="Jane Doe",
        cert_type_name="CPR",
    )
    assert "today" in subject.lower()
    assert "tomorrow" not in body.lower()


@pytest.mark.asyncio
async def test_expired_window_excludes_today():
    """A cert expiring == process_date is still valid today; window must end yesterday."""
    repo = AsyncMock()
    captured = {}

    async def _capture(start, end):
        captured["start"], captured["end"] = start, end
        return []

    repo.list_verified_records_expiring_between = AsyncMock(side_effect=_capture)
    gen = _gen(repo)
    gen.expiration_reminder_days = []  # skip the expiring-soon passes

    process_date = date(2026, 7, 12)
    await gen._generate_certificate_notifications(process_date)

    assert captured["end"] == date(2026, 7, 11), "EXPIRED window must end the day before process_date"


@pytest.mark.asyncio
async def test_due_today_pass_uses_due_soon_type():
    """The day-0 requirement pass must emit REQUIREMENT_DUE_SOON, not DUE_TOMORROW."""
    repo = AsyncMock()
    process_date = date(2026, 7, 12)

    async def _due_between(start, end):
        return [_requirement(process_date)] if (start, end) == (process_date, process_date) else []

    repo.list_requirements_due_between = AsyncMock(side_effect=_due_between)
    repo.get_employee_by_id = AsyncMock(return_value=None)
    repo.get_certificate_type_by_id = AsyncMock(return_value=None)
    repo.get_employees_by_role = AsyncMock(return_value=[])

    captured_types = []

    async def _insert(notification):
        captured_types.append(notification.notification_type)
        return True

    repo.insert_notification_if_absent = AsyncMock(side_effect=_insert)
    gen = _gen(repo)
    gen.due_reminder_days = []  # skip interval passes

    await gen._generate_requirement_notifications(process_date)

    assert NotificationType.REQUIREMENT_DUE_SOON in captured_types
    assert NotificationType.REQUIREMENT_DUE_TOMORROW not in captured_types


@pytest.mark.asyncio
async def test_day_one_interval_does_not_duplicate_tomorrow_notification():
    repo = AsyncMock()
    process_date = date(2026, 7, 12)
    requirement = _requirement(date(2026, 7, 13))

    async def _due_between(start, end):
        due_tomorrow = process_date.replace(day=13)
        return [requirement] if (start, end) == (due_tomorrow, due_tomorrow) else []

    repo.list_requirements_due_between = AsyncMock(side_effect=_due_between)
    repo.get_employee_by_id = AsyncMock(return_value=None)
    repo.get_certificate_type_by_id = AsyncMock(return_value=None)
    repo.get_employees_by_role = AsyncMock(return_value=[])
    captured_types = []

    async def _insert(notification):
        captured_types.append(notification.notification_type)
        return True

    repo.insert_notification_if_absent = AsyncMock(side_effect=_insert)
    gen = NotificationGenerator(repo, daily_overdue_enabled=False)
    gen.due_reminder_days = [1]

    await gen._generate_requirement_notifications(process_date)

    assert set(captured_types) == {NotificationType.REQUIREMENT_DUE_TOMORROW}
    assert len(captured_types) == 1
