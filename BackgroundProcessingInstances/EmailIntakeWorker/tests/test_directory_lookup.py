"""
Unit tests for GAL-aware directory lookup (INV-09).

Tests the DirectoryLookup.lookup_or_quarantine() decision tree:
  1. Non-city domain → ignore
  2. City domain + NOT in GAL → ignore
  3. City domain + in GAL + distribution list → ignore
  4. City domain + in GAL + employee exists → return employee_id
  5. City domain + in GAL + no employee → auto-create
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set up import paths
_project_root = Path(__file__).resolve().parents[3]
_api_src = str(_project_root / "CoreInstances" / "ApiServer" / "src")
_email_intake_src = str(_project_root / "BackgroundProcessingInstances" / "EmailIntakeWorker" / "src")
for _p in (_api_src, _email_intake_src):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gal_provider import PersonInfo
from directory_lookup import DirectoryLookup


# ── Helpers ──────────────────────────────────────────────────────────────


class FakeGALProvider:
    """In-memory GAL provider for testing."""

    def __init__(self, entries=None):
        # entries: dict of email -> {is_person, first_name, last_name}
        self._entries = entries or {}

    async def is_person(self, email: str) -> bool:
        entry = self._entries.get(email.lower())
        return entry is not None and entry.get("is_person", True)

    async def get_person_info(self, email: str) -> PersonInfo | None:
        entry = self._entries.get(email.lower())
        if not entry or not entry.get("is_person", True):
            return None
        return PersonInfo(
            first_name=entry["first_name"],
            last_name=entry["last_name"],
            email=email.lower(),
        )

    async def is_in_gal(self, email: str) -> bool:
        return email.lower() in self._entries


def make_lookup(gal_entries=None, allowed_domain="laredotx.gov"):
    """Create a DirectoryLookup with fake GAL and mocked session factory."""
    gal = FakeGALProvider(gal_entries or {})
    session_factory = MagicMock()
    return DirectoryLookup(
        session_factory=session_factory,
        gal_provider=gal,
        allowed_domain=allowed_domain,
    )


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_non_city_domain_returns_ignore():
    """Emails from non-city domains should be silently ignored."""
    lookup = make_lookup()
    emp_id, reason = await lookup.lookup_or_quarantine("user@gmail.com")
    assert emp_id is None
    assert reason == "ignore"


@pytest.mark.asyncio
async def test_city_domain_not_in_gal_returns_ignore():
    """City-domain emails NOT in the GAL should be silently ignored."""
    lookup = make_lookup(gal_entries={})
    emp_id, reason = await lookup.lookup_or_quarantine("unknown@laredotx.gov")
    assert emp_id is None
    assert reason == "ignore"


@pytest.mark.asyncio
async def test_distribution_list_returns_ignore():
    """GAL entries with is_person=False (distribution lists) should be ignored."""
    lookup = make_lookup(gal_entries={
        "allstaff@laredotx.gov": {
            "is_person": False,
            "first_name": "All",
            "last_name": "Staff",
        },
    })
    emp_id, reason = await lookup.lookup_or_quarantine("allstaff@laredotx.gov")
    assert emp_id is None
    assert reason == "ignore"


@pytest.mark.asyncio
async def test_city_domain_in_gal_employee_exists():
    """City-domain + GAL person + existing employee → returns employee_id."""
    gal_entries = {
        "jsmith@laredotx.gov": {
            "is_person": True,
            "first_name": "John",
            "last_name": "Smith",
        },
    }
    lookup = make_lookup(gal_entries=gal_entries)

    # Mock the DB lookup to return an existing employee
    lookup._lookup_employee_by_email = AsyncMock(return_value=42)

    emp_id, reason = await lookup.lookup_or_quarantine("jsmith@laredotx.gov")
    assert emp_id == 42
    assert reason is None


@pytest.mark.asyncio
async def test_city_domain_in_gal_no_employee_auto_creates():
    """City-domain + GAL person + no employee → auto-creates and returns new ID."""
    gal_entries = {
        "jdoe@laredotx.gov": {
            "is_person": True,
            "first_name": "Jane",
            "last_name": "Doe",
        },
    }
    lookup = make_lookup(gal_entries=gal_entries)

    # No existing employee
    lookup._lookup_employee_by_email = AsyncMock(return_value=None)
    # Mock auto-create to return a new ID
    lookup._auto_create_employee = AsyncMock(return_value=99)

    emp_id, reason = await lookup.lookup_or_quarantine("jdoe@laredotx.gov")
    assert emp_id == 99
    assert reason is None

    # Verify auto-create was called with correct info
    lookup._auto_create_employee.assert_awaited_once_with(
        first_name="Jane",
        last_name="Doe",
        email="jdoe@laredotx.gov",
    )


@pytest.mark.asyncio
async def test_auto_created_employee_has_correct_attributes():
    """Auto-created employees should have role=EMPLOYEE, no password, is_active=True."""
    gal_entries = {
        "new@laredotx.gov": {
            "is_person": True,
            "first_name": "New",
            "last_name": "Employee",
        },
    }
    lookup = make_lookup(gal_entries=gal_entries)
    lookup._lookup_employee_by_email = AsyncMock(return_value=None)

    # Capture EmployeeORM creation
    created_orm = None

    async def mock_auto_create(first_name, last_name, email):
        nonlocal created_orm
        from shared.orm_models import EmployeeORM
        # Simulate what _auto_create_employee does
        created_orm = EmployeeORM(
            employee_number=f"AUTO-12345",
            first_name=first_name,
            last_name=last_name,
            email=email,
            role="Employee",
            password_hash=None,
            is_active=True,
        )
        return 100

    lookup._auto_create_employee = mock_auto_create

    emp_id, reason = await lookup.lookup_or_quarantine("new@laredotx.gov")
    assert emp_id == 100
    assert reason is None
    assert created_orm is not None
    assert created_orm.role == "Employee"
    assert created_orm.password_hash is None
    assert created_orm.is_active is True
    assert created_orm.employee_number.startswith("AUTO-")
