"""
Unit tests for duplicate-assignment rejection in POST /requirements.

One open requirement per employee + certificate type. Satisfied and waived
rows are history and must not block a new compliance cycle.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.routes import requirements as requirements_module
from src.routes.schemas import RequirementCreate
from src.shared.models import (
    CertificateType,
    Employee,
    RequirementAssignment,
    RequirementStatus,
    Role,
)


def _coordinator() -> Employee:
    return Employee(
        id=100,
        employee_number="C00100",
        first_name="Coord",
        last_name="User",
        email="coord@ci.laredo.tx.us",
        role=Role.COORDINATOR,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _employee(employee_id: int = 7) -> Employee:
    return Employee(
        id=employee_id,
        employee_number="E00007",
        first_name="Test",
        last_name="Employee",
        email="test.employee@ci.laredo.tx.us",
        role=Role.EMPLOYEE,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _requirement(status: RequirementStatus, cert_type_id: int = 3) -> RequirementAssignment:
    return RequirementAssignment(
        id=55,
        employee_id=7,
        certificate_type_id=cert_type_id,
        due_date=date(2026, 9, 1),
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _repository(existing: list[RequirementAssignment]) -> AsyncMock:
    repository = AsyncMock()
    repository.get_certificate_type_by_id = AsyncMock(
        return_value=CertificateType(id=3, name="CPR Certification", description="")
    )
    repository.get_employee_by_id = AsyncMock(return_value=_employee())
    repository.list_requirements_for_employee = AsyncMock(return_value=existing)
    saved = _requirement(RequirementStatus.NOT_STARTED)
    saved.id = 99
    repository.create_requirement = AsyncMock(return_value=saved)
    return repository


def _request() -> RequirementCreate:
    return RequirementCreate(employee_id=7, certificate_type_id=3, due_date=date(2026, 12, 1))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "open_status",
    [
        RequirementStatus.NOT_STARTED,
        RequirementStatus.SUBMITTED,
        RequirementStatus.IN_PROGRESS,
        RequirementStatus.OVERDUE,
    ],
)
async def test_open_duplicate_is_rejected_with_409(open_status):
    repository = _repository([_requirement(open_status)])

    with pytest.raises(HTTPException) as exc_info:
        await requirements_module.create_requirement(
            request=_request(), current_user=_coordinator(), repository=repository
        )

    assert exc_info.value.status_code == 409
    assert "already has an open" in exc_info.value.detail
    repository.create_requirement.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "historical_status",
    [RequirementStatus.SATISFIED, RequirementStatus.WAIVED],
)
async def test_satisfied_or_waived_history_does_not_block_new_cycle(historical_status):
    repository = _repository([_requirement(historical_status)])

    response = await requirements_module.create_requirement(
        request=_request(), current_user=_coordinator(), repository=repository
    )

    assert response.id == 99
    repository.create_requirement.assert_awaited_once()


@pytest.mark.asyncio
async def test_open_requirement_for_other_cert_type_does_not_block():
    repository = _repository([_requirement(RequirementStatus.NOT_STARTED, cert_type_id=8)])

    response = await requirements_module.create_requirement(
        request=_request(), current_user=_coordinator(), repository=repository
    )

    assert response.id == 99
    repository.create_requirement.assert_awaited_once()
