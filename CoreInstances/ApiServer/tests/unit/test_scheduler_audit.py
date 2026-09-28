"""
Smoke test for the shared audit() helper signature used by the scheduler
notification batch (BackgroundProcessingInstances/SchedulerNotificationWorker).

A full end-to-end test of scheduler.py would require Redis, sessions, and
notification fixtures (deferred to PR0 fixtures work). This smoke test
pins the contract that matters here: the exact kwargs scheduler.py
passes to audit() must continue to be accepted by the helper. If a
refactor changes audit()'s signature in a way that breaks the scheduler
call site, this test fails immediately rather than at the next 6am
notification batch.

See: BackgroundProcessingInstances/SchedulerNotificationWorker/src/scheduler.py
     around the `await audit(repository=repo, action="notification_batch_sent", ...)`
     call following batch send completion.

TODO (PR0): once a redis + session fixture lands, add a scheduler-level
integration test that exercises the full notification cycle including
the audit emission path.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.shared.audit import audit
from src.shared.models import AuditActorType


@pytest.mark.asyncio
async def test_audit_helper_accepts_scheduler_call_signature() -> None:
    """audit() must accept the exact kwargs scheduler.py passes; the call
    must reach repository.create_audit_log with actor_type=SYSTEM."""
    repo = AsyncMock()
    repo.create_audit_log = AsyncMock(side_effect=lambda log: log)

    cycle_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    log = await audit(
        repository=repo,
        action="notification_batch_sent",
        target_type="notification_batch",
        target_id=cycle_id,
        details={
            "digests_sent": 5,
            "digests_failed": 0,
            "total_notifications": 12,
            "recipients_total": 5,
        },
        source_service="scheduler-worker",
        outcome="Success",
    )

    repo.create_audit_log.assert_awaited_once()
    # No actor was passed → must be a SYSTEM action with no employee_id.
    assert log.actor_type == AuditActorType.SYSTEM
    assert log.employee_id is None
    assert log.action == "notification_batch_sent"
    assert log.target_type == "notification_batch"
    assert log.target_id == cycle_id
    assert log.source_service == "scheduler-worker"
    assert log.outcome == "Success"


@pytest.mark.asyncio
async def test_audit_helper_partial_outcome_for_failed_digests() -> None:
    """When some digests fail, scheduler passes outcome='Partial'. Pin that."""
    repo = AsyncMock()
    repo.create_audit_log = AsyncMock(side_effect=lambda log: log)

    log = await audit(
        repository=repo,
        action="notification_batch_sent",
        target_type="notification_batch",
        target_id="20260419T060000Z",
        details={
            "digests_sent": 3,
            "digests_failed": 2,
            "total_notifications": 8,
            "recipients_total": 5,
        },
        source_service="scheduler-worker",
        outcome="Partial",
    )

    assert log.outcome == "Partial"
    # Secret-key scrubber must not strip benign telemetry keys.
    assert log.details == {
        "digests_sent": 3,
        "digests_failed": 2,
        "total_notifications": 8,
        "recipients_total": 5,
    }
