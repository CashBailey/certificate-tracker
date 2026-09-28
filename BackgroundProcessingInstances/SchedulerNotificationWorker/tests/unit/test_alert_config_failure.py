"""Notification policy reads fail closed on database errors."""

from unittest.mock import AsyncMock

import pytest

try:
    from src.scheduler import SchedulerWorker
except Exception:
    SchedulerWorker = None

pytestmark = pytest.mark.skipif(
    SchedulerWorker is None,
    reason="run inside the scheduler-worker image",
)


@pytest.mark.asyncio
async def test_alert_config_query_failure_does_not_substitute_defaults():
    worker = SchedulerWorker.__new__(SchedulerWorker)
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await worker._load_alert_config(session)
