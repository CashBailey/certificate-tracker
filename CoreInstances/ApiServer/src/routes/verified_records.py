"""
Verified Records API endpoints.

Provides access to verified certificate records after extraction approval.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from ..deps import get_repository, require_coordinator
from ..shared.models import Employee
from ..shared.protocols import Repository
from .schemas import VerifiedRecordResponse

router = APIRouter(prefix="/verified-records", tags=["verified-records"])


@router.get("", response_model=list[VerifiedRecordResponse])
async def list_verified_records(
    employee_id: Optional[int] = None,
    certificate_type: Optional[str] = None,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    List verified certificate records with optional filters.

    - Coordinator can see all records
    - Employees can only see their own records

    Query parameters:
        employee_id: Filter by employee ID
        certificate_type: Filter by certificate type name
    """
    # Determine which records to fetch (RBAC disabled — show all)
    if employee_id is not None:
        target_employee_id = employee_id
    else:
        target_employee_id = None

    # Fetch records
    records = await repository.list_verified_records(
        employee_id=target_employee_id,
        certificate_type=certificate_type,
    )

    return [
        VerifiedRecordResponse(
            id=r.id,
            extraction_id=r.extraction_id,
            document_id=r.document_id,
            employee_id=r.employee_id,
            certificate_holder_name=r.certificate_holder_name,
            certificate_type=r.certificate_type,
            certificate_number=r.certificate_number,
            issuing_authority=r.issuing_authority,
            issue_date=r.issue_date,
            expiration_date=r.expiration_date,
            training_hours=r.training_hours,
            license_class=r.license_class,
            endorsements=r.endorsements,
            created_at=r.created_at,
        )
        for r in records
    ]
