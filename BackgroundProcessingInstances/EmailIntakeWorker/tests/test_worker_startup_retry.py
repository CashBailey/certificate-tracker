"""Startup resilience: initial IMAP connect must retry, not crash the process."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

with patch("src.worker.get_session_factory", MagicMock()):
    from src.worker import EmailIntakeWorker


def _make_worker(email_client) -> EmailIntakeWorker:
    with patch("src.worker.get_session_factory", MagicMock()):
        return EmailIntakeWorker(
            email_client=email_client,
            directory_lookup=MagicMock(),
            minio_client=MagicMock(),
            redis_client=MagicMock(),
            poll_interval=60,
        )


class TestStartupConnectRetry:
    def test_initial_connect_failure_retries_with_backoff(self):
        """Two failed connects then success: worker keeps going, backoff grows."""
        email_client = MagicMock()
        email_client.connect.side_effect = [
            OSError("Temporary failure in name resolution"),
            OSError("Temporary failure in name resolution"),
            None,
        ]
        worker = _make_worker(email_client)

        sleep_delays = []

        async def fake_sleep(seconds):
            sleep_delays.append(seconds)

        async def stop_after_connect(*_a, **_kw):
            worker._running = False
            return 0

        worker.poll_once = stop_after_connect

        with patch("src.worker.asyncio.sleep", side_effect=fake_sleep):
            asyncio.run(worker.run())

        assert email_client.connect.call_count == 3
        assert sleep_delays[:2] == [30.0, 60.0], "exponential backoff between retries"
        email_client.disconnect.assert_called()

    def test_stop_during_startup_retries_exits_cleanly(self):
        """stop() while IMAP is down must end run() instead of retrying forever."""
        email_client = MagicMock()
        email_client.connect.side_effect = OSError("unreachable")
        worker = _make_worker(email_client)

        async def fake_sleep(_seconds):
            worker.stop()

        with patch("src.worker.asyncio.sleep", side_effect=fake_sleep):
            asyncio.run(worker.run())

        assert email_client.connect.call_count == 1

    def test_immediate_connect_success_does_not_sleep(self):
        email_client = MagicMock()
        email_client.connect.return_value = None
        worker = _make_worker(email_client)

        sleep_delays = []

        async def fake_sleep(seconds):
            sleep_delays.append(seconds)

        async def stop_after_connect(*_a, **_kw):
            worker._running = False
            return 0

        worker.poll_once = stop_after_connect

        with patch("src.worker.asyncio.sleep", side_effect=fake_sleep):
            asyncio.run(worker.run())

        assert email_client.connect.call_count == 1
        assert sleep_delays == []


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
