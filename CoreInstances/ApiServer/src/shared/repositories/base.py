"""
Base repository class for the City of Laredo Certificate Management System.

Provides common functionality for all domain repositories.
"""

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """
    Base class for domain-specific repositories.

    Provides:
    - Session management
    - Common query patterns
    - Transaction handling helpers

    All domain repositories should inherit from this class.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: AsyncSession from SQLAlchemy
        """
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """Get the database session."""
        return self._session

    async def flush(self) -> None:
        """Flush pending changes to the database."""
        await self._session.flush()

    async def refresh(self, instance) -> None:
        """Refresh an instance from the database."""
        await self._session.refresh(instance)
