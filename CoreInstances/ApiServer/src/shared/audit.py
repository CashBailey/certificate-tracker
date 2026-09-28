"""
Audit logging helpers for the City of Laredo Certificate Management System.

Provides utilities for creating audit log entries with proper validation.
"""

from datetime import datetime
from typing import Any, Optional

from .models import AuditActorType, AuditLog, Employee
from .protocols import Repository

# Keys that must never appear in audit details (secret exclusion)
_SECRET_KEYS = frozenset({
    "password", "password_hash", "token", "secret",
    "api_key", "cookie", "authorization",
})


def _scrub_details(details: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Remove secret-bearing keys from audit details."""
    if details is None:
        return None
    return {k: v for k, v in details.items() if k.lower() not in _SECRET_KEYS}


async def audit(
    repository: Repository,
    action: str,
    target_type: str,
    target_id: str,
    actor: Optional[Employee] = None,
    details: Optional[dict[str, Any]] = None,
    initiated_by: Optional[Employee] = None,
    occurred_at_utc: Optional[datetime] = None,
    correlation_id: Optional[str] = None,
    source_service: Optional[str] = None,
    outcome: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """
    Create an audit log entry with proper validation.

    Args:
        repository: Repository instance
        action: Action being performed (e.g., "extraction_approved")
        target_type: Type of target (e.g., "extraction", "requirement")
        target_id: ID of the target
        actor: Employee performing the action (None for system actions)
        details: Optional additional details (secret keys are scrubbed)
        initiated_by: Employee who initiated the action (for system actions)
        occurred_at_utc: When the event occurred (defaults to now in DB)
        correlation_id: UUID grouping related audit entries
        source_service: Which service produced the entry
        outcome: Result of the action (success/failure/denied)
        ip_address: Client IP address

    Returns:
        Created AuditLog entry

    Raises:
        ValueError: If actor constraints are violated
    """
    # Determine actor type and role
    if actor is None:
        actor_type = AuditActorType.SYSTEM
        employee_id = None
        actor_role = None
    else:
        actor_type = AuditActorType.EMPLOYEE
        employee_id = actor.id
        actor_role = actor.role.value if hasattr(actor.role, 'value') else str(actor.role)

    # Validate actor constraints
    if actor_type == AuditActorType.SYSTEM and employee_id is not None:
        raise ValueError("System actions must not have employee_id")
    if actor_type == AuditActorType.EMPLOYEE and employee_id is None:
        raise ValueError("Employee actions must have employee_id")

    log_entry = AuditLog(
        id=0,  # Will be set by DB
        actor_type=actor_type,
        employee_id=employee_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        details=_scrub_details(details),
        initiated_by_id=initiated_by.id if initiated_by else None,
        occurred_at_utc=occurred_at_utc,
        actor_role=actor_role,
        correlation_id=correlation_id,
        source_service=source_service,
        outcome=outcome,
        ip_address=ip_address,
    )

    return await repository.create_audit_log(log_entry)


async def audit_employee_action(
    repository: Repository,
    actor: Employee,
    action: str,
    target_type: str,
    target_id: str,
    details: Optional[dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
    source_service: Optional[str] = "api",
    outcome: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """
    Create an audit log entry for an employee-initiated action.

    Args:
        repository: Repository instance
        actor: Employee performing the action
        action: Action being performed
        target_type: Type of target
        target_id: ID of the target
        details: Optional additional details
        correlation_id: UUID grouping related audit entries
        source_service: Which service produced the entry. Defaults to "api"
            because employee actions only flow through HTTP routes; pass an
            explicit override (or None) only when calling from a non-api context.
        outcome: Result of the action
        ip_address: Client IP address

    Returns:
        Created AuditLog entry
    """
    return await audit(
        repository=repository,
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor=actor,
        details=details,
        correlation_id=correlation_id,
        source_service=source_service,
        outcome=outcome,
        ip_address=ip_address,
    )
