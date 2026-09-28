"""
Real UUID generator implementation for production use.
"""

import uuid
from uuid import UUID


class RealUuidGenerator:
    """Production UUID generator using Python's uuid4."""

    def generate(self) -> UUID:
        """Generate a new UUID."""
        return uuid.uuid4()
