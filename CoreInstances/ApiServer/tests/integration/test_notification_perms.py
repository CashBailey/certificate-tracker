"""
Integration tests for notification system permissions and schema.

Verifies:
- scheduler worker DB privileges on notification_events and job_cursors tables
- migration 029 columns (read, read_at) exist on notification_events
- job_cursors table schema is correct
"""

import os
import pytest

# Ensure test environment is set before any imports
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://laredo:laredo123@localhost:5432/laredo_certificates",
)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


def _ensure_asyncpg_driver(url: str) -> str:
    """Force asyncpg driver suffix.

    setdefault above is a no-op when the env already has DATABASE_URL set
    without a driver suffix (the dev/CI container default). create_async_engine
    then loads psycopg2 (the default sync driver) and raises "asyncio extension
    requires an async driver". Convert here so callers don't have to think about it.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture
async def db_engine():
    """Create an async engine for integration tests.

    Use the same SSL context the API server uses; without it the engine
    fails pg_hba.conf checks on the dev/CI postgres which requires hostssl
    for connections from the docker network.
    """
    from src.shared.tls import build_ssl_context
    database_url = _ensure_asyncpg_driver(os.environ["DATABASE_URL"])
    ssl_ctx = build_ssl_context()
    engine = create_async_engine(
        database_url,
        echo=False,
        connect_args={"ssl": ssl_ctx} if ssl_ctx else {},
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Create an async session for integration tests."""
    factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session
        await session.rollback()


# ==================== Schema verification ====================


class TestNotificationEventsSchema:
    """Verify notification_events table has the expected columns."""

    @pytest.mark.asyncio
    async def test_read_column_exists(self, db_session):
        """notification_events.read column should exist."""
        result = await db_session.execute(
            text("""
                SELECT column_name, data_type, column_default
                FROM information_schema.columns
                WHERE table_schema = 'notifications'
                  AND table_name = 'notification_events'
                  AND column_name = 'read'
            """)
        )
        row = result.fetchone()
        assert row is not None, "Column 'read' not found on notification_events"
        assert row[1] == "boolean"

    @pytest.mark.asyncio
    async def test_read_at_column_exists(self, db_session):
        """notification_events.read_at column should exist."""
        result = await db_session.execute(
            text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'notifications'
                  AND table_name = 'notification_events'
                  AND column_name = 'read_at'
            """)
        )
        row = result.fetchone()
        assert row is not None, "Column 'read_at' not found on notification_events"
        assert "timestamp" in row[1].lower()

    @pytest.mark.asyncio
    async def test_read_column_defaults_to_false(self, db_session):
        """read column should default to false."""
        result = await db_session.execute(
            text("""
                SELECT column_default
                FROM information_schema.columns
                WHERE table_schema = 'notifications'
                  AND table_name = 'notification_events'
                  AND column_name = 'read'
            """)
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] is not None and "false" in row[0].lower()

    @pytest.mark.asyncio
    async def test_delivered_column_still_exists(self, db_session):
        """delivered column should still exist (not replaced by read)."""
        result = await db_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'notifications'
                  AND table_name = 'notification_events'
                  AND column_name = 'delivered'
            """)
        )
        row = result.fetchone()
        assert row is not None, "Column 'delivered' should still exist"


# ==================== Scheduler worker permissions ====================


class TestSchedulerWorkerPermissions:
    """Verify laredo_scheduler_worker has required DB privileges."""

    @pytest.mark.asyncio
    async def test_select_on_notification_events(self, db_session):
        """Scheduler worker should have SELECT on notification_events."""
        result = await db_session.execute(
            text("""
                SELECT has_table_privilege(
                    'laredo_scheduler_worker',
                    'notifications.notification_events',
                    'SELECT'
                )
            """)
        )
        assert result.scalar() is True

    @pytest.mark.asyncio
    async def test_insert_on_notification_events(self, db_session):
        """Scheduler worker should have INSERT on notification_events."""
        result = await db_session.execute(
            text("""
                SELECT has_table_privilege(
                    'laredo_scheduler_worker',
                    'notifications.notification_events',
                    'INSERT'
                )
            """)
        )
        assert result.scalar() is True

    @pytest.mark.asyncio
    async def test_select_on_job_cursors(self, db_session):
        """Scheduler worker should have SELECT on job_cursors."""
        result = await db_session.execute(
            text("""
                SELECT has_table_privilege(
                    'laredo_scheduler_worker',
                    'notifications.job_cursors',
                    'SELECT'
                )
            """)
        )
        assert result.scalar() is True

    @pytest.mark.asyncio
    async def test_insert_on_job_cursors(self, db_session):
        """Scheduler worker should have INSERT on job_cursors."""
        result = await db_session.execute(
            text("""
                SELECT has_table_privilege(
                    'laredo_scheduler_worker',
                    'notifications.job_cursors',
                    'INSERT'
                )
            """)
        )
        assert result.scalar() is True

    @pytest.mark.asyncio
    async def test_update_on_job_cursors(self, db_session):
        """Scheduler worker should have UPDATE on job_cursors."""
        result = await db_session.execute(
            text("""
                SELECT has_table_privilege(
                    'laredo_scheduler_worker',
                    'notifications.job_cursors',
                    'UPDATE'
                )
            """)
        )
        assert result.scalar() is True

    @pytest.mark.asyncio
    async def test_select_on_verified_certificate_records(self, db_session):
        """Scheduler worker should have SELECT on verified_certificate_records (migration 028)."""
        result = await db_session.execute(
            text("""
                SELECT has_table_privilege(
                    'laredo_scheduler_worker',
                    'certificates.verified_certificate_records',
                    'SELECT'
                )
            """)
        )
        assert result.scalar() is True

    @pytest.mark.asyncio
    async def test_select_on_certificate_types(self, db_session):
        """Scheduler worker should have SELECT on certificate_types (migration 028)."""
        result = await db_session.execute(
            text("""
                SELECT has_table_privilege(
                    'laredo_scheduler_worker',
                    'certificates.certificate_types',
                    'SELECT'
                )
            """)
        )
        assert result.scalar() is True


# ==================== Cross-worker least privilege ====================


@pytest.mark.parametrize(
    ("role", "table_name", "privilege"),
    [
        (
            "laredo_email_intake_worker",
            "certificates.verified_certificate_records",
            "INSERT",
        ),
        (
            "laredo_email_intake_worker",
            "certificates.requirement_assignments",
            "UPDATE",
        ),
        (
            "laredo_extraction_worker",
            "certificates.employees",
            "UPDATE",
        ),
        (
            "laredo_extraction_worker",
            "certificates.verified_certificate_records",
            "INSERT",
        ),
        (
            "laredo_scheduler_worker",
            "certificates.employees",
            "UPDATE",
        ),
        (
            "laredo_scheduler_worker",
            "certificates.certificate_documents",
            "INSERT",
        ),
        (
            "laredo_scheduler_worker",
            "notifications.alert_configuration",
            "UPDATE",
        ),
    ],
)
@pytest.mark.asyncio
async def test_worker_cannot_mutate_another_workflow(
    db_session, role, table_name, privilege
):
    """A parser/worker identity must not bypass API RBAC or human review."""
    result = await db_session.execute(
        text("SELECT has_table_privilege(:role, :table_name, :privilege)"),
        {"role": role, "table_name": table_name, "privilege": privilege},
    )
    assert result.scalar() is False


@pytest.mark.parametrize(
    ("column_name", "expected"),
    [
        ("employee_number", True),
        ("first_name", True),
        ("last_name", True),
        ("email", True),
        ("role", False),
        ("password_hash", False),
        ("is_active", False),
        ("token_version", False),
    ],
)
@pytest.mark.asyncio
async def test_email_intake_employee_insert_is_column_scoped(
    db_session, column_name, expected
):
    """Email intake can create a passwordless Employee, never a login role."""
    result = await db_session.execute(
        text(
            """
            SELECT has_column_privilege(
                'laredo_email_intake_worker',
                'certificates.employees',
                :column_name,
                'INSERT'
            )
            """
        ),
        {"column_name": column_name},
    )
    assert result.scalar() is expected


@pytest.mark.parametrize(
    ("column_name", "expected"),
    [("document_id", True), ("review_state", False), ("reviewed_by_id", False)],
)
@pytest.mark.asyncio
async def test_email_intake_extraction_insert_is_processing_only(
    db_session, column_name, expected
):
    """Server defaults, not email input, choose extraction review state."""
    result = await db_session.execute(
        text(
            """
            SELECT has_column_privilege(
                'laredo_email_intake_worker',
                'certificates.extraction_runs',
                :column_name,
                'INSERT'
            )
            """
        ),
        {"column_name": column_name},
    )
    assert result.scalar() is expected


# ==================== Job cursors table ====================


class TestJobCursorsSchema:
    """Verify job_cursors table schema."""

    @pytest.mark.asyncio
    async def test_job_cursors_table_exists(self, db_session):
        """job_cursors table should exist in notifications schema."""
        result = await db_session.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'notifications'
                      AND table_name = 'job_cursors'
                )
            """)
        )
        assert result.scalar() is True

    @pytest.mark.asyncio
    async def test_job_cursors_has_job_name(self, db_session):
        """job_cursors should have a job_name column."""
        result = await db_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'notifications'
                  AND table_name = 'job_cursors'
                  AND column_name = 'job_name'
            """)
        )
        assert result.fetchone() is not None

    @pytest.mark.asyncio
    async def test_job_cursors_has_last_success_date(self, db_session):
        """job_cursors should have a last_success_date column."""
        result = await db_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'notifications'
                  AND table_name = 'job_cursors'
                  AND column_name = 'last_success_date'
            """)
        )
        assert result.fetchone() is not None
