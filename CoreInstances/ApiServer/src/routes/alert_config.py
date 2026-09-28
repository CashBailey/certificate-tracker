"""
Alert Configuration API endpoints.

Provides GET/PUT access to the singleton alert configuration that controls
notification reminder intervals, daily-overdue toggle, and global send time.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import get_repository, require_coordinator
from ..shared.audit import audit_employee_action
from ..shared.models import AlertConfiguration, Employee
from ..shared.protocols import Repository
from .schemas import AlertConfigResponse, AlertConfigUpdate

router = APIRouter(prefix="/alert-config", tags=["alert-config"])


def _validate_day_offsets(days: list[int], field_name: str) -> None:
    """Validate a list of reminder day offsets."""
    for d in days:
        if d < 1 or d > 365:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name}: each value must be between 1 and 365, got {d}",
            )
    if len(days) != len(set(days)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name}: duplicate values not allowed",
        )
    if days != sorted(days, reverse=True):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name}: values must be sorted in descending order",
        )


@router.get("", response_model=AlertConfigResponse)
async def get_alert_config(
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    Get the current alert configuration.

    Returns the singleton alert configuration that controls notification
    reminder intervals, daily-overdue behavior, and global send time.
    Coordinator-only access.
    """
    config = await repository.get_alert_configuration()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert configuration not found. Run migrations to seed defaults.",
        )

    return AlertConfigResponse(
        requirement_reminder_days=config.requirement_reminder_days,
        certificate_reminder_days=config.certificate_reminder_days,
        daily_overdue_enabled=config.daily_overdue_enabled,
        global_send_hour=config.global_send_hour,
        global_send_minute=config.global_send_minute,
        updated_at=config.updated_at,
        updated_by_id=config.updated_by_id,
    )


@router.put("", response_model=AlertConfigResponse)
async def update_alert_config(
    body: AlertConfigUpdate,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    Update the alert configuration.

    Full replacement of all configuration fields. Coordinator-only access.
    Emits an audit event on successful update.
    """
    # Validate day offsets
    _validate_day_offsets(body.requirement_reminder_days, "requirement_reminder_days")
    _validate_day_offsets(body.certificate_reminder_days, "certificate_reminder_days")

    # Get current config for audit diff
    current = await repository.get_alert_configuration()
    if not current:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert configuration not found. Run migrations to seed defaults.",
        )

    # Build updated config
    updated = AlertConfiguration(
        id=1,
        requirement_reminder_days=body.requirement_reminder_days,
        certificate_reminder_days=body.certificate_reminder_days,
        daily_overdue_enabled=body.daily_overdue_enabled,
        global_send_hour=body.global_send_hour,
        global_send_minute=body.global_send_minute,
        updated_by_id=current_user.id,
    )

    result = await repository.update_alert_configuration(updated)

    # Emit audit event
    changes = {}
    if current.requirement_reminder_days != body.requirement_reminder_days:
        changes["requirement_reminder_days"] = {
            "old": current.requirement_reminder_days,
            "new": body.requirement_reminder_days,
        }
    if current.certificate_reminder_days != body.certificate_reminder_days:
        changes["certificate_reminder_days"] = {
            "old": current.certificate_reminder_days,
            "new": body.certificate_reminder_days,
        }
    if current.daily_overdue_enabled != body.daily_overdue_enabled:
        changes["daily_overdue_enabled"] = {
            "old": current.daily_overdue_enabled,
            "new": body.daily_overdue_enabled,
        }
    if current.global_send_hour != body.global_send_hour:
        changes["global_send_hour"] = {
            "old": current.global_send_hour,
            "new": body.global_send_hour,
        }
    if current.global_send_minute != body.global_send_minute:
        changes["global_send_minute"] = {
            "old": current.global_send_minute,
            "new": body.global_send_minute,
        }

    if changes:
        await audit_employee_action(
            repository=repository,
            actor=current_user,
            action="alert_config.updated",
            target_type="AlertConfiguration",
            target_id="1",
            details={"changes": changes},
        )

    return AlertConfigResponse(
        requirement_reminder_days=result.requirement_reminder_days,
        certificate_reminder_days=result.certificate_reminder_days,
        daily_overdue_enabled=result.daily_overdue_enabled,
        global_send_hour=result.global_send_hour,
        global_send_minute=result.global_send_minute,
        updated_at=result.updated_at,
        updated_by_id=result.updated_by_id,
    )
