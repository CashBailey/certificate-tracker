"""
Unit tests for notification read-state repository methods.

Verifies that mark_notification_read, count_unread_notifications,
list_notifications_for_user, and mark_all_notifications_read use the
`read` / `read_at` columns (not the `delivered` / `delivered_at` columns).
"""

import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.shared.models import NotificationEvent, NotificationType
from src.shared.orm_models import NotificationEventORM
from src.shared.repository import SqlRepository


# ==================== Helpers ====================


def _make_notification_orm(**overrides):
    """Create a NotificationEventORM-like mock with sensible defaults."""
    defaults = dict(
        id=1,
        notification_type="RequirementDueSoon",
        recipient_employee_id=100,
        subject="Test",
        body="Test body",
        dedupe_key="test:1:2026-03-15",
        related_requirement_id=None,
        related_certificate_id=None,
        effective_date=date(2026, 3, 15),
        delivered=False,
        delivered_at=None,
        read=False,
        read_at=None,
        created_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _get_update_values(session_mock):
    """Extract the values dict from an UPDATE statement passed to session.execute."""
    stmt = session_mock.execute.call_args[0][0]
    # SQLAlchemy Update stores values in _values as {Column: BindParameter}
    result = {}
    for col, bind in stmt._values.items():
        result[col.key] = bind.value
    return result


def _make_session_for_scalars(*orm_objects):
    """Create a mock session whose execute().scalars() returns the given objects."""
    session = AsyncMock()
    # We need scalars() to be a sync method that returns an iterable
    execute_result = MagicMock()
    execute_result.scalars.return_value = list(orm_objects)
    session.execute.return_value = execute_result
    return session


def _make_session_for_scalar(value):
    """Create a mock session whose execute().scalar() returns a single value."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar.return_value = value
    session.execute.return_value = execute_result
    return session


def _make_session_for_rowcount(count):
    """Create a mock session whose execute().rowcount returns the given count."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.rowcount = count
    session.execute.return_value = execute_result
    return session


# ==================== mark_notification_read ====================


class TestMarkNotificationRead:
    """Tests for SqlRepository.mark_notification_read."""

    @pytest.mark.asyncio
    async def test_sets_read_true_and_read_at(self):
        """mark_notification_read should set read=True and read_at=now()."""
        session = AsyncMock()
        repo = SqlRepository(session)

        await repo.mark_notification_read(notification_id=42)

        values = _get_update_values(session)
        assert values["read"] is True
        assert "read_at" in values
        assert isinstance(values["read_at"], datetime)

    @pytest.mark.asyncio
    async def test_does_not_touch_delivered(self):
        """mark_notification_read must NOT modify the delivered column."""
        session = AsyncMock()
        repo = SqlRepository(session)

        await repo.mark_notification_read(notification_id=42)

        values = _get_update_values(session)
        assert "delivered" not in values
        assert "delivered_at" not in values

    @pytest.mark.asyncio
    async def test_read_at_is_utc_now(self):
        """read_at timestamp should be close to utcnow."""
        session = AsyncMock()
        repo = SqlRepository(session)

        before = datetime.now(timezone.utc)
        await repo.mark_notification_read(notification_id=42)
        after = datetime.now(timezone.utc)

        values = _get_update_values(session)
        assert before <= values["read_at"] <= after


# ==================== count_unread_notifications ====================


class TestCountUnreadNotifications:
    """Tests for SqlRepository.count_unread_notifications."""

    @pytest.mark.asyncio
    async def test_filters_on_read_not_delivered(self):
        """count_unread should filter on read=False, not delivered=False."""
        session = _make_session_for_scalar(5)
        repo = SqlRepository(session)

        await repo.count_unread_notifications(employee_id=100)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "read" in compiled.lower()

    @pytest.mark.asyncio
    async def test_returns_count(self):
        """Should return the scalar count value."""
        session = _make_session_for_scalar(5)
        repo = SqlRepository(session)

        result = await repo.count_unread_notifications(employee_id=100)
        assert result == 5

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self):
        """Should return 0 when scalar returns None."""
        session = _make_session_for_scalar(None)
        repo = SqlRepository(session)

        result = await repo.count_unread_notifications(employee_id=100)
        assert result == 0


# ==================== list_notifications_for_user ====================


class TestListNotificationsForUser:
    """Tests for SqlRepository.list_notifications_for_user."""

    @pytest.mark.asyncio
    async def test_unread_only_filters_on_read(self):
        """unread_only=True should filter on read=False, not delivered=False."""
        orm1 = _make_notification_orm(id=1, read=False)
        session = _make_session_for_scalars(orm1)
        repo = SqlRepository(session)

        await repo.list_notifications_for_user(employee_id=100, unread_only=True)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "read" in compiled.lower()

    @pytest.mark.asyncio
    async def test_returns_all_when_unread_only_false(self):
        """unread_only=False should return all notifications."""
        orm1 = _make_notification_orm(id=1, read=False)
        orm2 = _make_notification_orm(id=2, read=True)
        session = _make_session_for_scalars(orm1, orm2)
        repo = SqlRepository(session)

        results = await repo.list_notifications_for_user(
            employee_id=100, unread_only=False
        )
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_returns_notification_events(self):
        """Should return NotificationEvent domain objects."""
        orm1 = _make_notification_orm(id=1)
        session = _make_session_for_scalars(orm1)
        repo = SqlRepository(session)

        results = await repo.list_notifications_for_user(employee_id=100)
        assert len(results) == 1
        assert isinstance(results[0], NotificationEvent)

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        """Should pass limit to the query."""
        session = _make_session_for_scalars()
        repo = SqlRepository(session)

        await repo.list_notifications_for_user(employee_id=100, limit=5)
        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "5" in compiled


# ==================== mark_all_notifications_read ====================


class TestMarkAllNotificationsRead:
    """Tests for SqlRepository.mark_all_notifications_read."""

    @pytest.mark.asyncio
    async def test_sets_read_true_on_all_unread(self):
        """mark_all_notifications_read should set read=True, read_at on unread."""
        session = _make_session_for_rowcount(3)
        repo = SqlRepository(session)

        await repo.mark_all_notifications_read(employee_id=100)

        values = _get_update_values(session)
        assert values["read"] is True
        assert "read_at" in values

    @pytest.mark.asyncio
    async def test_does_not_touch_delivered(self):
        """mark_all_notifications_read must NOT modify delivered columns."""
        session = _make_session_for_rowcount(3)
        repo = SqlRepository(session)

        await repo.mark_all_notifications_read(employee_id=100)

        values = _get_update_values(session)
        assert "delivered" not in values
        assert "delivered_at" not in values

    @pytest.mark.asyncio
    async def test_returns_rowcount(self):
        """Should return number of rows updated."""
        session = _make_session_for_rowcount(3)
        repo = SqlRepository(session)

        count = await repo.mark_all_notifications_read(employee_id=100)
        assert count == 3

    @pytest.mark.asyncio
    async def test_filters_on_read_false(self):
        """WHERE clause should filter read=False (not delivered=False)."""
        session = _make_session_for_rowcount(0)
        repo = SqlRepository(session)

        await repo.mark_all_notifications_read(employee_id=100)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "read" in compiled.lower()

    @pytest.mark.asyncio
    async def test_read_at_is_utc_now(self):
        """read_at timestamp should be close to utcnow."""
        session = _make_session_for_rowcount(1)
        repo = SqlRepository(session)

        before = datetime.now(timezone.utc)
        await repo.mark_all_notifications_read(employee_id=100)
        after = datetime.now(timezone.utc)

        values = _get_update_values(session)
        assert before <= values["read_at"] <= after


# ==================== ORM-to-model mapping ====================


class TestNotificationOrmToModel:
    """Tests that _notification_orm_to_model maps read/read_at correctly."""

    def test_maps_read_fields(self):
        """Domain model should include read and read_at from ORM."""
        session = AsyncMock()
        repo = SqlRepository(session)

        now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        orm_obj = _make_notification_orm(read=True, read_at=now)

        model = repo._notification_orm_to_model(orm_obj)

        assert model.read is True
        assert model.read_at == now

    def test_maps_unread_defaults(self):
        """Unread notification should have read=False, read_at=None."""
        session = AsyncMock()
        repo = SqlRepository(session)

        orm_obj = _make_notification_orm(read=False, read_at=None)

        model = repo._notification_orm_to_model(orm_obj)

        assert model.read is False
        assert model.read_at is None

    def test_read_and_delivered_are_independent(self):
        """read and delivered should be mapped independently."""
        session = AsyncMock()
        repo = SqlRepository(session)

        # delivered=True but read=False (notification sent but not opened)
        orm_obj = _make_notification_orm(
            delivered=True,
            delivered_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
            read=False,
            read_at=None,
        )

        model = repo._notification_orm_to_model(orm_obj)

        assert model.delivered is True
        assert model.read is False
