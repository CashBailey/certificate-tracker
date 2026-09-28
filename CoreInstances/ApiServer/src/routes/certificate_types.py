"""
Certificate Types API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import get_current_user, get_repository, require_coordinator
from ..shared.models import CertificateType, Employee
from ..shared.protocols import Repository
from ..shared.audit import audit_employee_action
from .schemas import (
    CertificateTypeCreate,
    CertificateTypeResponse,
    CertificateTypeUpdate,
)

router = APIRouter(prefix="/certificate-types", tags=["certificate-types"])


def _to_response(ct: CertificateType) -> CertificateTypeResponse:
    """Convert domain model to response schema."""
    return CertificateTypeResponse(
        id=ct.id,
        name=ct.name,
        description=ct.description,
        validity_period_days=ct.validity_period_days,
        created_at=ct.created_at,
        updated_at=ct.updated_at,
    )


@router.get("", response_model=list[CertificateTypeResponse])
async def list_certificate_types(
    current_user: Employee = Depends(get_current_user),
    repository: Repository = Depends(get_repository),
):
    """List all certificate types."""
    cert_types = await repository.list_certificate_types()
    return [_to_response(ct) for ct in cert_types]


@router.get("/{cert_type_id}", response_model=CertificateTypeResponse)
async def get_certificate_type(
    cert_type_id: int,
    current_user: Employee = Depends(get_current_user),
    repository: Repository = Depends(get_repository),
):
    """Get a certificate type by ID."""
    ct = await repository.get_certificate_type_by_id(cert_type_id)
    if ct is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate type not found",
        )
    return _to_response(ct)


@router.post(
    "",
    response_model=CertificateTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_certificate_type(
    data: CertificateTypeCreate,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """Create a new certificate type. Coordinator only."""
    # Check name uniqueness
    existing = await repository.get_certificate_type_by_name(data.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Certificate type name already exists",
        )

    cert_type = CertificateType(
        id=0,  # Set by DB
        name=data.name,
        description=data.description,
        validity_period_days=data.validity_period_days,
    )
    created = await repository.create_certificate_type(cert_type)

    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="certificate_type_created",
        target_type="certificate_type",
        target_id=str(created.id),
        details={
            "name": created.name,
            "validity_period_days": created.validity_period_days,
        },
    )

    return _to_response(created)


@router.patch("/{cert_type_id}", response_model=CertificateTypeResponse)
async def update_certificate_type(
    cert_type_id: int,
    data: CertificateTypeUpdate,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """Update a certificate type. Coordinator only."""
    # Verify it exists
    existing = await repository.get_certificate_type_by_id(cert_type_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate type not found",
        )

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        return _to_response(existing)

    # Check name uniqueness if renaming
    if "name" in updates and updates["name"] != existing.name:
        collision = await repository.get_certificate_type_by_name(updates["name"])
        if collision is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Certificate type name already exists",
            )

    # Capture old values for audit
    old_values = {field: getattr(existing, field) for field in updates}

    updated = await repository.update_certificate_type(cert_type_id, updates)

    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="certificate_type_updated",
        target_type="certificate_type",
        target_id=str(cert_type_id),
        details={
            "updated_fields": list(updates.keys()),
            "old_values": {k: str(v) if v is not None else None for k, v in old_values.items()},
            "new_values": {k: str(v) if v is not None else None for k, v in updates.items()},
        },
    )

    return _to_response(updated)


@router.delete("/{cert_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certificate_type(
    cert_type_id: int,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """Delete a certificate type. Coordinator only."""
    # Verify it exists
    existing = await repository.get_certificate_type_by_id(cert_type_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate type not found",
        )

    # Check for active requirement assignments
    req_count = await repository.count_requirements_for_cert_type(cert_type_id)
    if req_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete certificate type with existing requirement assignments",
        )

    # Capture name before deletion for audit
    name = existing.name
    await repository.delete_certificate_type(cert_type_id)

    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="certificate_type_deleted",
        target_type="certificate_type",
        target_id=str(cert_type_id),
        details={"name": name},
    )

    return None
