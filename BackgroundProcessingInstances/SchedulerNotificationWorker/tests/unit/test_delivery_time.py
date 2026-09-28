"""Digest delivery time must never produce hour=24 (CronTrigger crash)."""

import pytest

try:
    from src.scheduler import current_central_date, delivery_time
except Exception:  # heavy deps / relative imports unavailable outside the worker image
    delivery_time = None
    current_central_date = None

pytestmark = pytest.mark.skipif(
    delivery_time is None,
    reason="run inside the scheduler-worker image (needs apscheduler/redis/shared)",
)


@pytest.mark.parametrize(
    "send_hour,send_minute,expected",
    [
        (6, 0, (6, 15)),
        (23, 44, (23, 59)),   # last minute that stays same-day
        (23, 45, (0, 0)),     # rolls to next day - was hour=24 before the fix
        (23, 59, (0, 14)),
        (0, 0, (0, 15)),
    ],
)
def test_delivery_time_wraps_past_midnight(send_hour, send_minute, expected):
    assert delivery_time(send_hour, send_minute) == expected


def test_delivery_hour_is_always_a_valid_cron_hour():
    for hour in range(24):
        for minute in range(60):
            dh, dm = delivery_time(hour, minute)
            assert 0 <= dh <= 23
            assert 0 <= dm <= 59


def test_business_date_uses_central_time_near_utc_midnight():
    from datetime import datetime, timezone

    assert current_central_date(
        datetime(2026, 7, 13, 4, 30, tzinfo=timezone.utc),
    ).isoformat() == "2026-07-12"
