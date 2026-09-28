"""
Object-level authorization on PATCH /employees/{id}.

Regression guard for the Admin-account-takeover / last-admin-lockout hole:
a Coordinator must not be able to mutate an Admin account through any field
(email, is_active, ...), not just the role field.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.routes import employees as employees_module
from src.routes.schemas import EmployeeUpdate
from src.shared.models import Employee, Role


def _actor(role: Role) -> Employee:
    return Employee(
        id=1 if role == Role.ADMIN else 2,
        employee_number="A00001",
        first_name="Actor",
        last_name="User",
        email="actor@ci.laredo.tx.us",
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _target(role_value: str, *, is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=99,
        employee_number="T00099",
        first_name="Target",
        last_name="Admin",
        email="target.admin@ci.laredo.tx.us",
        role=role_value,
        manager_id=None,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _db_returning(target) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = target
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        EmployeeUpdate(email="attacker@evil.com"),
        EmployeeUpdate(is_active=False),
        EmployeeUpdate(first_name="Renamed"),
    ],
)
async def test_coordinator_cannot_mutate_admin_account(payload):
    db = _db_returning(_target(Role.ADMIN.value))
    repository = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await employees_module.update_employee(
            employee_id=99,
            data=payload,
            db=db,
            current_user=_actor(Role.COORDINATOR),
            repository=repository,
        )

    assert exc_info.value.status_code == 403
    assert "Admin" in exc_info.value.detail
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_may_still_update_admin_account():
    db = _db_returning(_target(Role.ADMIN.value))
    repository = AsyncMock()

    response = await employees_module.update_employee(
        employee_id=99,
        data=EmployeeUpdate(first_name="Renamed"),
        db=db,
        current_user=_actor(Role.ADMIN),
        repository=repository,
    )

    assert response.first_name == "Renamed"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_may_update_non_admin_employee():
    db = _db_returning(_target(Role.EMPLOYEE.value))
    repository = AsyncMock()

    response = await employees_module.update_employee(
        employee_id=99,
        data=EmployeeUpdate(first_name="Renamed"),
        db=db,
        current_user=_actor(Role.COORDINATOR),
        repository=repository,
    )

    assert response.first_name == "Renamed"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_cannot_reactivate_admin_account():
    db = _db_returning(_target(Role.ADMIN.value, is_active=False))

    with pytest.raises(HTTPException) as exc_info:
        await employees_module.reactivate_employee(
            employee_id=99,
            db=db,
            current_user=_actor(Role.COORDINATOR),
            repository=AsyncMock(),
        )

    assert exc_info.value.status_code == 403
    assert "Admin" in exc_info.value.detail
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_may_reactivate_admin_account():
    db = _db_returning(_target(Role.ADMIN.value, is_active=False))

    response = await employees_module.reactivate_employee(
        employee_id=99,
        db=db,
        current_user=_actor(Role.ADMIN),
        repository=AsyncMock(),
    )

    assert response.is_active is True
    db.commit.assert_awaited_once()
