"""
Requirements API endpoints.
"""

import csv
import io
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse

# Must match _UNBOUNDED_QUERY_CAP in repository.py. Keep in sync or move to a shared constants module.
_REQUIREMENTS_CAP = 10_000

# Maximum number of rows allowed in CSV import to prevent resource exhaustion
MAX_CSV_IMPORT_ROWS = 10000

from ..deps import get_repository, require_coordinator
from ..shared.models import Employee, RequirementAssignment, RequirementStatus, Role
from ..shared.protocols import Repository
from ..shared.audit import audit_employee_action
from ..authorizer import authorizer
from .schemas import (
    ImportRowResult,
    RequirementCreate,
    RequirementImportResponse,
    RequirementResponse,
    RequirementsPageResponse,
    RequirementWaive,
)

router = APIRouter(prefix="/requirements", tags=["requirements"])


async def _get_expiration_date(
    requirement: RequirementAssignment,
    repository: Repository,
) -> Optional[date]:
    """Compute certificate expiration date for a satisfied requirement."""
    if not requirement.satisfied_by_id:
        return None
    rec = await repository.get_verified_record_by_id(requirement.satisfied_by_id)
    if not rec:
        return None
    if rec.expiration_date:
        return rec.expiration_date
    if rec.issue_date:
        ct = await repository.get_certificate_type_by_id(requirement.certificate_type_id)
        if ct and ct.validity_period_days:
            return rec.issue_date + timedelta(days=ct.validity_period_days)
    return None


@router.post(
    "", response_model=RequirementResponse, status_code=status.HTTP_201_CREATED
)
async def create_requirement(
    request: RequirementCreate,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    Create a new requirement assignment.

    Only Coordinator can create requirements.
    """
    # Verify certificate type exists
    cert_type = await repository.get_certificate_type_by_id(request.certificate_type_id)
    if not cert_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate type {request.certificate_type_id} not found",
        )

    # Verify employee exists
    employee = await repository.get_employee_by_id(request.employee_id)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee {request.employee_id} not found",
        )

    # Prevent assigning compliance requirements to Admin-role accounts
    if employee.role == Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compliance requirements cannot be assigned to Admin accounts",
        )

    # Reject duplicate open assignments: one open requirement per
    # employee + certificate type. Satisfied/waived rows are history and
    # do not block a new compliance cycle.
    existing = await repository.list_requirements_for_employee(request.employee_id)
    for existing_req in existing:
        if existing_req.certificate_type_id == request.certificate_type_id and (
            existing_req.status
            not in (RequirementStatus.SATISFIED, RequirementStatus.WAIVED)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Employee already has an open {cert_type.name} requirement "
                    f"due {existing_req.due_date}"
                ),
            )

    # Create requirement
    requirement = RequirementAssignment(
        id=0,
        employee_id=request.employee_id,
        certificate_type_id=request.certificate_type_id,
        due_date=request.due_date,
        status=RequirementStatus.NOT_STARTED,
    )

    saved = await repository.create_requirement(requirement)

    # Audit log for requirement creation
    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="requirement_created",
        target_type="requirement",
        target_id=str(saved.id),
        details={
            "employee_id": request.employee_id,
            "certificate_type_id": request.certificate_type_id,
            "due_date": str(request.due_date),
        },
    )

    return RequirementResponse(
        id=saved.id,
        employee_id=saved.employee_id,
        certificate_type_id=saved.certificate_type_id,
        due_date=saved.due_date,
        status=saved.status.value,
        satisfied_by_id=saved.satisfied_by_id,
        waived_at=saved.waived_at,
        waived_by_id=saved.waived_by_id,
        waiver_reason=saved.waiver_reason,
        waiver_expiration=saved.waiver_expiration,
        created_at=saved.created_at,
        updated_at=saved.updated_at,
    )


@router.post("/import", response_model=RequirementImportResponse)
async def import_requirements(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    Bulk import requirement assignments from a CSV file.

    CSV format:
    ```
    employee_identifier,certificate_type,due_date
    E12345,First Aid/CPR,2026-06-30
    jane.doe@ci.laredo.tx.us,HIPAA Training,2026-04-15
    ```

    - employee_identifier: Employee number (e.g., "E12345") OR email address
    - certificate_type: Certificate type name (must match existing type, case-insensitive)
    - due_date: Due date in YYYY-MM-DD format

    Lookup order: employee_number first, then email.

    Only Coordinator can perform bulk imports.
    """
    # Validate file type
    if file.filename and not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file (.csv extension)",
        )

    # Parse CSV as a stream to avoid loading large files into memory.
    try:
        file.file.seek(0)
        text_stream = io.TextIOWrapper(file.file, encoding="utf-8", newline="")
        reader = csv.DictReader(text_stream)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded",
        )

    # Validate header columns
    required_columns = {"employee_identifier", "certificate_type", "due_date"}
    if not reader.fieldnames:
        text_stream.detach()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty or has no header row",
        )
    missing_columns = required_columns - set(reader.fieldnames)
    if missing_columns:
        text_stream.detach()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required columns: {', '.join(sorted(missing_columns))}",
        )

    # Cache for lookups to avoid repeated DB queries
    employee_cache: dict[str, Employee | None] = {}
    cert_type_cache: dict[str, int | None] = {}  # name (lower) -> id
    # Cache existing requirements per employee: employee_id -> set of (cert_type_id, due_date)
    requirements_cache: dict[int, set[tuple[int, date]]] = {}

    # Pre-load all certificate types for case-insensitive lookup
    all_cert_types = await repository.list_certificate_types()
    for ct in all_cert_types:
        cert_type_cache[ct.name.lower()] = ct.id

    results: list[ImportRowResult] = []
    created_count = 0
    skipped_count = 0
    error_count = 0
    today = date.today()

    total_rows = 0

    try:
        for row_num, row in enumerate(reader, start=1):
            total_rows = row_num

            # Validate row count early to prevent resource exhaustion
            if row_num > MAX_CSV_IMPORT_ROWS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"CSV file has more than {MAX_CSV_IMPORT_ROWS} rows; "
                        f"maximum allowed is {MAX_CSV_IMPORT_ROWS}"
                    ),
                )

            employee_identifier = row.get("employee_identifier", "").strip()
            certificate_type_name = row.get("certificate_type", "").strip()
            due_date_str = row.get("due_date", "").strip()

            # Validate employee_identifier is not empty
            if not employee_identifier:
                results.append(
                    ImportRowResult(
                        row=row_num,
                        status="error",
                        reason="Employee identifier is empty",
                    )
                )
                error_count += 1
                continue

            # Validate certificate_type is not empty
            if not certificate_type_name:
                results.append(
                    ImportRowResult(
                        row=row_num,
                        status="error",
                        reason="Certificate type is empty",
                    )
                )
                error_count += 1
                continue

            # Validate and parse due_date
            if not due_date_str:
                results.append(
                    ImportRowResult(
                        row=row_num,
                        status="error",
                        reason="Due date is empty",
                    )
                )
                error_count += 1
                continue

            try:
                due_date = date.fromisoformat(due_date_str)
            except ValueError:
                results.append(
                    ImportRowResult(
                        row=row_num,
                        status="error",
                        reason=f"Invalid date format '{due_date_str}', expected YYYY-MM-DD",
                    )
                )
                error_count += 1
                continue

            # Validate due date is not in the past
            if due_date < today:
                results.append(
                    ImportRowResult(
                        row=row_num,
                        status="error",
                        reason=f"Due date '{due_date_str}' is in the past",
                    )
                )
                error_count += 1
                continue

            # Look up employee (with caching)
            if employee_identifier not in employee_cache:
                # Try employee_number first
                employee = await repository.get_employee_by_number(employee_identifier)
                if not employee:
                    # Fall back to email
                    employee = await repository.get_employee_by_email(employee_identifier)
                employee_cache[employee_identifier] = employee

            employee = employee_cache[employee_identifier]
            if not employee:
                results.append(
                    ImportRowResult(
                        row=row_num,
                        status="error",
                        reason=f"Employee '{employee_identifier}' not found",
                    )
                )
                error_count += 1
                continue

            if employee.role == Role.ADMIN:
                results.append(
                    ImportRowResult(
                        row=row_num,
                        status="error",
                        reason="Compliance requirements cannot be assigned to Admin accounts",
                    )
                )
                error_count += 1
                continue

            # Look up certificate type (case-insensitive)
            cert_type_id = cert_type_cache.get(certificate_type_name.lower())
            if cert_type_id is None:
                results.append(
                    ImportRowResult(
                        row=row_num,
                        status="error",
                        reason=f"Certificate type '{certificate_type_name}' not found",
                    )
                )
                error_count += 1
                continue

            # Check for duplicate (same employee + cert type + due date)
            # Load and cache requirements for this employee if not already cached
            if employee.id not in requirements_cache:
                existing_requirements = await repository.list_requirements_for_employee(
                    employee.id
                )
                requirements_cache[employee.id] = {
                    (r.certificate_type_id, r.due_date) for r in existing_requirements
                }

            is_duplicate = (cert_type_id, due_date) in requirements_cache[employee.id]
            if is_duplicate:
                results.append(
                    ImportRowResult(
                        row=row_num,
                        status="skipped",
                        reason="Duplicate requirement (same employee, certificate type, and due date)",
                    )
                )
                skipped_count += 1
                continue

            # If dry_run, report what would be created but don't actually create
            if dry_run:
                # Update cache to detect duplicates within the same import file
                requirements_cache[employee.id].add((cert_type_id, due_date))
                results.append(
                    ImportRowResult(
                        row=row_num,
                        status="created",
                        reason="Would be created (dry run)",
                    )
                )
                created_count += 1
                continue

            # Create the requirement
            requirement = RequirementAssignment(
                id=0,
                employee_id=employee.id,
                certificate_type_id=cert_type_id,
                due_date=due_date,
                status=RequirementStatus.NOT_STARTED,
            )
            saved = await repository.create_requirement(requirement)

            # Update cache to detect duplicates within the same import file
            requirements_cache[employee.id].add((cert_type_id, due_date))

            results.append(
                ImportRowResult(
                    row=row_num,
                    status="created",
                    requirement_id=saved.id,
                )
            )
            created_count += 1
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded",
        )
    finally:
        # Detach wrapper so UploadFile can manage its own underlying file handle.
        text_stream.detach()

    # Audit log the bulk import operation
    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="requirements_bulk_import",
        target_type="requirement",
        target_id="bulk",
        details={
            "total_rows": total_rows,
            "created": created_count,
            "skipped": skipped_count,
            "errors": error_count,
            "filename": file.filename,
            "dry_run": dry_run,
        },
    )

    return RequirementImportResponse(
        success=error_count == 0,
        dry_run=dry_run,
        total_rows=total_rows,
        created=created_count,
        skipped=skipped_count,
        errors=error_count,
        results=results,
    )


@router.get("/paged", response_model=RequirementsPageResponse)
async def list_requirements_paged(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=500),
    status_filter: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    List requirements with server-side pagination, status filtering, and search.

    Returns a page of requirements along with the total count.
    Status filter values: Overdue, DueSoon, InProgress, Satisfied, Waived
    """
    offset = (page - 1) * page_size
    requirements, total = await repository.list_all_requirements_paginated(
        limit=page_size,
        offset=offset,
        status_filter=status_filter or None,
        search=search or None,
    )

    # Build employee name map
    employees = await repository.list_employees()
    emp_name_map = {e.id: f"{e.first_name} {e.last_name}".strip() for e in employees}

    # Build expiration date map for satisfied requirements
    expiration_map: dict[int, Optional[date]] = {}
    satisfied_ids = [r.satisfied_by_id for r in requirements if r.satisfied_by_id]
    if satisfied_ids:
        cert_types = await repository.list_certificate_types()
        ct_validity = {ct.id: ct.validity_period_days for ct in cert_types}
        for sid in satisfied_ids:
            rec = await repository.get_verified_record_by_id(sid)
            if rec:
                if rec.expiration_date:
                    expiration_map[sid] = rec.expiration_date
                elif rec.issue_date:
                    vdays = ct_validity.get(
                        next(
                            (r.certificate_type_id for r in requirements if r.satisfied_by_id == sid),
                            None,
                        )
                    )
                    if vdays:
                        expiration_map[sid] = rec.issue_date + timedelta(days=vdays)

    items = [
        RequirementResponse(
            id=r.id,
            employee_id=r.employee_id,
            employee_name=emp_name_map.get(r.employee_id),
            certificate_type_id=r.certificate_type_id,
            due_date=r.due_date,
            status=r.status.value,
            satisfied_by_id=r.satisfied_by_id,
            expiration_date=expiration_map.get(r.satisfied_by_id) if r.satisfied_by_id else None,
            waived_at=r.waived_at,
            waived_by_id=r.waived_by_id,
            waiver_reason=r.waiver_reason,
            waiver_expiration=r.waiver_expiration,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in requirements
    ]

    return RequirementsPageResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


@router.get("", response_model=list[RequirementResponse])
async def list_requirements(
    employee_id: int | None = None,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    List requirements.

    Only Coordinator can list requirements.
    Optionally filter by employee_id.
    """
    if employee_id:
        # Check permission to view other's requirements
        if employee_id != current_user.id:
            authorizer.require_can_view_reports(current_user)
        requirements = await repository.list_requirements_for_employee(employee_id)
    else:
        # Coordinator sees all requirements across all employees.
        # Pass limit=None so the dashboard compliance counters (computed from
        # this response on the frontend) don't silently undercount.
        requirements = await repository.list_all_requirements(limit=None)

    # Build employee name map for display
    employees = await repository.list_employees()
    emp_name_map = {
        e.id: f"{e.first_name} {e.last_name}".strip() for e in employees
    }

    # Build expiration date map for satisfied requirements
    expiration_map: dict[int, Optional[date]] = {}
    satisfied_ids = [r.satisfied_by_id for r in requirements if r.satisfied_by_id]
    if satisfied_ids:
        cert_types = await repository.list_certificate_types()
        ct_validity = {ct.id: ct.validity_period_days for ct in cert_types}
        for sid in satisfied_ids:
            rec = await repository.get_verified_record_by_id(sid)
            if rec:
                if rec.expiration_date:
                    expiration_map[sid] = rec.expiration_date
                elif rec.issue_date:
                    vdays = ct_validity.get(
                        next((r.certificate_type_id for r in requirements if r.satisfied_by_id == sid), None)
                    )
                    if vdays:
                        expiration_map[sid] = rec.issue_date + timedelta(days=vdays)

    items = [
        RequirementResponse(
            id=r.id,
            employee_id=r.employee_id,
            employee_name=emp_name_map.get(r.employee_id),
            certificate_type_id=r.certificate_type_id,
            due_date=r.due_date,
            status=r.status.value,
            satisfied_by_id=r.satisfied_by_id,
            expiration_date=expiration_map.get(r.satisfied_by_id) if r.satisfied_by_id else None,
            waived_at=r.waived_at,
            waived_by_id=r.waived_by_id,
            waiver_reason=r.waiver_reason,
            waiver_expiration=r.waiver_expiration,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in requirements
    ]
    if len(items) == _REQUIREMENTS_CAP:
        return JSONResponse(
            content=[item.model_dump(mode="json") for item in items],
            headers={"X-Total-Capped": "true"},
        )
    return items


@router.post("/{requirement_id}/waive", response_model=RequirementResponse)
async def waive_requirement(
    requirement_id: int,
    request: RequirementWaive,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    Waive a requirement.

    Only Coordinator can waive requirements.
    """
    requirement = await repository.get_requirement_by_id(requirement_id)

    if not requirement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requirement {requirement_id} not found",
        )

    if requirement.status == RequirementStatus.WAIVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requirement is already waived",
        )

    await repository.waive_requirement(
        requirement_id=requirement_id,
        waived_by_id=current_user.id,
        reason=request.reason,
        expiration=request.expiration,
    )

    # Audit log for requirement waiver
    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="requirement_waived",
        target_type="requirement",
        target_id=str(requirement_id),
        details={
            "reason": request.reason,
            "expiration": str(request.expiration) if request.expiration else None,
        },
    )

    # Fetch updated requirement
    updated = await repository.get_requirement_by_id(requirement_id)
    exp_date = await _get_expiration_date(updated, repository)

    return RequirementResponse(
        id=updated.id,
        employee_id=updated.employee_id,
        certificate_type_id=updated.certificate_type_id,
        due_date=updated.due_date,
        status=updated.status.value,
        satisfied_by_id=updated.satisfied_by_id,
        expiration_date=exp_date,
        waived_at=updated.waived_at,
        waived_by_id=updated.waived_by_id,
        waiver_reason=updated.waiver_reason,
        waiver_expiration=updated.waiver_expiration,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.post("/{requirement_id}/unwaive", response_model=RequirementResponse)
async def unwaive_requirement(
    requirement_id: int,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    Restore a waived requirement to active status.

    Only Coordinator can unwaive requirements.
    Clears all waiver fields and sets status based on current state:
    - If requirement was previously satisfied, status becomes Satisfied
    - Otherwise, status becomes NotStarted
    """
    requirement = await repository.get_requirement_by_id(requirement_id)

    if not requirement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requirement {requirement_id} not found",
        )

    if requirement.status != RequirementStatus.WAIVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requirement is not waived",
        )

    await repository.unwaive_requirement(requirement_id=requirement_id)

    # Audit log for requirement unwaiver
    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="requirement_unwaived",
        target_type="requirement",
        target_id=str(requirement_id),
    )

    # Fetch updated requirement
    updated = await repository.get_requirement_by_id(requirement_id)
    exp_date = await _get_expiration_date(updated, repository)

    return RequirementResponse(
        id=updated.id,
        employee_id=updated.employee_id,
        certificate_type_id=updated.certificate_type_id,
        due_date=updated.due_date,
        status=updated.status.value,
        satisfied_by_id=updated.satisfied_by_id,
        expiration_date=exp_date,
        waived_at=updated.waived_at,
        waived_by_id=updated.waived_by_id,
        waiver_reason=updated.waiver_reason,
        waiver_expiration=updated.waiver_expiration,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )
