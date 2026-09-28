"""
Notifications API endpoints.

Provides access to user notifications for requirements and certificate events.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_repository, get_current_user
from ..shared.models import Employee
from ..shared.protocols import Repository
from .schemas import NotificationResponse, NotificationListResponse, MarkReadResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _notification_to_response(notification) -> NotificationResponse:
    """Convert notification model to response schema."""
    return NotificationResponse(
        id=notification.id,
        notification_type=notification.notification_type.value,
        recipient_employee_id=notification.recipient_employee_id,
        subject=notification.subject,
        body=notification.body,
        read=notification.read,
        read_at=notification.read_at,
        related_requirement_id=notification.related_requirement_id,
        related_certificate_id=notification.related_certificate_id,
        created_at=notification.created_at,
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(
        False, description="If true, only return unread notifications"
    ),
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of notifications to return"
    ),
    current_user: Employee = Depends(get_current_user),
    repository: Repository = Depends(get_repository),
):
    """
    List notifications for the current user.

    Returns notifications ordered by creation date (newest first).
    Also includes count of total unread notifications.

    Query parameters:
    - **unread_only**: If true, only return unread notifications
    - **limit**: Maximum results (default 50, max 200)
    """
    notifications = await repository.list_notifications_for_user(
        employee_id=current_user.id,
        unread_only=unread_only,
        limit=limit,
    )

    unread_count = await repository.count_unread_notifications(current_user.id)

    return NotificationListResponse(
        notifications=[_notification_to_response(n) for n in notifications],
        total_unread=unread_count,
    )


@router.get("/unread-count")
async def get_unread_count(
    current_user: Employee = Depends(get_current_user),
    repository: Repository = Depends(get_repository),
):
    """
    Get count of unread notifications for the current user.

    Useful for displaying notification badges in the UI.
    """
    count = await repository.count_unread_notifications(current_user.id)
    return {"unread_count": count}


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: int,
    current_user: Employee = Depends(get_current_user),
    repository: Repository = Depends(get_repository),
):
    """
    Get a specific notification by ID.

    Users can only access their own notifications.
    """
    notification = await repository.get_notification_by_id(notification_id)

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found",
        )

    # Users can only see their own notifications
    if notification.recipient_employee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access another user's notifications",
        )

    return _notification_to_response(notification)


@router.post("/{notification_id}/mark-read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: int,
    current_user: Employee = Depends(get_current_user),
    repository: Repository = Depends(get_repository),
):
    """
    Mark a specific notification as read.

    Users can only mark their own notifications as read.
    """
    notification = await repository.get_notification_by_id(notification_id)

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found",
        )

    # Users can only mark their own notifications as read
    if notification.recipient_employee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot mark another user's notifications as read",
        )

    # Mark as read
    if not notification.read:
        await repository.mark_notification_read(notification_id)

    # Fetch updated notification
    updated = await repository.get_notification_by_id(notification_id)
    return _notification_to_response(updated)


@router.post("/mark-all-read", response_model=MarkReadResponse)
async def mark_all_notifications_read(
    current_user: Employee = Depends(get_current_user),
    repository: Repository = Depends(get_repository),
):
    """
    Mark all notifications as read for the current user.

    Returns the number of notifications that were marked as read.
    """
    count = await repository.mark_all_notifications_read(current_user.id)

    return MarkReadResponse(
        marked_count=count,
        message=f"Marked {count} notification(s) as read",
    )
