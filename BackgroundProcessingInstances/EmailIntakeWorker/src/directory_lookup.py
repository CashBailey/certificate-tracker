"""
Directory lookup for mapping email addresses to employee IDs.

GAL-aware lookup (INV-09): city-domain senders not in the GAL are silently
ignored. City-domain senders who ARE in the GAL but have no employee record
are auto-created.
"""

import logging
import os
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from shared.orm_models import EmployeeORM

try:
    from .gal_provider import DatabaseGALProvider, GALProvider
except ImportError:
    from gal_provider import DatabaseGALProvider, GALProvider


logger = logging.getLogger(__name__)


# Database connection setup
_engine = None
_session_factory = None


def get_database_url() -> str:
    """Get database URL from environment."""
    raw_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://laredo:laredo_dev_password@postgres:5432/laredo_certificates"
    )
    # Ensure asyncpg driver
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url


def get_session_factory() -> async_sessionmaker:
    """Get or create the session factory."""
    global _engine, _session_factory

    if _session_factory is None:
        from shared.tls import build_ssl_context
        ssl_ctx = build_ssl_context()
        _engine = create_async_engine(
            get_database_url(),
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            connect_args={"ssl": ssl_ctx} if ssl_ctx else {},
        )
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _session_factory


class DirectoryLookup:
    """
    GAL-aware directory lookup service for email-to-employee mapping.

    Decision logic:
      1. Non-city domain → ignore
      2. City domain + NOT in GAL → ignore
      3. City domain + in GAL + is_person=False → ignore
      4. City domain + in GAL + is_person=True + employee exists → return employee
      5. City domain + in GAL + is_person=True + no employee → auto-create
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        gal_provider: GALProvider,
        allowed_domain: Optional[str] = None,
    ):
        self.session_factory = session_factory
        self.gal_provider = gal_provider
        self.allowed_domain = allowed_domain or os.environ.get(
            "ALLOWED_EMAIL_DOMAIN", "ci.laredo.tx.us"
        )

    def _is_city_domain(self, email: str) -> bool:
        """Check if email is from the city domain."""
        if not self.allowed_domain:
            return True
        try:
            domain = email.lower().split("@")[1]
            return domain == self.allowed_domain.lower()
        except (IndexError, AttributeError):
            return False

    async def _lookup_employee_by_email(self, email: str) -> Optional[int]:
        """Look up active employee ID by email address."""
        async with self.session_factory() as session:
            stmt = select(EmployeeORM.id).where(
                EmployeeORM.email == email.lower(),
                EmployeeORM.is_active.is_(True),
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def _auto_create_employee(self, first_name: str, last_name: str, email: str) -> int:
        """Auto-create an employee record from GAL info. Returns new employee ID."""
        for attempt in range(2):
            employee_number = f"AUTO-{uuid.uuid4().hex[:8].upper()}"
            try:
                async with self.session_factory() as session:
                    orm_obj = EmployeeORM(
                        employee_number=employee_number,
                        first_name=first_name,
                        last_name=last_name,
                        email=email.lower(),
                    )
                    session.add(orm_obj)
                    await session.commit()
                    await session.refresh(orm_obj)
                    logger.info(
                        "Auto-created employee from GAL: id=%d, email=%s, employee_number=%s",
                        orm_obj.id,
                        email,
                        employee_number,
                    )
                    return orm_obj.id
            except IntegrityError:
                if attempt == 0:
                    logger.warning(
                        "IntegrityError on auto-employee creation for %s "
                        "(employee_number collision), retrying with new UUID",
                        email,
                    )
                    continue
                logger.error(
                    "IntegrityError on auto-employee creation for %s after retry; "
                    "concurrent creation likely succeeded",
                    email,
                )
                raise
        # Unreachable — satisfies type checker
        raise RuntimeError("_auto_create_employee loop exited without returning")

    async def lookup_or_quarantine(
        self,
        email: str,
    ) -> tuple[Optional[int], Optional[str]]:
        """
        Look up employee by email using GAL-aware logic.

        Returns:
            Tuple of (employee_id, reason):
              - (employee_id, None) → success
              - (None, "ignore") → silently skip
              - (None, other_string) → quarantine reason (reserved for future)
        """
        # 1. Non-city domain → ignore
        if not self._is_city_domain(email):
            logger.debug("Ignoring non-city domain: %s", email)
            return None, "ignore"

        # 2. City domain + NOT in GAL → ignore
        if not await self.gal_provider.is_in_gal(email.lower()):
            logger.debug("Ignoring city email not in GAL: %s", email)
            return None, "ignore"

        # 3. City domain + in GAL + is_person=False → ignore (distribution list)
        if not await self.gal_provider.is_person(email.lower()):
            logger.debug("Ignoring distribution list: %s", email)
            return None, "ignore"

        # 4. City domain + in GAL + is_person=True — check for existing employee
        employee_id = await self._lookup_employee_by_email(email)
        if employee_id is not None:
            return employee_id, None

        # 5. No employee record → auto-create from GAL
        person_info = await self.gal_provider.get_person_info(email.lower())
        if person_info is None:
            # Shouldn't happen (is_person was True), but be defensive
            logger.warning("GAL person info vanished for %s", email)
            return None, "ignore"

        new_employee_id = await self._auto_create_employee(
            first_name=person_info.first_name,
            last_name=person_info.last_name,
            email=person_info.email,
        )
        return new_employee_id, None


def create_directory_lookup_from_env() -> DirectoryLookup:
    """Create a DirectoryLookup instance from environment variables."""
    session_factory = get_session_factory()
    gal_provider = DatabaseGALProvider(session_factory)
    return DirectoryLookup(
        session_factory=session_factory,
        gal_provider=gal_provider,
        allowed_domain=os.environ.get("ALLOWED_EMAIL_DOMAIN", "ci.laredo.tx.us"),
    )
