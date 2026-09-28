"""
SQLAlchemy repository implementation for the City of Laredo Certificate Management System.

Implements the Repository protocol using async SQLAlchemy sessions.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from .models import (
    AlertConfiguration,
    AuditLog,
    AuditActorType,
    CertificateDocument,
    CertificateType,
    DeletionTombstone,
    EmailIntakeMessage,
    EmailProcessingState,
    Employee,
    ExtractionRun,
    IntakeChannel,
    JobCursor,
    NotificationEvent,
    PasswordResetToken,
    RequirementAssignment,
    ReviewState,
    VerifiedCertificateRecord,
)
from .orm_models import (
    AlertConfigurationORM,
    AuditLogORM,
    CertificateDocumentORM,
    CertificateTypeORM,
    DeletionTombstoneORM,
    EmailIntakeMessageORM,
    EmployeeORM,
    ExtractionRunORM,
    JobCursorORM,
    NotificationEventORM,
    PasswordResetTokenORM,
    RequirementAssignmentORM,
    VerifiedCertificateRecordORM,
)


# Hard cap for unbounded list queries. Prevents runaway memory consumption on
# endpoints that have not yet been migrated to full pagination.
_UNBOUNDED_QUERY_CAP = 10_000


class SqlRepository:
    """SQLAlchemy repository implementation."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session."""
        self.session = session

    # ==================== EMPLOYEE OPERATIONS ====================

    async def get_employee_by_id(self, employee_id: int) -> Optional[Employee]:
        """Get employee by ID."""
        stmt = select(EmployeeORM).where(EmployeeORM.id == employee_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._employee_orm_to_model(orm_obj) if orm_obj else None

    async def get_employee_by_email(self, email: str) -> Optional[Employee]:
        """Get employee by email."""
        stmt = select(EmployeeORM).where(EmployeeORM.email == email)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._employee_orm_to_model(orm_obj) if orm_obj else None

    async def get_employee_by_number(self, employee_number: str) -> Optional[Employee]:
        """Get employee by employee number."""
        stmt = select(EmployeeORM).where(EmployeeORM.employee_number == employee_number)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._employee_orm_to_model(orm_obj) if orm_obj else None

    async def list_employees(self) -> list[Employee]:
        """List all employees."""
        stmt = select(EmployeeORM).order_by(
            EmployeeORM.last_name, EmployeeORM.first_name
        )
        result = await self.session.execute(stmt)
        return [self._employee_orm_to_model(orm_obj) for orm_obj in result.scalars()]

    async def get_employees_by_role(self, role: str) -> list[Employee]:
        """
        Get all employees with a specific role.

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
        return [self._employee_orm_to_model(orm_obj) for orm_obj in result.scalars()]

    async def create_employee(self, employee: Employee) -> Employee:
        """Create a new employee."""
        orm_obj = EmployeeORM(
            employee_number=employee.employee_number,
            first_name=employee.first_name,
            last_name=employee.last_name,
            email=employee.email,
            role=employee.role.value,
            manager_id=employee.manager_id,
        )
        self.session.add(orm_obj)
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return self._employee_orm_to_model(orm_obj)

    async def update_employee_password(
        self, employee_id: int, password_hash: str
    ) -> None:
        """Update employee password hash and increment token_version to invalidate existing JWTs."""
        stmt = (
            update(EmployeeORM)
            .where(EmployeeORM.id == employee_id)
            .values(
                password_hash=password_hash,
                token_version=EmployeeORM.token_version + 1,
            )
        )
        await self.session.execute(stmt)

    async def update_password_hash_only(
        self, employee_id: int, password_hash: str
    ) -> None:
        """Update password hash WITHOUT bumping token_version (transparent Argon2id rehash)."""
        stmt = (
            update(EmployeeORM)
            .where(EmployeeORM.id == employee_id)
            .values(password_hash=password_hash)
        )
        await self.session.execute(stmt)

    async def update_employee_last_logout_at(
        self, employee_id: int, timestamp: datetime
    ) -> None:
        """Set last_logout_at to invalidate all refresh tokens issued before this time."""
        stmt = (
            update(EmployeeORM)
            .where(EmployeeORM.id == employee_id)
            .values(last_logout_at=timestamp)
        )
        await self.session.execute(stmt)

    async def create_password_reset_token(
        self, employee_id: int, token_hash: str, expires_at: datetime
    ) -> None:
        """Insert a new password reset token record."""
        orm_obj = PasswordResetTokenORM(
            employee_id=employee_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(orm_obj)
        await self.session.flush()

    async def get_password_reset_token_by_hash(
        self, token_hash: str
    ) -> Optional[PasswordResetToken]:
        """Fetch password reset token by its SHA-256 hash."""
        stmt = select(PasswordResetTokenORM).where(
            PasswordResetTokenORM.token_hash == token_hash
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._password_reset_token_orm_to_model(orm_obj) if orm_obj else None

    async def mark_password_reset_token_used(self, token_id: int) -> None:
        """Mark a password reset token as used by setting used_at."""
        stmt = (
            update(PasswordResetTokenORM)
            .where(PasswordResetTokenORM.id == token_id)
            .values(used_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    async def claim_password_reset_token(self, token_id: int) -> bool:
        """
        Atomically mark a password reset token as used.

        Uses a conditional UPDATE (WHERE used_at IS NULL) so that concurrent
        requests with the same token can only succeed once.

        Returns True if this call claimed the token (it was unused).
        Returns False if the token was already claimed (concurrent reuse attempt).
        """
        stmt = (
            update(PasswordResetTokenORM)
            .where(
                PasswordResetTokenORM.id == token_id,
                PasswordResetTokenORM.used_at.is_(None),
            )
            .values(used_at=datetime.now(timezone.utc))
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1

    def _password_reset_token_orm_to_model(
        self, orm_obj: PasswordResetTokenORM
    ) -> PasswordResetToken:
        """Convert ORM object to domain model."""
        return PasswordResetToken(
            id=orm_obj.id,
            employee_id=orm_obj.employee_id,
            token_hash=orm_obj.token_hash,
            expires_at=orm_obj.expires_at,
            created_at=orm_obj.created_at,
            used_at=orm_obj.used_at,
        )

    def _employee_orm_to_model(self, orm_obj: EmployeeORM) -> Employee:
        """Convert ORM object to domain model."""
        from .models import Role

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
            token_version=orm_obj.token_version,
            last_logout_at=orm_obj.last_logout_at,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at,
        )

    # ==================== CERTIFICATE TYPE OPERATIONS ====================

    async def get_certificate_type_by_id(
        self, cert_type_id: int
    ) -> Optional[CertificateType]:
        """Get certificate type by ID."""
        stmt = select(CertificateTypeORM).where(CertificateTypeORM.id == cert_type_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._cert_type_orm_to_model(orm_obj) if orm_obj else None

    async def get_certificate_type_by_name(
        self, name: str
    ) -> Optional[CertificateType]:
        """Get certificate type by name."""
        stmt = select(CertificateTypeORM).where(CertificateTypeORM.name == name)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._cert_type_orm_to_model(orm_obj) if orm_obj else None

    async def list_certificate_types(self) -> list[CertificateType]:
        """List all certificate types."""
        stmt = select(CertificateTypeORM).order_by(CertificateTypeORM.name)
        result = await self.session.execute(stmt)
        return [self._cert_type_orm_to_model(orm_obj) for orm_obj in result.scalars()]

    async def create_certificate_type(
        self, cert_type: CertificateType
    ) -> CertificateType:
        """Create a new certificate type."""
        orm_obj = CertificateTypeORM(
            name=cert_type.name,
            description=cert_type.description,
            validity_period_days=cert_type.validity_period_days,
        )
        self.session.add(orm_obj)
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return self._cert_type_orm_to_model(orm_obj)

    async def update_certificate_type(
        self, cert_type_id: int, updates: dict
    ) -> Optional[CertificateType]:
        """Update a certificate type. Returns None if not found."""
        stmt = select(CertificateTypeORM).where(CertificateTypeORM.id == cert_type_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if orm_obj is None:
            return None
        for field, value in updates.items():
            setattr(orm_obj, field, value)
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return self._cert_type_orm_to_model(orm_obj)

    async def delete_certificate_type(self, cert_type_id: int) -> bool:
        """Delete a certificate type. Returns True if deleted, False if not found."""
        stmt = select(CertificateTypeORM).where(CertificateTypeORM.id == cert_type_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if orm_obj is None:
            return False
        await self.session.delete(orm_obj)
        await self.session.flush()
        return True

    async def count_requirements_for_cert_type(self, cert_type_id: int) -> int:
        """Count requirement assignments referencing a certificate type."""
        stmt = (
            select(func.count())
            .select_from(RequirementAssignmentORM)
            .where(RequirementAssignmentORM.certificate_type_id == cert_type_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    def _cert_type_orm_to_model(self, orm_obj: CertificateTypeORM) -> CertificateType:
        """Convert ORM object to domain model."""
        return CertificateType(
            id=orm_obj.id,
            name=orm_obj.name,
            description=orm_obj.description,
            validity_period_days=orm_obj.validity_period_days,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at,
        )

    # ==================== REQUIREMENT OPERATIONS ====================

    async def create_requirement(
        self, requirement: RequirementAssignment
    ) -> RequirementAssignment:
        """Create a new requirement assignment."""
        orm_obj = RequirementAssignmentORM(
            employee_id=requirement.employee_id,
            certificate_type_id=requirement.certificate_type_id,
            due_date=requirement.due_date,
            status=requirement.status.value,
            created_by_id=requirement.created_by_id,
            requested_by_id=requirement.requested_by_id,
        )
        self.session.add(orm_obj)
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return self._requirement_orm_to_model(orm_obj)

    async def get_requirement_by_id(
        self, requirement_id: int
    ) -> Optional[RequirementAssignment]:
        """Get requirement by ID."""
        stmt = select(RequirementAssignmentORM).where(
            RequirementAssignmentORM.id == requirement_id
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._requirement_orm_to_model(orm_obj) if orm_obj else None

    async def list_all_requirements(
        self, limit: Optional[int] = _UNBOUNDED_QUERY_CAP
    ) -> list[RequirementAssignment]:
        """List all requirement assignments across all employees.

        Pass ``limit=None`` to bypass the safety cap (use only for endpoints
        that genuinely need every row, e.g. CSV/XLSX export and dashboard
        compliance counters that would otherwise silently undercount).
        """
        stmt = (
            select(RequirementAssignmentORM)
            .order_by(RequirementAssignmentORM.due_date)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return [self._requirement_orm_to_model(orm_obj) for orm_obj in result.scalars()]

    async def list_all_requirements_paginated(
        self,
        limit: int = 25,
        offset: int = 0,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[list[RequirementAssignment], int]:
        """List requirements with pagination, optional status filter, and optional search."""
        today = date.today()
        thirty_days = today + timedelta(days=30)

        # Build WHERE conditions for status filter
        status_cond = None
        if status_filter == "Overdue":
            status_cond = and_(
                RequirementAssignmentORM.due_date < today,
                RequirementAssignmentORM.satisfied_by_id.is_(None),
                RequirementAssignmentORM.waived_at.is_(None),
            )
        elif status_filter == "DueSoon":
            status_cond = and_(
                RequirementAssignmentORM.due_date >= today,
                RequirementAssignmentORM.due_date <= thirty_days,
                RequirementAssignmentORM.satisfied_by_id.is_(None),
                RequirementAssignmentORM.waived_at.is_(None),
            )
        elif status_filter == "InProgress":
            status_cond = and_(
                RequirementAssignmentORM.due_date > thirty_days,
                RequirementAssignmentORM.satisfied_by_id.is_(None),
                RequirementAssignmentORM.waived_at.is_(None),
            )
        elif status_filter == "Satisfied":
            status_cond = RequirementAssignmentORM.satisfied_by_id.is_not(None)
        elif status_filter == "Waived":
            status_cond = RequirementAssignmentORM.waived_at.is_not(None)

        # Build count query
        count_stmt = select(func.count()).select_from(RequirementAssignmentORM)
        # Build items query
        items_stmt = select(RequirementAssignmentORM)

        # Apply status filter
        if status_cond is not None:
            count_stmt = count_stmt.where(status_cond)
            items_stmt = items_stmt.where(status_cond)

        # Apply search (join with employees and certificate types)
        if search:
            escaped_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            search_term = f"%{escaped_search}%"
            items_stmt = items_stmt.join(
                EmployeeORM,
                RequirementAssignmentORM.employee_id == EmployeeORM.id,
            ).join(
                CertificateTypeORM,
                RequirementAssignmentORM.certificate_type_id == CertificateTypeORM.id,
            )
            count_stmt = count_stmt.join(
                EmployeeORM,
                RequirementAssignmentORM.employee_id == EmployeeORM.id,
            ).join(
                CertificateTypeORM,
                RequirementAssignmentORM.certificate_type_id == CertificateTypeORM.id,
            )
            search_cond = or_(
                (EmployeeORM.first_name + " " + EmployeeORM.last_name).ilike(search_term),
                EmployeeORM.first_name.ilike(search_term),
                EmployeeORM.last_name.ilike(search_term),
                CertificateTypeORM.name.ilike(search_term),
            )
            count_stmt = count_stmt.where(search_cond)
            items_stmt = items_stmt.where(search_cond)

        # Execute count
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        # Execute paginated items
        items_stmt = (
            items_stmt
            .order_by(RequirementAssignmentORM.due_date)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(items_stmt)
        items = [self._requirement_orm_to_model(orm_obj) for orm_obj in result.scalars()]

        return items, total

    async def list_requirements_for_employee(
        self, employee_id: int
    ) -> list[RequirementAssignment]:
        """List all requirements for an employee."""
        stmt = (
            select(RequirementAssignmentORM)
            .where(RequirementAssignmentORM.employee_id == employee_id)
            .order_by(RequirementAssignmentORM.due_date)
        )
        result = await self.session.execute(stmt)
        return [self._requirement_orm_to_model(orm_obj) for orm_obj in result.scalars()]

    async def list_requirements_due_between(
        self, start_date: date, end_date: date
    ) -> list[RequirementAssignment]:
        """List requirements due between dates."""
        stmt = (
            select(RequirementAssignmentORM)
            .where(
                and_(
                    RequirementAssignmentORM.due_date >= start_date,
                    RequirementAssignmentORM.due_date <= end_date,
                )
            )
            .order_by(RequirementAssignmentORM.due_date)
        )
        result = await self.session.execute(stmt)
        return [self._requirement_orm_to_model(orm_obj) for orm_obj in result.scalars()]

    async def update_requirement_status(self, requirement_id: int, status: str) -> None:
        """Update requirement status."""
        stmt = (
            update(RequirementAssignmentORM)
            .where(RequirementAssignmentORM.id == requirement_id)
            .values(status=status)
        )
        await self.session.execute(stmt)

    async def link_requirement_if_unset(
        self,
        requirement_id: int,
        verified_record_id: int,
        expected_employee_id: int,
        expected_certificate_type_id: int,
    ) -> bool:
        """Atomically satisfy one compatible, open, unwaived requirement."""
        stmt = (
            update(RequirementAssignmentORM)
            .where(
                and_(
                    RequirementAssignmentORM.id == requirement_id,
                    RequirementAssignmentORM.satisfied_by_id == None,
                    RequirementAssignmentORM.waived_at == None,
                    RequirementAssignmentORM.employee_id == expected_employee_id,
                    RequirementAssignmentORM.certificate_type_id
                    == expected_certificate_type_id,
                    RequirementAssignmentORM.status.notin_(("Satisfied", "Waived")),
                )
            )
            .values(satisfied_by_id=verified_record_id, status="Satisfied")
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1

    async def find_open_requirement_by_cert_type(
        self, employee_id: int, certificate_type_name: str
    ) -> Optional[int]:
        """Find an unsatisfied requirement matching employee + cert type name.

        Matching is exact-then-fuzzy. The exact match is the fast path. If
        no exact hit, fall back to a case-insensitive substring (contains)
        match to handle cases where the extraction emits a short canonical
        name (e.g. "HIPAA Privacy & Security Training") while the seeded
        type carries a parenthetical qualifier (e.g. "... (HB 300 - Texas)").
        Without this, requirements never auto-link for any cert type whose
        seeded name has a suffix the cert artwork does not include.

        Fail-stop on ambiguous fuzzy matches: the fallback fetches up to
        2 candidates and returns ``None`` when both come back, so a
        Coordinator must manually link via ``request.requirement_id``
        instead of risking an auto-link to the wrong requirement (e.g.
        "First Aid - Basic" vs. "First Aid - Advanced"). The exact path
        is never affected because exact matches are unambiguous by
        definition for a given (employee_id, name) pair.
        """
        # Try exact match first
        exact_stmt = (
            select(RequirementAssignmentORM.id)
            .join(
                CertificateTypeORM,
                CertificateTypeORM.id == RequirementAssignmentORM.certificate_type_id,
            )
            .where(
                and_(
                    RequirementAssignmentORM.employee_id == employee_id,
                    CertificateTypeORM.name == certificate_type_name,
                    RequirementAssignmentORM.satisfied_by_id == None,
                )
            )
            .order_by(RequirementAssignmentORM.due_date)
            .limit(1)
        )
        result = await self.session.execute(exact_stmt)
        rid = result.scalar_one_or_none()
        if rid is not None:
            return rid

        # Fallback: case-insensitive substring match (contains).
        # Escape LIKE metacharacters in the user-supplied name to keep the
        # match literal (substring search must not interpret % or _).
        escaped = (
            certificate_type_name.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        fuzzy_stmt = (
            select(RequirementAssignmentORM.id)
            .join(
                CertificateTypeORM,
                CertificateTypeORM.id == RequirementAssignmentORM.certificate_type_id,
            )
            .where(
                and_(
                    RequirementAssignmentORM.employee_id == employee_id,
                    CertificateTypeORM.name.ilike(f"%{escaped}%", escape="\\"),
                    RequirementAssignmentORM.satisfied_by_id == None,
                )
            )
            .order_by(RequirementAssignmentORM.due_date)
            .limit(2)
        )
        result = await self.session.execute(fuzzy_stmt)
        rows = result.scalars().all()
        if len(rows) >= 2:
            # Ambiguous: refuse to auto-link. Coordinator must pick the
            # right requirement explicitly via request.requirement_id.
            return None
        return rows[0] if rows else None

    async def waive_requirement(
        self,
        requirement_id: int,
        waived_by_id: int,
        reason: str,
        expiration: Optional[date] = None,
    ) -> None:
        """Mark requirement as waived."""
        from .models import RequirementStatus

        stmt = (
            update(RequirementAssignmentORM)
            .where(RequirementAssignmentORM.id == requirement_id)
            .values(
                status=RequirementStatus.WAIVED.value,
                waived_at=datetime.now(timezone.utc),
                waived_by_id=waived_by_id,
                waiver_reason=reason,
                waiver_expiration=expiration,
            )
        )
        await self.session.execute(stmt)

    async def unwaive_requirement(self, requirement_id: int) -> None:
        """
        Restore a waived requirement to active status.

        Clears all waiver fields and sets status based on current state:
        - If satisfied_by_id is set, status becomes Satisfied
        - Otherwise, status becomes NotStarted
        """
        from .models import RequirementStatus

        # First get the requirement to check if it's satisfied
        stmt = select(RequirementAssignmentORM).where(
            RequirementAssignmentORM.id == requirement_id
        )
        result = await self.session.execute(stmt)
        requirement = result.scalar_one_or_none()

        if not requirement:
            return

        # Determine new status
        if requirement.satisfied_by_id is not None:
            new_status = RequirementStatus.SATISFIED.value
        else:
            new_status = RequirementStatus.NOT_STARTED.value

        # Clear waiver fields and update status
        stmt = (
            update(RequirementAssignmentORM)
            .where(RequirementAssignmentORM.id == requirement_id)
            .values(
                status=new_status,
                waived_at=None,
                waived_by_id=None,
                waiver_reason=None,
                waiver_expiration=None,
            )
        )
        await self.session.execute(stmt)

    def _requirement_orm_to_model(
        self, orm_obj: RequirementAssignmentORM
    ) -> RequirementAssignment:
        """Convert ORM object to domain model."""
        from .models import RequirementStatus

        return RequirementAssignment(
            id=orm_obj.id,
            employee_id=orm_obj.employee_id,
            certificate_type_id=orm_obj.certificate_type_id,
            due_date=orm_obj.due_date,
            status=RequirementStatus(orm_obj.status),
            satisfied_by_id=orm_obj.satisfied_by_id,
            waived_at=orm_obj.waived_at,
            waived_by_id=orm_obj.waived_by_id,
            waiver_reason=orm_obj.waiver_reason,
            waiver_expiration=orm_obj.waiver_expiration,
            created_by_id=orm_obj.created_by_id,
            requested_by_id=orm_obj.requested_by_id,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at,
        )

    # ==================== DOCUMENT OPERATIONS ====================

    async def create_document(
        self, document: CertificateDocument
    ) -> CertificateDocument:
        """Create a new document record."""
        orm_obj = CertificateDocumentORM(
            employee_id=document.employee_id,
            storage_key=document.storage_key,
            file_name=document.file_name,
            file_type=document.file_type,
            file_size_bytes=document.file_size_bytes,
            uploaded_by_id=document.uploaded_by_id,
            acting_as=document.acting_as,
            intake_channel=document.intake_channel.value,
            source_email_message_id=document.source_email_message_id,
            target_requirement_id=document.target_requirement_id,
            file_hash=document.file_hash,
        )
        self.session.add(orm_obj)
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return self._document_orm_to_model(orm_obj)

    async def get_document_by_employee_and_hash(
        self,
        employee_id: int,
        file_hash: str,
    ) -> Optional[CertificateDocument]:
        """
        Find existing document by employee and file hash for deduplication.

        Only returns non-deleted documents.

        Args:
            employee_id: Employee ID
            file_hash: SHA-256 hash of file content

        Returns:
            Existing document if found, None otherwise
        """
        stmt = select(CertificateDocumentORM).where(
            and_(
                CertificateDocumentORM.employee_id == employee_id,
                CertificateDocumentORM.file_hash == file_hash,
                CertificateDocumentORM.deleted_at == None,
            )
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._document_orm_to_model(orm_obj) if orm_obj else None

    async def get_document_by_id(
        self, document_id: int
    ) -> Optional[CertificateDocument]:
        """Get non-deleted document by ID."""
        stmt = select(CertificateDocumentORM).where(
            and_(
                CertificateDocumentORM.id == document_id,
                CertificateDocumentORM.deleted_at == None,
            )
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._document_orm_to_model(orm_obj) if orm_obj else None

    async def list_documents_for_employee(
        self, employee_id: int
    ) -> list[CertificateDocument]:
        """List non-deleted documents for an employee."""
        stmt = (
            select(CertificateDocumentORM)
            .where(
                and_(
                    CertificateDocumentORM.employee_id == employee_id,
                    CertificateDocumentORM.deleted_at == None,
                )
            )
            .order_by(CertificateDocumentORM.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._document_orm_to_model(orm_obj) for orm_obj in result.scalars()]

    def _document_orm_to_model(
        self, orm_obj: CertificateDocumentORM
    ) -> CertificateDocument:
        """Convert ORM object to domain model."""
        return CertificateDocument(
            id=orm_obj.id,
            employee_id=orm_obj.employee_id,
            storage_key=orm_obj.storage_key,
            file_name=orm_obj.file_name,
            file_type=orm_obj.file_type,
            file_size_bytes=orm_obj.file_size_bytes,
            uploaded_by_id=orm_obj.uploaded_by_id,
            acting_as=orm_obj.acting_as,
            intake_channel=IntakeChannel(orm_obj.intake_channel),
            source_email_message_id=orm_obj.source_email_message_id,
            target_requirement_id=orm_obj.target_requirement_id,
            file_hash=orm_obj.file_hash,
            created_at=orm_obj.created_at,
        )

    # ==================== EXTRACTION OPERATIONS ====================

    async def create_extraction(self, extraction: ExtractionRun) -> ExtractionRun:
        """Create a new extraction run."""
        orm_obj = ExtractionRunORM(
            document_id=extraction.document_id,
            review_state=extraction.review_state.value,
            extracted_fields=extraction.extracted_fields,
            needs_review=extraction.needs_review,
            needs_review_reasons=extraction.needs_review_reasons,
            template_id=extraction.template_id,
            template_version=extraction.template_version,
            template_match_evidence=extraction.template_match_evidence,
            review_assist=extraction.review_assist,
            field_evidence=extraction.field_evidence,
        )
        self.session.add(orm_obj)
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return self._extraction_orm_to_model(orm_obj)

    async def get_extraction_by_id(self, extraction_id: int) -> Optional[ExtractionRun]:
        """Get extraction by ID."""
        stmt = select(ExtractionRunORM).where(ExtractionRunORM.id == extraction_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._extraction_orm_to_model(orm_obj) if orm_obj else None

    async def get_extraction_by_document_id(
        self, document_id: int
    ) -> Optional[ExtractionRun]:
        """Get the most recent extraction for a document."""
        stmt = (
            select(ExtractionRunORM)
            .where(ExtractionRunORM.document_id == document_id)
            .order_by(ExtractionRunORM.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._extraction_orm_to_model(orm_obj) if orm_obj else None

    async def update_extraction_results(
        self,
        extraction_id: int,
        extracted_fields: dict,
        needs_review: bool,
        needs_review_reasons: list[str],
        template_id: Optional[str] = None,
        template_version: Optional[int] = None,
        template_match_evidence: Optional[dict] = None,
        review_assist: Optional[dict] = None,
        field_evidence: Optional[dict] = None,
        expected_state: ReviewState = ReviewState.PROCESSING,
        expected_version: int = 0,
        new_state: ReviewState = ReviewState.PENDING_REVIEW,
    ) -> Optional[ExtractionRun]:
        """Atomically persist results only while the expected state is current."""
        stmt = (
            update(ExtractionRunORM)
            .where(
                and_(
                    ExtractionRunORM.id == extraction_id,
                    ExtractionRunORM.review_state == expected_state.value,
                    ExtractionRunORM.review_state_version == expected_version,
                )
            )
            .values(
                extracted_fields=extracted_fields,
                needs_review=needs_review,
                needs_review_reasons=needs_review_reasons,
                template_id=template_id,
                template_version=template_version,
                template_match_evidence=template_match_evidence,
                review_assist=review_assist,
                field_evidence=field_evidence,
                review_state=new_state.value,
                review_state_version=expected_version + 1,
            )
            .returning(ExtractionRunORM.id)
        )
        result = await self.session.execute(stmt)
        updated_id = result.scalar_one_or_none()
        if updated_id is None:
            return None

        await self.session.flush()
        refreshed = await self.session.execute(
            select(ExtractionRunORM).where(ExtractionRunORM.id == updated_id)
        )
        orm_obj = refreshed.scalar_one()
        return self._extraction_orm_to_model(orm_obj)

    async def update_document_file_type(
        self,
        document_id: int,
        file_type: str,
        file_size_bytes: int,
    ) -> None:
        """Update document file type and size after image-to-PDF conversion."""
        stmt = (
            update(CertificateDocumentORM)
            .where(CertificateDocumentORM.id == document_id)
            .values(file_type=file_type, file_size_bytes=file_size_bytes)
        )
        await self.session.execute(stmt)

    async def list_extractions_by_state(
        self, state: ReviewState
    ) -> list[ExtractionRun]:
        """List extractions by review state."""
        stmt = (
            select(ExtractionRunORM)
            .where(ExtractionRunORM.review_state == state.value)
            .order_by(ExtractionRunORM.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._extraction_orm_to_model(orm_obj) for orm_obj in result.scalars()]

    async def list_all_extractions(
        self, limit: Optional[int] = _UNBOUNDED_QUERY_CAP
    ) -> list[ExtractionRun]:
        """List all extractions regardless of review state.

        Pass ``limit=None`` to bypass the safety cap. Same pattern as
        ``list_all_requirements`` — needed by callers that compute aggregate
        state across the full table (e.g. dashboard counters) so they don't
        silently truncate at 10k.
        """
        stmt = (
            select(ExtractionRunORM)
            .order_by(ExtractionRunORM.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return [self._extraction_orm_to_model(orm_obj) for orm_obj in result.scalars()]

    async def try_transition_extraction_review_state(
        self,
        extraction_id: int,
        expected_state: ReviewState,
        expected_version: int,
        new_state: ReviewState,
        reviewed_by_id: Optional[int] = None,
    ) -> bool:
        """
        Attempt to transition extraction review state with optimistic locking.
        Returns True if transition succeeded, False if version conflict.
        """
        stmt = (
            update(ExtractionRunORM)
            .where(
                and_(
                    ExtractionRunORM.id == extraction_id,
                    ExtractionRunORM.review_state == expected_state.value,
                    ExtractionRunORM.review_state_version == expected_version,
                )
            )
            .values(
                review_state=new_state.value,
                review_state_version=expected_version + 1,
                reviewed_by_id=reviewed_by_id,
                reviewed_at=datetime.now(timezone.utc) if reviewed_by_id else None,
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1

    def _extraction_orm_to_model(self, orm_obj: ExtractionRunORM) -> ExtractionRun:
        """Convert ORM object to domain model."""
        return ExtractionRun(
            id=orm_obj.id,
            document_id=orm_obj.document_id,
            review_state=ReviewState(orm_obj.review_state),
            extracted_fields=orm_obj.extracted_fields,
            needs_review=orm_obj.needs_review,
            needs_review_reasons=orm_obj.needs_review_reasons,
            template_id=orm_obj.template_id,
            template_version=orm_obj.template_version,
            template_match_evidence=orm_obj.template_match_evidence,
            review_assist=orm_obj.review_assist,
            field_evidence=orm_obj.field_evidence,
            reviewed_by_id=orm_obj.reviewed_by_id,
            reviewed_at=orm_obj.reviewed_at,
            review_state_version=orm_obj.review_state_version,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at,
        )

    # ==================== VERIFIED RECORD OPERATIONS ====================

    async def insert_verified_record_idempotent(
        self, record: VerifiedCertificateRecord
    ) -> VerifiedCertificateRecord:
        """
        Insert verified record with idempotency guarantee on extraction_id.
        Returns existing record if already exists.
        """
        # Try to insert
        orm_obj = VerifiedCertificateRecordORM(
            extraction_id=record.extraction_id,
            document_id=record.document_id,
            employee_id=record.employee_id,
            certificate_holder_name=record.certificate_holder_name,
            certificate_type=record.certificate_type,
            certificate_number=record.certificate_number,
            issuing_authority=record.issuing_authority,
            issue_date=record.issue_date,
            expiration_date=record.expiration_date,
            training_hours=record.training_hours,
            license_class=record.license_class,
            endorsements=record.endorsements,
            reviewed_by_id=record.reviewed_by_id,
            reviewed_at=record.reviewed_at,
            field_provenance=record.field_provenance,
        )
        # SAVEPOINT so a duplicate extraction_id only rolls back this insert,
        # not any prior work in the enclosing review transaction.
        try:
            async with self.session.begin_nested():
                self.session.add(orm_obj)
                await self.session.flush()
            await self.session.refresh(orm_obj)
            return self._verified_record_orm_to_model(orm_obj)
        except IntegrityError:
            # Record already exists, fetch it (outer transaction is intact).
            stmt = select(VerifiedCertificateRecordORM).where(
                VerifiedCertificateRecordORM.extraction_id == record.extraction_id
            )
            result = await self.session.execute(stmt)
            existing = result.scalar_one()
            return self._verified_record_orm_to_model(existing)

    async def get_verified_record_by_extraction_id(
        self, extraction_id: int
    ) -> Optional[VerifiedCertificateRecord]:
        """Get verified record by extraction ID."""
        stmt = select(VerifiedCertificateRecordORM).where(
            VerifiedCertificateRecordORM.extraction_id == extraction_id
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._verified_record_orm_to_model(orm_obj) if orm_obj else None

    async def list_verified_records_for_employee(
        self, employee_id: int
    ) -> list[VerifiedCertificateRecord]:
        """List all verified records for an employee."""
        stmt = (
            select(VerifiedCertificateRecordORM)
            .where(VerifiedCertificateRecordORM.employee_id == employee_id)
            .order_by(VerifiedCertificateRecordORM.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [
            self._verified_record_orm_to_model(orm_obj) for orm_obj in result.scalars()
        ]

    async def list_verified_records(
        self,
        employee_id: Optional[int] = None,
        certificate_type: Optional[str] = None,
    ) -> list[VerifiedCertificateRecord]:
        """
        List verified records with optional filters.

        Args:
            employee_id: Filter by employee ID (None for all employees)
            certificate_type: Filter by certificate type name

        Returns:
            List of matching verified records
        """
        stmt = select(VerifiedCertificateRecordORM)

        conditions = []
        if employee_id is not None:
            conditions.append(VerifiedCertificateRecordORM.employee_id == employee_id)
        if certificate_type is not None:
            conditions.append(
                VerifiedCertificateRecordORM.certificate_type == certificate_type
            )

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.order_by(VerifiedCertificateRecordORM.created_at.desc())

        result = await self.session.execute(stmt)
        return [
            self._verified_record_orm_to_model(orm_obj) for orm_obj in result.scalars()
        ]

    async def get_verified_record_by_id(
        self, record_id: int
    ) -> Optional[VerifiedCertificateRecord]:
        """Get verified record by ID."""
        stmt = select(VerifiedCertificateRecordORM).where(
            VerifiedCertificateRecordORM.id == record_id
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._verified_record_orm_to_model(orm_obj) if orm_obj else None

    async def list_verified_records_expiring_between(
        self,
        start_date: date,
        end_date: date,
    ) -> list[VerifiedCertificateRecord]:
        """List verified records expiring between dates."""
        stmt = (
            select(VerifiedCertificateRecordORM)
            .where(
                and_(
                    VerifiedCertificateRecordORM.expiration_date >= start_date,
                    VerifiedCertificateRecordORM.expiration_date <= end_date,
                )
            )
            .order_by(VerifiedCertificateRecordORM.expiration_date)
        )
        result = await self.session.execute(stmt)
        return [
            self._verified_record_orm_to_model(orm_obj) for orm_obj in result.scalars()
        ]

    async def list_verified_records_created_between(
        self,
        start_date: date,
        end_date: date,
    ) -> list[VerifiedCertificateRecord]:
        """List verified records created between dates (inclusive)."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        stmt = (
            select(VerifiedCertificateRecordORM)
            .where(
                and_(
                    VerifiedCertificateRecordORM.created_at >= start_dt,
                    VerifiedCertificateRecordORM.created_at <= end_dt,
                )
            )
            .order_by(VerifiedCertificateRecordORM.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [
            self._verified_record_orm_to_model(orm_obj) for orm_obj in result.scalars()
        ]

    def _verified_record_orm_to_model(
        self, orm_obj: VerifiedCertificateRecordORM
    ) -> VerifiedCertificateRecord:
        """Convert ORM object to domain model."""
        return VerifiedCertificateRecord(
            id=orm_obj.id,
            extraction_id=orm_obj.extraction_id,
            document_id=orm_obj.document_id,
            employee_id=orm_obj.employee_id,
            certificate_holder_name=orm_obj.certificate_holder_name,
            certificate_type=orm_obj.certificate_type,
            certificate_number=orm_obj.certificate_number,
            issuing_authority=orm_obj.issuing_authority,
            issue_date=orm_obj.issue_date,
            expiration_date=orm_obj.expiration_date,
            training_hours=orm_obj.training_hours,
            license_class=orm_obj.license_class,
            endorsements=orm_obj.endorsements,
            reviewed_by_id=orm_obj.reviewed_by_id,
            reviewed_at=orm_obj.reviewed_at,
            field_provenance=orm_obj.field_provenance,
            created_at=orm_obj.created_at,
        )

    # ==================== NOTIFICATION OPERATIONS ====================

    async def insert_notification_if_absent(
        self, notification: NotificationEvent
    ) -> bool:
        """
        Insert notification with idempotency guarantee on dedupe_key.
        Returns True if inserted, False if already exists.
        """
        orm_obj = NotificationEventORM(
            notification_type=notification.notification_type.value,
            recipient_employee_id=notification.recipient_employee_id,
            subject=notification.subject,
            body=notification.body,
            dedupe_key=notification.dedupe_key,
            related_requirement_id=notification.related_requirement_id,
            related_certificate_id=notification.related_certificate_id,
            effective_date=notification.effective_date,
        )

        # Wrap the insert in a SAVEPOINT so a dedupe collision only rolls back
        # this one row. A plain session.rollback() would discard every
        # notification already flushed in the same daily-generation batch.
        try:
            async with self.session.begin_nested():
                self.session.add(orm_obj)
                await self.session.flush()
            return True
        except IntegrityError:
            return False

    async def list_undelivered_notifications(
        self, limit: int = 5000
    ) -> list[NotificationEvent]:
        """List undelivered notifications ordered by recipient then creation time."""
        stmt = (
            select(NotificationEventORM)
            .where(NotificationEventORM.delivered == False)
            .order_by(
                NotificationEventORM.recipient_employee_id,
                NotificationEventORM.created_at,
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            self._notification_orm_to_model(orm_obj) for orm_obj in result.scalars()
        ]

    async def mark_notification_delivered(self, notification_id: int) -> None:
        """Mark notification as delivered."""
        stmt = (
            update(NotificationEventORM)
            .where(NotificationEventORM.id == notification_id)
            .values(delivered=True, delivered_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    async def mark_notifications_delivered_batch(
        self, notification_ids: list[int]
    ) -> None:
        """Mark multiple notifications as delivered in a single UPDATE."""
        if not notification_ids:
            return
        stmt = (
            update(NotificationEventORM)
            .where(NotificationEventORM.id.in_(notification_ids))
            .values(delivered=True, delivered_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    async def mark_notification_read(self, notification_id: int) -> None:
        """Mark notification as read."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(NotificationEventORM)
            .where(NotificationEventORM.id == notification_id)
            .values(read=True, read_at=now)
        )
        await self.session.execute(stmt)

    async def list_notifications_for_user(
        self,
        employee_id: int,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[NotificationEvent]:
        """
        List notifications for a specific user.

        Args:
            employee_id: ID of the recipient employee
            unread_only: If True, only return unread (not delivered) notifications
            limit: Maximum number of results

        Returns:
            List of notifications ordered by creation date (newest first)
        """
        stmt = select(NotificationEventORM).where(
            NotificationEventORM.recipient_employee_id == employee_id
        )

        if unread_only:
            stmt = stmt.where(NotificationEventORM.read == False)

        stmt = stmt.order_by(NotificationEventORM.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return [
            self._notification_orm_to_model(orm_obj) for orm_obj in result.scalars()
        ]

    async def get_notification_by_id(
        self, notification_id: int
    ) -> Optional[NotificationEvent]:
        """Get notification by ID."""
        stmt = select(NotificationEventORM).where(
            NotificationEventORM.id == notification_id
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._notification_orm_to_model(orm_obj) if orm_obj else None

    async def mark_all_notifications_read(self, employee_id: int) -> int:
        """
        Mark all notifications as read for a user.

        Args:
            employee_id: ID of the recipient employee

        Returns:
            Number of notifications marked as read
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(NotificationEventORM)
            .where(
                and_(
                    NotificationEventORM.recipient_employee_id == employee_id,
                    NotificationEventORM.read == False,
                )
            )
            .values(read=True, read_at=now)
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def count_unread_notifications(self, employee_id: int) -> int:
        """Count unread notifications for a user."""
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(NotificationEventORM)
            .where(
                and_(
                    NotificationEventORM.recipient_employee_id == employee_id,
                    NotificationEventORM.read == False,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    def _notification_orm_to_model(
        self, orm_obj: NotificationEventORM
    ) -> NotificationEvent:
        """Convert ORM object to domain model."""
        from .models import NotificationType

        return NotificationEvent(
            id=orm_obj.id,
            notification_type=NotificationType(orm_obj.notification_type),
            recipient_employee_id=orm_obj.recipient_employee_id,
            subject=orm_obj.subject,
            body=orm_obj.body,
            dedupe_key=orm_obj.dedupe_key,
            related_requirement_id=orm_obj.related_requirement_id,
            related_certificate_id=orm_obj.related_certificate_id,
            effective_date=orm_obj.effective_date,
            delivered=orm_obj.delivered,
            delivered_at=orm_obj.delivered_at,
            read=orm_obj.read,
            read_at=orm_obj.read_at,
            created_at=orm_obj.created_at,
        )

    # ==================== ALERT CONFIGURATION OPERATIONS ====================

    async def get_alert_configuration(self) -> Optional[AlertConfiguration]:
        """Get the singleton alert configuration (id=1)."""
        stmt = select(AlertConfigurationORM).where(AlertConfigurationORM.id == 1)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._alert_config_orm_to_model(orm_obj) if orm_obj else None

    async def update_alert_configuration(
        self, config: AlertConfiguration
    ) -> AlertConfiguration:
        """Update the singleton alert configuration."""
        stmt = (
            update(AlertConfigurationORM)
            .where(AlertConfigurationORM.id == 1)
            .values(
                requirement_reminder_days=config.requirement_reminder_days,
                certificate_reminder_days=config.certificate_reminder_days,
                daily_overdue_enabled=config.daily_overdue_enabled,
                global_send_hour=config.global_send_hour,
                global_send_minute=config.global_send_minute,
                updated_by_id=config.updated_by_id,
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

        # Return updated config
        return await self.get_alert_configuration()

    def _alert_config_orm_to_model(
        self, orm_obj: AlertConfigurationORM
    ) -> AlertConfiguration:
        """Convert ORM object to domain model."""
        return AlertConfiguration(
            id=orm_obj.id,
            requirement_reminder_days=list(orm_obj.requirement_reminder_days),
            certificate_reminder_days=list(orm_obj.certificate_reminder_days),
            daily_overdue_enabled=orm_obj.daily_overdue_enabled,
            global_send_hour=orm_obj.global_send_hour,
            global_send_minute=orm_obj.global_send_minute,
            updated_at=orm_obj.updated_at,
            updated_by_id=orm_obj.updated_by_id,
        )

    # ==================== JOB CURSOR OPERATIONS ====================

    async def upsert_job_cursor(self, cursor: JobCursor) -> None:
        """
        Upsert job cursor with monotonic date guarantee.
        Raises ValueError if new date is before existing date.
        """
        # Check existing cursor
        stmt = select(JobCursorORM).where(JobCursorORM.job_name == cursor.job_name)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing and cursor.last_success_date < existing.last_success_date:
            raise ValueError(
                f"Cannot move cursor backwards: {existing.last_success_date} -> {cursor.last_success_date}"
            )

        # Upsert
        if existing:
            stmt = (
                update(JobCursorORM)
                .where(JobCursorORM.job_name == cursor.job_name)
                .values(last_success_date=cursor.last_success_date)
            )
            await self.session.execute(stmt)
        else:
            orm_obj = JobCursorORM(
                job_name=cursor.job_name,
                last_success_date=cursor.last_success_date,
            )
            self.session.add(orm_obj)

    async def get_job_cursor(self, job_name: str) -> Optional[JobCursor]:
        """Get job cursor by name."""
        stmt = select(JobCursorORM).where(JobCursorORM.job_name == job_name)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._job_cursor_orm_to_model(orm_obj) if orm_obj else None

    def _job_cursor_orm_to_model(self, orm_obj: JobCursorORM) -> JobCursor:
        """Convert ORM object to domain model."""
        return JobCursor(
            job_name=orm_obj.job_name,
            last_success_date=orm_obj.last_success_date,
            updated_at=orm_obj.updated_at,
        )

    # ==================== AUDIT LOG OPERATIONS ====================

    async def create_audit_log(self, log: AuditLog) -> AuditLog:
        """Create an audit log entry."""
        orm_obj = AuditLogORM(
            actor_type=log.actor_type.value,
            employee_id=log.employee_id,
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            details=log.details,
            initiated_by_id=log.initiated_by_id,
            actor_role=log.actor_role,
            correlation_id=log.correlation_id,
            source_service=log.source_service,
            outcome=log.outcome,
            ip_address=log.ip_address,
        )
        # Set occurred_at_utc if caller provided it; otherwise DB default (now()) applies
        if log.occurred_at_utc is not None:
            orm_obj.occurred_at_utc = log.occurred_at_utc
        self.session.add(orm_obj)
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return self._audit_log_orm_to_model(orm_obj)

    async def list_audit_logs(
        self,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        action: Optional[str] = None,
        employee_id: Optional[int] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        source_service: Optional[str] = None,
        outcome: Optional[str] = None,
        actor_role: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[AuditLog], int]:
        """List audit logs with optional filters, pagination, and total count."""
        conditions = []
        if target_type:
            conditions.append(AuditLogORM.target_type == target_type)
        if target_id:
            conditions.append(AuditLogORM.target_id == target_id)
        if action:
            conditions.append(AuditLogORM.action == action)
        if employee_id is not None:
            conditions.append(AuditLogORM.employee_id == employee_id)
        if created_after is not None:
            conditions.append(AuditLogORM.occurred_at_utc >= created_after)
        if created_before is not None:
            conditions.append(AuditLogORM.occurred_at_utc < created_before)
        if source_service:
            conditions.append(AuditLogORM.source_service == source_service)
        if outcome:
            conditions.append(AuditLogORM.outcome == outcome)
        if actor_role:
            conditions.append(AuditLogORM.actor_role == actor_role)

        where_clause = and_(*conditions) if conditions else True

        # Count total matching rows
        count_stmt = select(func.count()).select_from(AuditLogORM).where(where_clause)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch page
        stmt = (
            select(AuditLogORM)
            .where(where_clause)
            .order_by(AuditLogORM.occurred_at_utc.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        items = [self._audit_log_orm_to_model(orm_obj) for orm_obj in result.scalars()]

        return items, total

    async def get_audit_log_by_id(self, log_id: int) -> Optional[AuditLog]:
        """Get audit log by ID."""
        stmt = select(AuditLogORM).where(AuditLogORM.id == log_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._audit_log_orm_to_model(orm_obj) if orm_obj else None

    def _audit_log_orm_to_model(self, orm_obj: AuditLogORM) -> AuditLog:
        """Convert ORM object to domain model."""
        return AuditLog(
            id=orm_obj.id,
            actor_type=AuditActorType(orm_obj.actor_type),
            employee_id=orm_obj.employee_id,
            action=orm_obj.action,
            target_type=orm_obj.target_type,
            target_id=orm_obj.target_id,
            details=orm_obj.details,
            initiated_by_id=orm_obj.initiated_by_id,
            occurred_at_utc=orm_obj.occurred_at_utc,
            recorded_at_utc=orm_obj.recorded_at_utc,
            actor_role=orm_obj.actor_role,
            correlation_id=orm_obj.correlation_id,
            source_service=orm_obj.source_service,
            outcome=orm_obj.outcome,
            ip_address=orm_obj.ip_address,
        )

    # ==================== EMAIL INTAKE OPERATIONS ====================

    async def create_email_intake_message(
        self, message: EmailIntakeMessage
    ) -> EmailIntakeMessage:
        """Create an email intake message record."""
        orm_obj = EmailIntakeMessageORM(
            message_id=message.message_id,
            from_address=message.from_address,
            received_at=message.received_at,
            subject=message.subject,
            attachment_count=message.attachment_count,
            processing_state=message.processing_state.value,
            error_reason=message.error_reason,
            employee_id=message.employee_id,
            attachment_hashes=message.attachment_hashes,
        )
        self.session.add(orm_obj)
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return self._email_intake_message_orm_to_model(orm_obj)

    async def get_email_intake_message_by_message_id(
        self, message_id: str
    ) -> Optional[EmailIntakeMessage]:
        """Get email intake message by provider message ID (for idempotency)."""
        stmt = select(EmailIntakeMessageORM).where(
            EmailIntakeMessageORM.message_id == message_id
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._email_intake_message_orm_to_model(orm_obj) if orm_obj else None

    async def get_email_intake_message_by_id(
        self, intake_id: int
    ) -> Optional[EmailIntakeMessage]:
        """Get email intake message by ID."""
        stmt = select(EmailIntakeMessageORM).where(
            EmailIntakeMessageORM.id == intake_id
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._email_intake_message_orm_to_model(orm_obj) if orm_obj else None

    async def list_email_intake_messages(
        self,
        processing_state: Optional[EmailProcessingState] = None,
        limit: int = 100,
    ) -> list[EmailIntakeMessage]:
        """List email intake messages with optional filter by state."""
        stmt = select(EmailIntakeMessageORM)

        if processing_state:
            stmt = stmt.where(
                EmailIntakeMessageORM.processing_state == processing_state.value
            )

        stmt = stmt.order_by(EmailIntakeMessageORM.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return [
            self._email_intake_message_orm_to_model(orm_obj)
            for orm_obj in result.scalars()
        ]

    async def update_email_intake_message_state(
        self,
        intake_id: int,
        state: EmailProcessingState,
        error_reason: Optional[str] = None,
        employee_id: Optional[int] = None,
    ) -> None:
        """Update email intake message processing state."""
        values = {"processing_state": state.value}
        if error_reason is not None:
            values["error_reason"] = error_reason
        if employee_id is not None:
            values["employee_id"] = employee_id

        stmt = (
            update(EmailIntakeMessageORM)
            .where(EmailIntakeMessageORM.id == intake_id)
            .values(**values)
        )
        await self.session.execute(stmt)

    def _email_intake_message_orm_to_model(
        self, orm_obj: EmailIntakeMessageORM
    ) -> EmailIntakeMessage:
        """Convert ORM object to domain model."""
        return EmailIntakeMessage(
            id=orm_obj.id,
            message_id=orm_obj.message_id,
            from_address=orm_obj.from_address,
            received_at=orm_obj.received_at,
            subject=orm_obj.subject,
            attachment_count=orm_obj.attachment_count,
            processing_state=EmailProcessingState(orm_obj.processing_state),
            error_reason=orm_obj.error_reason,
            employee_id=orm_obj.employee_id,
            attachment_hashes=orm_obj.attachment_hashes,
            created_at=orm_obj.created_at,
        )

    # ==================== RETENTION AND LEGAL HOLD OPERATIONS ====================

    async def soft_delete_document(
        self,
        document_id: int,
        deleted_by_id: Optional[int] = None,
        retention_days: int = 90,
    ) -> bool:
        """
        Soft delete a document by setting deleted_at timestamp.

        Will fail if the document is under legal hold.

        Args:
            document_id: ID of the document to delete
            deleted_by_id: ID of the employee performing the deletion
            retention_days: Days to retain the document before hard delete

        Returns:
            True if document was soft deleted, False if under legal hold or not found

        Raises:
            ValueError: If document is under legal hold
        """
        # First check if document exists and is under legal hold
        stmt = select(CertificateDocumentORM).where(
            CertificateDocumentORM.id == document_id
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            return False

        if doc.legal_hold:
            raise ValueError(
                f"Document {document_id} is under legal hold and cannot be deleted"
            )

        if doc.deleted_at is not None:
            return False  # Already deleted

        # Calculate retention expiration
        retention_expires = datetime.now(timezone.utc) + timedelta(days=retention_days)

        # Perform soft delete
        stmt = (
            update(CertificateDocumentORM)
            .where(
                and_(
                    CertificateDocumentORM.id == document_id,
                    CertificateDocumentORM.legal_hold == False,
                    CertificateDocumentORM.deleted_at == None,
                )
            )
            .values(
                deleted_at=datetime.now(timezone.utc),
                retention_expires_at=retention_expires,
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1

    async def set_document_legal_hold(
        self,
        document_id: int,
        hold: bool,
    ) -> bool:
        """
        Set or remove legal hold on a document.

        Args:
            document_id: ID of the document
            hold: True to set legal hold, False to remove

        Returns:
            True if the hold status was updated, False if document not found
        """
        stmt = (
            update(CertificateDocumentORM)
            .where(CertificateDocumentORM.id == document_id)
            .values(legal_hold=hold)
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1

    async def set_verified_record_legal_hold(
        self,
        record_id: int,
        hold: bool,
    ) -> bool:
        """
        Set or remove legal hold on a verified certificate record.

        Args:
            record_id: ID of the verified record
            hold: True to set legal hold, False to remove

        Returns:
            True if the hold status was updated, False if record not found
        """
        stmt = (
            update(VerifiedCertificateRecordORM)
            .where(VerifiedCertificateRecordORM.id == record_id)
            .values(legal_hold=hold)
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1

    async def list_documents_for_retention_purge(
        self,
        cutoff_date: datetime,
        limit: int = 100,
    ) -> list[CertificateDocument]:
        """
        List soft-deleted documents past their retention period for hard deletion.

        Only returns documents that:
        - Have been soft deleted (deleted_at is set)
        - Are past their retention expiration date
        - Are NOT under legal hold

        Args:
            cutoff_date: Purge documents with retention_expires_at before this date
            limit: Maximum number of documents to return

        Returns:
            List of documents eligible for hard deletion
        """
        stmt = (
            select(CertificateDocumentORM)
            .where(
                and_(
                    CertificateDocumentORM.deleted_at != None,
                    CertificateDocumentORM.retention_expires_at != None,
                    CertificateDocumentORM.retention_expires_at <= cutoff_date,
                    CertificateDocumentORM.legal_hold == False,
                )
            )
            .order_by(CertificateDocumentORM.retention_expires_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [self._document_orm_to_model(orm_obj) for orm_obj in result.scalars()]

    async def create_deletion_tombstone(
        self,
        entity_type: str,
        entity_id: int,
        deleted_by_id: Optional[int] = None,
        deletion_reason: Optional[str] = None,
        entity_metadata: Optional[dict] = None,
    ) -> DeletionTombstone:
        """
        Create a tombstone record for a hard-deleted entity.

        Args:
            entity_type: Type of entity (e.g., "document", "verified_record")
            entity_id: ID of the deleted entity
            deleted_by_id: ID of employee who performed deletion
            deletion_reason: Reason for deletion
            entity_metadata: Additional metadata to preserve about the entity

        Returns:
            Created tombstone record
        """
        orm_obj = DeletionTombstoneORM(
            entity_type=entity_type,
            entity_id=entity_id,
            deleted_by_id=deleted_by_id,
            deletion_reason=deletion_reason,
            entity_metadata=entity_metadata,
        )
        self.session.add(orm_obj)
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return self._tombstone_orm_to_model(orm_obj)

    async def hard_delete_document(
        self,
        document_id: int,
        deleted_by_id: Optional[int] = None,
        deletion_reason: Optional[str] = None,
    ) -> Optional[DeletionTombstone]:
        """
        Hard delete a document and create a tombstone record.

        Only works for documents that:
        - Have been soft deleted
        - Are NOT under legal hold

        Args:
            document_id: ID of the document to delete
            deleted_by_id: ID of employee performing deletion
            deletion_reason: Reason for deletion

        Returns:
            Tombstone record if deleted, None if document not found or not eligible
        """
        # Fetch document first to verify eligibility and capture metadata
        stmt = select(CertificateDocumentORM).where(
            and_(
                CertificateDocumentORM.id == document_id,
                CertificateDocumentORM.deleted_at != None,
                CertificateDocumentORM.legal_hold == False,
            )
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        # Capture metadata for tombstone
        metadata = {
            "employee_id": doc.employee_id,
            "storage_key": doc.storage_key,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "file_size_bytes": doc.file_size_bytes,
            "uploaded_by_id": doc.uploaded_by_id,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "deleted_at": doc.deleted_at.isoformat() if doc.deleted_at else None,
        }

        # Create tombstone
        tombstone = await self.create_deletion_tombstone(
            entity_type="document",
            entity_id=document_id,
            deleted_by_id=deleted_by_id,
            deletion_reason=deletion_reason,
            entity_metadata=metadata,
        )

        # Hard delete the document
        from sqlalchemy import delete

        stmt = delete(CertificateDocumentORM).where(
            CertificateDocumentORM.id == document_id
        )
        await self.session.execute(stmt)

        return tombstone

    def _tombstone_orm_to_model(
        self, orm_obj: DeletionTombstoneORM
    ) -> DeletionTombstone:
        """Convert ORM object to domain model."""
        return DeletionTombstone(
            id=orm_obj.id,
            entity_type=orm_obj.entity_type,
            entity_id=orm_obj.entity_id,
            deleted_at=orm_obj.deleted_at,
            deleted_by_id=orm_obj.deleted_by_id,
            deletion_reason=orm_obj.deletion_reason,
            entity_metadata=orm_obj.entity_metadata,
        )
