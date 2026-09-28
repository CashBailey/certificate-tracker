"""
Audit Logs API endpoints.

Provides access to system audit trail for compliance and governance.
Admin-only access — Coordinators use operational views instead.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import get_repository, require_admin
from ..shared.models import AuditLog, Employee
from ..shared.protocols import Repository
from .schemas import AuditLogListResponse, AuditLogResponse

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


def _log_to_response(log: AuditLog, name_map: dict[int, str]) -> AuditLogResponse:
    """Convert domain AuditLog to response, enriching with actor name."""
    actor_name = name_map.get(log.employee_id) if log.employee_id else None
    return AuditLogResponse(
        id=log.id,
        actor_type=log.actor_type.value,
        employee_id=log.employee_id,
        actor_name=actor_name,
        action=log.action,
        target_type=log.target_type,
        target_id=log.target_id,
        details=log.details,
        initiated_by_id=log.initiated_by_id,
        occurred_at_utc=log.occurred_at_utc,
        recorded_at_utc=log.recorded_at_utc,
        actor_role=log.actor_role,
        correlation_id=log.correlation_id,
        source_service=log.source_service,
        outcome=log.outcome,
        ip_address=log.ip_address,
    )


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    target_type: Optional[str] = Query(
        None,
        description="Filter by target type (e.g., 'extraction', 'requirement', 'employee')",
    ),
    target_id: Optional[str] = Query(None, description="Filter by target ID"),
    action: Optional[str] = Query(
        None,
        description="Filter by action (e.g., 'extraction_approved', 'requirement_waived')",
    ),
    employee_id: Optional[int] = Query(None, description="Filter by actor employee ID"),
    created_after: Optional[datetime] = Query(
        None, description="Filter events on or after this timestamp (inclusive)"
    ),
    created_before: Optional[datetime] = Query(
        None, description="Filter events before this timestamp (exclusive)"
    ),
    source_service: Optional[str] = Query(
        None, description="Filter by source service (e.g., 'api', 'extraction-worker')"
    ),
    outcome: Optional[str] = Query(
        None, description="Filter by outcome (e.g., 'success', 'failure', 'denied')"
    ),
    actor_role: Optional[str] = Query(
        None, description="Filter by actor role at time of action"
    ),
    skip: int = Query(0, ge=0, description="Number of results to skip for pagination"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of results to return"
    ),
    current_user: Employee = Depends(require_admin),
    repository: Repository = Depends(get_repository),
):
    """
    List audit log entries with optional filters.

    Admin-only endpoint for governance and oversight.

    Filters:
    - **target_type**: Type of resource (extraction, requirement, employee, etc.)
    - **target_id**: Specific resource ID
    - **action**: Type of action performed
    - **employee_id**: Actor who performed the action
    - **created_after**: Events on or after this timestamp
    - **created_before**: Events before this timestamp
    - **source_service**: Service that produced the event
    - **outcome**: Result of the action (success/failure/denied)
    - **actor_role**: Role of the actor at time of action
    - **skip/limit**: Pagination (default 100, max 1000)
    """
    logs, total = await repository.list_audit_logs(
        target_type=target_type,
        target_id=target_id,
        action=action,
        employee_id=employee_id,
        created_after=created_after,
        created_before=created_before,
        source_service=source_service,
        outcome=outcome,
        actor_role=actor_role,
        skip=skip,
        limit=limit,
    )

    # Batch-load actor names to avoid N+1 queries
    actor_ids = {log.employee_id for log in logs if log.employee_id is not None}
    employees = await repository.list_employees()
    name_map = {
        e.id: f"{e.first_name} {e.last_name}".strip()
        for e in employees
        if e.id in actor_ids
    }

    return AuditLogListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[_log_to_response(log, name_map) for log in logs],
    )

