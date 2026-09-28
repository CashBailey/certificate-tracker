"""
Unit tests for requirement CSV import safeguards.
"""

import io
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile

from src.routes import requirements as requirements_module
from src.shared.models import Employee, Role


def _make_coordinator() -> Employee:
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


@pytest.mark.asyncio
async def test_import_rejects_when_row_limit_exceeded(monkeypatch):
    monkeypatch.setattr(requirements_module, "MAX_CSV_IMPORT_ROWS", 10)

    # 11 data rows + header.
    rows = [
        "employee_identifier,certificate_type,due_date",
        *[f"E{i:05d},Unknown Type,2030-01-01" for i in range(11)],
    ]
    payload = "\n".join(rows).encode("utf-8")
    upload = UploadFile(filename="bulk.csv", file=io.BytesIO(payload))

    repository = AsyncMock()
    repository.list_certificate_types = AsyncMock(return_value=[])

    with pytest.raises(HTTPException, match="maximum allowed"):
        await requirements_module.import_requirements(
            file=upload,
            dry_run=True,
            current_user=_make_coordinator(),
            repository=repository,
        )


@pytest.mark.asyncio
async def test_import_rejects_admin_target_without_creating_requirement():
    payload = (
        "employee_identifier,certificate_type,due_date\n"
        "A00001,Forklift,2030-01-01\n"
    ).encode("utf-8")
    upload = UploadFile(filename="bulk.csv", file=io.BytesIO(payload))

    admin = Employee(
        id=1,
        employee_number="A00001",
        first_name="System",
        last_name="Admin",
        email="admin@ci.laredo.tx.us",
        role=Role.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repository = AsyncMock()
    repository.list_certificate_types.return_value = [
        SimpleNamespace(id=7, name="Forklift")
    ]
    repository.get_employee_by_number.return_value = admin

    response = await requirements_module.import_requirements(
        file=upload,
        dry_run=False,
        current_user=_make_coordinator(),
        repository=repository,
    )

    assert response.created == 0
    assert response.errors == 1
    assert "Admin" in response.results[0].reason
    repository.insert_requirement.assert_not_awaited()
