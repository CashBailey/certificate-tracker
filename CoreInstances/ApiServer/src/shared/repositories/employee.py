"""
Employee repository for the City of Laredo Certificate Management System.

Handles all employee-related database operations.
"""

from typing import Optional

from sqlalchemy import select, update, and_

from ..models import Employee, Role
from ..orm_models import EmployeeORM
from .base import BaseRepository


class EmployeeRepository(BaseRepository):
    """Repository for Employee domain operations."""

    async def get_by_id(self, employee_id: int) -> Optional[Employee]:
        """Get employee by ID."""
        stmt = select(EmployeeORM).where(EmployeeORM.id == employee_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._to_model(orm_obj) if orm_obj else None

    async def get_by_email(self, email: str) -> Optional[Employee]:
        """Get employee by email."""
        stmt = select(EmployeeORM).where(EmployeeORM.email == email)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._to_model(orm_obj) if orm_obj else None

    async def get_by_number(self, employee_number: str) -> Optional[Employee]:
        """Get employee by employee number."""
        stmt = select(EmployeeORM).where(EmployeeORM.employee_number == employee_number)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._to_model(orm_obj) if orm_obj else None

    async def list_all(self) -> list[Employee]:
        """List all employees."""
        stmt = select(EmployeeORM).order_by(
            EmployeeORM.last_name, EmployeeORM.first_name
        )
        result = await self.session.execute(stmt)
        return [self._to_model(orm_obj) for orm_obj in result.scalars()]

    async def list_by_role(self, role: str) -> list[Employee]:
        """
        Get all active employees with a specific role.

        Args:
            role: Role value to filter by (e.g., "Coordinator", "Admin")

        Returns:
            List of employees with the specified role
        """
        stmt = (
            select(EmployeeORM)
            .where(and_(EmployeeORM.role == role, EmployeeORM.is_active == True))
            .order_by(EmployeeORM.last_name, EmployeeORM.first_name)
        )
        result = await self.session.execute(stmt)
        return [self._to_model(orm_obj) for orm_obj in result.scalars()]

    async def create(self, employee: Employee) -> Employee:
        """Create a new employee."""
        orm_obj = EmployeeORM(
            employee_number=employee.employee_number,
            first_name=employee.first_name,
            last_name=employee.last_name,
            email=employee.email,
            role=employee.role.value
            if isinstance(employee.role, Role)
            else employee.role,
            manager_id=employee.manager_id,
        )
        self.session.add(orm_obj)
        await self.flush()
        await self.refresh(orm_obj)
        return self._to_model(orm_obj)

    async def update_password(self, employee_id: int, password_hash: str) -> None:
        """Update employee password hash."""
        stmt = (
            update(EmployeeORM)
            .where(EmployeeORM.id == employee_id)
            .values(password_hash=password_hash)
        )
        await self.session.execute(stmt)

    async def update(
        self,
        employee_id: int,
        *,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None,
        manager_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        lms_username_id: Optional[str] = None,
    ) -> Optional[Employee]:
        """
        Update employee fields.

        Only non-None values will be updated.

        Returns:
            Updated employee or None if not found
        """
        # Build update values
        values = {}
        if first_name is not None:
            values["first_name"] = first_name
        if last_name is not None:
            values["last_name"] = last_name
        if email is not None:
            values["email"] = email
        if role is not None:
            values["role"] = role
        if manager_id is not None:
            values["manager_id"] = manager_id
        if is_active is not None:
            values["is_active"] = is_active
        if lms_username_id is not None:
            values["lms_username_id"] = lms_username_id

        if not values:
            return await self.get_by_id(employee_id)

        stmt = update(EmployeeORM).where(EmployeeORM.id == employee_id).values(**values)
        await self.session.execute(stmt)

        return await self.get_by_id(employee_id)

    async def deactivate(self, employee_id: int) -> None:
        """Deactivate an employee."""
        stmt = (
            update(EmployeeORM)
            .where(EmployeeORM.id == employee_id)
            .values(is_active=False)
        )
        await self.session.execute(stmt)

    async def reactivate(self, employee_id: int) -> None:
        """Reactivate an employee."""
        stmt = (
            update(EmployeeORM)
            .where(EmployeeORM.id == employee_id)
            .values(is_active=True)
        )
        await self.session.execute(stmt)

    def _to_model(self, orm_obj: EmployeeORM) -> Employee:
        """Convert ORM object to domain model."""
        return Employee(
            id=orm_obj.id,
            employee_number=orm_obj.employee_number,
            first_name=orm_obj.first_name,
            last_name=orm_obj.last_name,
            email=orm_obj.email,
            role=Role(orm_obj.role),
            manager_id=orm_obj.manager_id,
            password_hash=orm_obj.password_hash,
            is_active=orm_obj.is_active,
            lms_username_id=orm_obj.lms_username_id,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at,
        )
