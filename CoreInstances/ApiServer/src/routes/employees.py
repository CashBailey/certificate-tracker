"""
Employee management API endpoints.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db_session, get_repository, require_coordinator_or_admin
from ..shared.orm_models import EmployeeORM as Employee
from ..shared.models import Role
from ..shared.repository import SqlRepository
from ..shared.protocols import Repository
from ..shared.audit import audit_employee_action
from ..auth.service import AuthService
from .schemas import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeListResponse,
)

router = APIRouter(prefix="/employees", tags=["employees"])
logger = logging.getLogger(__name__)


@router.get("", response_model=EmployeeListResponse)
async def list_employees(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user: Employee = Depends(require_coordinator_or_admin),
):
    """
    List all employees with optional filtering.

    Only Coordinator or Admin can list employees.
    """
    query = select(Employee)

    # Exclude Admin system accounts from default listing (B1/B2)
    # Admin is only visible if explicitly filtered with ?role=Admin
    if role:
        query = query.where(Employee.role == role)
    else:
        query = query.where(Employee.role != "Admin")
    if is_active is not None:
        query = query.where(Employee.is_active == is_active)
    if search:
        for token in search.split():
            # Escape LIKE metacharacters so user input is treated as a literal
            # substring - prevents `%` from matching all records or `_` from
            # acting as a single-character wildcard.
            escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            token_filter = f"%{escaped}%"
            query = query.where(
                (Employee.first_name.ilike(token_filter, escape="\\"))
                | (Employee.last_name.ilike(token_filter, escape="\\"))
                | (Employee.email.ilike(token_filter, escape="\\"))
                | (Employee.employee_number.ilike(token_filter, escape="\\"))
            )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.order_by(Employee.last_name, Employee.first_name)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    employees = result.scalars().all()

    return EmployeeListResponse(
        employees=[EmployeeResponse.model_validate(e) for e in employees],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: Employee = Depends(require_coordinator_or_admin),
):
    """Get a single employee by ID."""
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )

    return EmployeeResponse.model_validate(employee)


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Employee = Depends(require_coordinator_or_admin),
    repository: Repository = Depends(get_repository),
):
    """Create a new employee. Coordinator or Admin only."""
    # Check for duplicate email
    existing = await db.execute(select(Employee).where(Employee.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Check for duplicate employee number
    existing = await db.execute(
        select(Employee).where(Employee.employee_number == data.employee_number)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee number already exists",
        )

    # Validate manager_id if provided
    if data.manager_id:
        manager = await db.execute(
            select(Employee).where(Employee.id == data.manager_id)
        )
        if not manager.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Manager not found"
            )

    # Admin role cannot be assigned via API (HLSD Decision 14, A5 fix)
    if data.role == "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts cannot be created through the API",
        )

    # Create employee without a password - they will set it via the setup email
    employee = Employee(
        employee_number=data.employee_number,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        password_hash=None,
        role=data.role,
        manager_id=data.manager_id,
        is_active=True,
    )

    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    # Audit log for employee creation
    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="employee_created",
        target_type="employee",
        target_id=str(employee.id),
        details={
            "employee_number": data.employee_number,
            "role": data.role,
            "email": data.email,
        },
    )

    # Send account setup email (best-effort - don't fail the creation if email fails)
    try:
        auth_service = AuthService(SqlRepository(db))
        await auth_service.send_account_setup_email(
            employee.id, employee.email, employee.first_name
        )
    except Exception:
        logger.exception(
            "Account setup email delivery failed after employee creation",
            extra={"employee_id": employee.id},
        )

    return EmployeeResponse.model_validate(employee)


@router.patch("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    data: EmployeeUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Employee = Depends(require_coordinator_or_admin),
    repository: Repository = Depends(get_repository),
):
    """Update an employee. Coordinator or Admin only."""
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )

    # Object-level guard: only an Admin may mutate an Admin account. Without
    # this, a Coordinator could PATCH an Admin's email (then trigger a password
    # reset to take it over) or set is_active=false on the last Admin - both
    # bypass the equivalent guards that already protect the deactivate path.
    if (
        employee.role == Role.ADMIN.value
        and current_user.role != Role.ADMIN.value
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Coordinators cannot modify Admin accounts",
        )

    # Check for duplicate email if changing
    if data.email and data.email != employee.email:
        existing = await db.execute(
            select(Employee).where(Employee.email == data.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Check for duplicate employee number if changing
    if data.employee_number and data.employee_number != employee.employee_number:
        existing = await db.execute(
            select(Employee).where(Employee.employee_number == data.employee_number)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee number already exists",
            )

    # Validate manager_id if provided
    if data.manager_id is not None:
        if data.manager_id:
            # Prevent self-reference
            if data.manager_id == employee_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Employee cannot be their own manager",
                )
            manager = await db.execute(
                select(Employee).where(Employee.id == data.manager_id)
            )
            if not manager.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Manager not found"
                )

    # Role assignment guards (HLSD Decision 14, A5 fix)
    if data.role is not None:
        if data.role == "Admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role cannot be assigned through the API",
            )
        if employee.role == "Admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot change the role of an Admin account",
            )

    # Capture role before mutation for audit log
    old_role: Optional[str] = employee.role if data.role is not None else None

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(employee, field, value)

    await db.commit()
    await db.refresh(employee)

    # Audit log for employee updates
    audit_details: dict = {"updated_fields": list(update_data.keys())}
    if old_role is not None and data.role is not None and old_role != data.role:
        audit_details["old_role"] = old_role
        audit_details["new_role"] = data.role

    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="employee_updated",
        target_type="employee",
        target_id=str(employee_id),
        details=audit_details,
    )

    return EmployeeResponse.model_validate(employee)


@router.post("/{employee_id}/send-setup-email", status_code=status.HTTP_202_ACCEPTED)
async def send_setup_email(
    employee_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: Employee = Depends(require_coordinator_or_admin),
):
    """Resend the account setup email so the employee can set their password."""
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send setup email to a deactivated employee",
        )

    auth_service = AuthService(SqlRepository(db))
    try:
        await auth_service.send_account_setup_email(
            employee.id, employee.email, employee.first_name
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Setup email could not be delivered. Verify SMTP TLS configuration and retry.",
        ) from exc

    return {"message": "Setup email sent"}


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: Employee = Depends(require_coordinator_or_admin),
    repository: Repository = Depends(get_repository),
):
    """
    Deactivate an employee (soft delete). Coordinator or Admin only.

    Cannot deactivate yourself or the last admin.
    """
    if employee_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself"
        )

    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )

    # Coordinators cannot deactivate Admin accounts
    if employee.role == Role.ADMIN.value and current_user.role == Role.COORDINATOR.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Coordinators cannot deactivate Admin accounts",
        )

    # Prevent deactivating the last admin
    if employee.role == Role.ADMIN.value:
        admin_count = await db.execute(
            select(func.count())
            .select_from(Employee)
            .where((Employee.role == Role.ADMIN.value) & (Employee.is_active == True))
        )
        if admin_count.scalar() <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active admin",
            )

    employee.is_active = False
    await db.commit()

    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="employee_deactivated",
        target_type="employee",
        target_id=str(employee_id),
        details={"employee_role": employee.role},
    )

    return None


@router.post("/{employee_id}/reactivate", response_model=EmployeeResponse)
async def reactivate_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: Employee = Depends(require_coordinator_or_admin),
    repository: Repository = Depends(get_repository),
):
    """Reactivate a deactivated employee. Coordinator or Admin only."""
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )

    # Reactivation restores every permission held by the target account. Keep
    # the same object-level Admin boundary enforced by update/deactivation.
    if employee.role == Role.ADMIN.value and current_user.role == Role.COORDINATOR.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Coordinators cannot reactivate Admin accounts",
        )

    if employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Employee is already active"
        )

    employee.is_active = True
    await db.commit()
    await db.refresh(employee)

    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="employee_reactivated",
        target_type="employee",
        target_id=str(employee_id),
        details={"employee_role": employee.role},
    )

    return EmployeeResponse.model_validate(employee)
