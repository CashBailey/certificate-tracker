"""
Real clock implementation for production use.
"""

from datetime import date, datetime, timezone


class RealClock:
    """Production clock implementation using system time."""

    def now(self) -> datetime:
        """Return current UTC datetime."""
        return datetime.now(timezone.utc)

    def today(self) -> date:
        """Return current UTC date."""
        return datetime.now(timezone.utc).date()
