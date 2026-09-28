"""
Unit tests for notification generation logic.

Tests notification-related pure functions and logic patterns.
The actual NotificationGenerator lives in the scheduler worker, but we test
the shared notification models and patterns here.
"""

import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.shared.models import (
    NotificationType,
    NotificationEvent,
)


# ============================================================================
# These are the pure functions from the scheduler worker's notifications.py
# We duplicate them here to test the logic without cross-container imports.
# Default values match the DB seed in notifications.alert_configuration.
# ============================================================================

DUE_REMINDER_DAYS = [90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1]
EXPIRATION_REMINDER_DAYS = [90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1]


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


# ============================================================================
# Tests
# ============================================================================


class TestMakeDedupeKey:
    """Tests for make_dedupe_key function."""

    def test_creates_deterministic_key(self):
        """Same inputs should produce same dedupe key."""
        key1 = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=123,
            date_ref=date(2026, 2, 4),
        )
        key2 = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=123,
            date_ref=date(2026, 2, 4),
        )
        assert key1 == key2

    def test_different_types_different_keys(self):
        """Different notification types should produce different keys."""
        key1 = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=123,
            date_ref=date(2026, 2, 4),
        )
        key2 = make_dedupe_key(
            NotificationType.REQUIREMENT_OVERDUE,
            entity_id=123,
            date_ref=date(2026, 2, 4),
        )
        assert key1 != key2

    def test_different_entities_different_keys(self):
        """Different entity IDs should produce different keys."""
        key1 = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=123,
            date_ref=date(2026, 2, 4),
        )
        key2 = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=456,
            date_ref=date(2026, 2, 4),
        )
        assert key1 != key2

    def test_different_dates_different_keys(self):
        """Different dates should produce different keys."""
        key1 = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=123,
            date_ref=date(2026, 2, 4),
        )
        key2 = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=123,
            date_ref=date(2026, 2, 5),
        )
        assert key1 != key2

    def test_key_format_includes_all_components(self):
        """Dedupe key should include type, entity, and date."""
        key = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=123,
            date_ref=date(2026, 2, 4),
        )
        # Key contains the enum value (CamelCase), entity ID, and date
        assert NotificationType.REQUIREMENT_DUE_SOON.value in key
        assert "123" in key
        assert "2026-02-04" in key

    def test_key_is_unique_per_interval(self):
        """Adding interval suffix creates unique keys per reminder."""
        base_key = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=123,
            date_ref=date(2026, 2, 4),
        )

        # Keys with different day suffixes should be different
        key_90 = f"{base_key}:90"
        key_60 = f"{base_key}:60"
        key_30 = f"{base_key}:30"

        assert key_90 != key_60 != key_30
        assert all(base_key in k for k in [key_90, key_60, key_30])


class TestReminderIntervals:
    """Tests for reminder interval constants."""

    def test_due_reminder_days_match_default_intervals(self):
        """Due reminders should match the default managed interval list."""
        assert DUE_REMINDER_DAYS == [90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1]

    def test_expiration_reminder_days_match_default_intervals(self):
        """Expiration reminders should match the default managed interval list."""
        assert EXPIRATION_REMINDER_DAYS == [90, 60, 30, 15, 7, 6, 5, 4, 3, 2, 1]

    def test_reminder_days_are_descending(self):
        """Reminder days should be in descending order."""
        assert DUE_REMINDER_DAYS == sorted(DUE_REMINDER_DAYS, reverse=True)
        assert EXPIRATION_REMINDER_DAYS == sorted(EXPIRATION_REMINDER_DAYS, reverse=True)


class TestNotificationTypes:
    """Tests for NotificationType enum values."""

    def test_requirement_notification_types_exist(self):
        """Requirement-related notification types should exist."""
        assert hasattr(NotificationType, "REQUIREMENT_DUE_SOON")
        assert hasattr(NotificationType, "REQUIREMENT_DUE_TOMORROW")
        assert hasattr(NotificationType, "REQUIREMENT_OVERDUE")

    def test_certificate_notification_types_exist(self):
        """Certificate-related notification types should exist."""
        assert hasattr(NotificationType, "CERTIFICATE_EXPIRING_SOON")
        assert hasattr(NotificationType, "CERTIFICATE_EXPIRED")

    def test_notification_types_have_string_values(self):
        """Notification types should have string values for dedupe keys."""
        # All types should have string values (for serialization)
        for ntype in NotificationType:
            assert isinstance(ntype.value, str)
            assert len(ntype.value) > 0


class TestNotificationEvent:
    """Tests for NotificationEvent model."""

    @pytest.fixture
    def sample_notification(self):
        """Create a sample notification event."""
        return NotificationEvent(
            id=1,
            notification_type=NotificationType.REQUIREMENT_DUE_SOON,
            recipient_employee_id=100,
            subject="Test Subject",
            body="Test Body",
            dedupe_key="test_key",
            related_requirement_id=50,
            effective_date=date(2026, 3, 15),
        )

    def test_notification_has_required_fields(self, sample_notification):
        """Notification should have all required fields."""
        assert sample_notification.notification_type is not None
        assert sample_notification.recipient_employee_id is not None
        assert sample_notification.subject is not None
        assert sample_notification.body is not None
        assert sample_notification.dedupe_key is not None

    def test_notification_has_optional_fields(self, sample_notification):
        """Notification should support optional relationship fields."""
        assert sample_notification.related_requirement_id == 50
        assert sample_notification.effective_date == date(2026, 3, 15)


class TestDedupeKeyIdempotency:
    """Tests for deduplication key idempotency patterns."""

    def test_same_notification_same_key(self):
        """Identical notification parameters produce identical keys."""
        params = {
            "notification_type": NotificationType.REQUIREMENT_DUE_SOON,
            "entity_id": 123,
            "date_ref": date(2026, 2, 4),
        }

        keys = [make_dedupe_key(**params) for _ in range(100)]
        assert len(set(keys)) == 1  # All keys identical

    def test_key_survives_serialization(self):
        """Dedupe key can be stored and compared as string."""
        key = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=123,
            date_ref=date(2026, 2, 4),
        )

        # Simulate storing and retrieving from database
        stored = str(key)
        retrieved = stored

        assert retrieved == key

    def test_key_format_is_predictable(self):
        """Dedupe key format is predictable for external verification."""
        key = make_dedupe_key(
            NotificationType.CERTIFICATE_EXPIRING_SOON,
            entity_id=456,
            date_ref=date(2026, 5, 15),
        )

        # Format: {type.value}:{id}:{date}
        expected = f"{NotificationType.CERTIFICATE_EXPIRING_SOON.value}:456:2026-05-15"
        assert key == expected


class TestNotificationSchedulingLogic:
    """Tests for notification scheduling logic patterns."""

    @pytest.fixture
    def today(self):
        """Fixed reference date for tests."""
        return date(2026, 2, 4)

    def test_90_day_reminder_target_date(self, today):
        """90-day reminder targets 90 days from today."""
        target = today + timedelta(days=90)
        assert target == date(2026, 5, 5)

    def test_60_day_reminder_target_date(self, today):
        """60-day reminder targets 60 days from today."""
        target = today + timedelta(days=60)
        assert target == date(2026, 4, 5)

    def test_30_day_reminder_target_date(self, today):
        """30-day reminder targets 30 days from today."""
        target = today + timedelta(days=30)
        assert target == date(2026, 3, 6)

    def test_due_tomorrow_target_date(self, today):
        """Due tomorrow reminder targets tomorrow."""
        target = today + timedelta(days=1)
        assert target == date(2026, 2, 5)

    def test_overdue_lookback_window(self, today):
        """Overdue check looks back 90 days."""
        lookback_start = today - timedelta(days=90)
        lookback_end = today - timedelta(days=1)

        assert lookback_start == date(2025, 11, 6)
        assert lookback_end == date(2026, 2, 3)


class TestBackfillLogic:
    """Tests for cursor-based backfill logic patterns."""

    def test_backfill_date_range(self):
        """Backfill should process all dates between cursor and today."""
        last_success = date(2026, 2, 1)
        current = date(2026, 2, 4)

        # Calculate dates to process: last_success + 1 through current
        process_start = last_success + timedelta(days=1)
        dates_to_process = []
        d = process_start
        while d <= current:
            dates_to_process.append(d)
            d += timedelta(days=1)

        assert dates_to_process == [
            date(2026, 2, 2),
            date(2026, 2, 3),
            date(2026, 2, 4),
        ]

    def test_no_backfill_needed_when_current(self):
        """No backfill when cursor is yesterday."""
        last_success = date(2026, 2, 3)  # Yesterday
        current = date(2026, 2, 4)

        process_start = last_success + timedelta(days=1)
        dates_to_process = []
        d = process_start
        while d <= current:
            dates_to_process.append(d)
            d += timedelta(days=1)

        assert dates_to_process == [date(2026, 2, 4)]  # Only today

    def test_large_backfill_gap(self):
        """Should handle large gaps (e.g., weekend or holiday)."""
        last_success = date(2026, 1, 28)  # A week ago
        current = date(2026, 2, 4)

        process_start = last_success + timedelta(days=1)
        dates_to_process = []
        d = process_start
        while d <= current:
            dates_to_process.append(d)
            d += timedelta(days=1)

        # Should have 7 days
        assert len(dates_to_process) == 7
        assert dates_to_process[0] == date(2026, 1, 29)
        assert dates_to_process[-1] == date(2026, 2, 4)


class TestCoordinatorNotificationLogic:
    """Tests for Coordinator notification patterns (per OPS-02)."""

    def test_coordinator_dedupe_key_is_distinct(self):
        """Coordinator notification should have distinct dedupe key."""
        base_key = make_dedupe_key(
            NotificationType.REQUIREMENT_DUE_SOON,
            entity_id=123,
            date_ref=date(2026, 2, 4),
        )

        employee_key = f"{base_key}:30"  # With interval
        coordinator_key = f"{base_key}:30:coordinator"

        assert employee_key != coordinator_key
        assert "coordinator" in coordinator_key

    def test_should_skip_coordinator_if_same_as_employee(self):
        """Logic: if coordinator_id == employee_id, skip coordinator notification."""
        coordinator_id = 100
        employee_id = 100

        should_create_coordinator_notification = (
            coordinator_id is not None and coordinator_id != employee_id
        )

        assert should_create_coordinator_notification is False

    def test_should_include_coordinator_if_different(self):
        """Logic: if coordinator_id != employee_id, include coordinator notification."""
        coordinator_id = 999
        employee_id = 100

        should_create_coordinator_notification = (
            coordinator_id is not None and coordinator_id != employee_id
        )

        assert should_create_coordinator_notification is True

    def test_should_skip_coordinator_if_none(self):
        """Logic: if no coordinator exists, skip coordinator notification."""
        coordinator_id = None
        employee_id = 100

        should_create_coordinator_notification = (
            coordinator_id is not None and coordinator_id != employee_id
        )

        assert should_create_coordinator_notification is False


class TestFilteringRules:
    """Tests for notification filtering rule logic."""

    def test_satisfied_requirement_skipped(self):
        """Satisfied requirements should not generate notifications."""
        satisfied_by_id = 999  # Has been satisfied

        should_notify = satisfied_by_id is None

        assert should_notify is False

    def test_waived_requirement_skipped(self):
        """Waived requirements should not generate notifications."""
        waived_at = date(2026, 1, 15)  # Has been waived

        should_notify = waived_at is None

        assert should_notify is False

    def test_pending_requirement_notified(self):
        """Pending (unsatisfied, unwaived) requirements should notify."""
        satisfied_by_id = None
        waived_at = None

        should_notify = satisfied_by_id is None and waived_at is None

        assert should_notify is True

    def test_combined_filter_logic(self):
        """Combined filter: notify only if not satisfied AND not waived."""
        test_cases = [
            (None, None, True),      # Not satisfied, not waived -> notify
            (999, None, False),      # Satisfied -> skip
            (None, date(2026,1,1), False),  # Waived -> skip
            (999, date(2026,1,1), False),   # Both -> skip
        ]

        for satisfied_by_id, waived_at, expected in test_cases:
            should_notify = satisfied_by_id is None and waived_at is None
            assert should_notify == expected, f"Failed for {satisfied_by_id}, {waived_at}"
