"""
insert_notification_if_absent must isolate a dedupe collision to a SAVEPOINT.

A plain session.rollback() would discard every notification already flushed in
the same daily-generation batch, silently truncating that day's notifications
at the first duplicate. This guards against a regression back to that behavior.
"""

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.shared.repository import SqlRepository
from src.shared.models import NotificationEvent, NotificationType


def _notification() -> NotificationEvent:
    return NotificationEvent(
        id=0,
        notification_type=NotificationType.REQUIREMENT_DUE_SOON,
        recipient_employee_id=42,
        subject="s",
        body="b",
        dedupe_key="k",
        related_requirement_id=None,
        related_certificate_id=None,
        effective_date=date(2026, 7, 12),
    )


class _SavepointSession:
    """Records begin_nested / rollback / flush calls; flush can raise."""

    def __init__(self, flush_raises: bool):
        self._flush_raises = flush_raises
        self.begin_nested_called = 0
        self.rollback_called = 0
        self.add = MagicMock()

    def begin_nested(self):
        self.begin_nested_called += 1

        @asynccontextmanager
        async def _cm():
            try:
                yield
            except IntegrityError:
                # A real savepoint rolls itself back and re-raises.
                raise

        return _cm()

    async def flush(self):
        if self._flush_raises:
            raise IntegrityError("dup", None, Exception("dup"))

    async def rollback(self):
        self.rollback_called += 1


@pytest.mark.asyncio
async def test_insert_returns_true_and_uses_savepoint_on_success():
    session = _SavepointSession(flush_raises=False)
    repo = SqlRepository(session)

    result = await repo.insert_notification_if_absent(_notification())

    assert result is True
    assert session.begin_nested_called == 1


@pytest.mark.asyncio
async def test_collision_returns_false_without_full_rollback():
    session = _SavepointSession(flush_raises=True)
    repo = SqlRepository(session)

    result = await repo.insert_notification_if_absent(_notification())

    assert result is False
    # The whole-transaction rollback (which would nuke the batch) must NOT happen.
    assert session.rollback_called == 0
    assert session.begin_nested_called == 1
