"""
GAL (Global Address List) provider for city employee lookup.

Provides a protocol-based interface for querying the GAL directory
to determine if an email sender is a known city employee (INV-09).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from shared.orm_models import GALDirectoryORM


@dataclass
class PersonInfo:
    """Information about a person from the GAL directory."""

    first_name: str
    last_name: str
    email: str


@runtime_checkable
class GALProvider(Protocol):
    """Protocol for GAL directory lookups."""

    async def is_person(self, email: str) -> bool: ...

    async def get_person_info(self, email: str) -> Optional[PersonInfo]: ...

    async def is_in_gal(self, email: str) -> bool: ...


class DatabaseGALProvider:
    """GAL provider backed by the gal_directory database table."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def is_person(self, email: str) -> bool:
        """Check if email belongs to a person (not a distribution list)."""
        async with self.session_factory() as session:
            stmt = select(GALDirectoryORM.is_person).where(
                GALDirectoryORM.email == email.lower()
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row is True

    async def get_person_info(self, email: str) -> Optional[PersonInfo]:
        """Get person info from GAL. Returns None if not found or not a person."""
        async with self.session_factory() as session:
            stmt = select(GALDirectoryORM).where(
                GALDirectoryORM.email == email.lower(),
                GALDirectoryORM.is_person.is_(True),
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if not row:
                return None
            return PersonInfo(
                first_name=row.first_name,
                last_name=row.last_name,
                email=row.email,
            )

    async def is_in_gal(self, email: str) -> bool:
        """Check if email exists in GAL (regardless of is_person flag)."""
        async with self.session_factory() as session:
            stmt = select(GALDirectoryORM.id).where(
                GALDirectoryORM.email == email.lower()
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None
