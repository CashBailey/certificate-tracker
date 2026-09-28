"""
Unit tests for notification API routes.

Tests the endpoints in src/routes/notifications.py using FastAPI's TestClient
with dependency overrides for repository and authentication.
"""

import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.deps import get_repository, get_current_user
from src.routes.notifications import router
from src.shared.models import Employee, NotificationEvent, NotificationType, Role


# ==================== Helpers ====================


def _make_employee(employee_id: int = 7) -> Employee:
    """Create a test employee."""
    return Employee(
        id=employee_id,
        employee_number="E00001",
        first_name="Test",
        last_name="User",
        email="test.user@ci.laredo.tx.us",
        role=Role.EMPLOYEE,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_notification(
    notification_id: int = 42,
    recipient_id: int = 7,
    read: bool = False,
    read_at=None,
    notification_type: NotificationType = NotificationType.REQUIREMENT_DUE_SOON,
) -> NotificationEvent:
    """Create a test notification."""
    return NotificationEvent(
        id=notification_id,
        notification_type=notification_type,
        recipient_employee_id=recipient_id,
        subject="Upcoming Requirement: CPR-BLS Due 2026-04-15 (30 days)",
        body="You have a CPR-BLS requirement due on 2026-04-15.",
        dedupe_key=f"RequirementDueSoon:{notification_id}:2026-04-15",
        related_requirement_id=15,
        related_certificate_id=None,
        effective_date=date(2026, 4, 15),
        delivered=True,
        delivered_at=datetime(2026, 3, 16, 6, 0, 0, tzinfo=timezone.utc),
        read=read,
        read_at=read_at,
        created_at=datetime(2026, 3, 16, 6, 0, 0, tzinfo=timezone.utc),
    )


def _create_app(mock_repo: AsyncMock, user: Employee) -> FastAPI:
    """Create a FastAPI app with overridden dependencies."""
    app = FastAPI()
    app.include_router(router, prefix="/api")

    app.dependency_overrides[get_repository] = lambda: mock_repo
    app.dependency_overrides[get_current_user] = lambda: user

    return app


def _create_unauthenticated_app(mock_repo: AsyncMock) -> FastAPI:
    """Create a FastAPI app with no authentication (raises 401)."""
    from fastapi import HTTPException, status

    app = FastAPI()
    app.include_router(router, prefix="/api")

    app.dependency_overrides[get_repository] = lambda: mock_repo

    def no_user():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    app.dependency_overrides[get_current_user] = no_user

    return app


# ==================== GET /api/notifications ====================


class TestListNotifications:
    """Tests for GET /api/notifications."""

    def test_returns_notifications_with_read_field(self):
        """Response should include `read` field, not `delivered`."""
        user = _make_employee()
        notif = _make_notification(read=False)
        mock_repo = AsyncMock()
        mock_repo.list_notifications_for_user = AsyncMock(return_value=[notif])
        mock_repo.count_unread_notifications = AsyncMock(return_value=1)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.get("/api/notifications")
        assert resp.status_code == 200

        data = resp.json()
        assert "notifications" in data
        assert len(data["notifications"]) == 1

        n = data["notifications"][0]
        assert "read" in n
        assert n["read"] is False
        assert "delivered" not in n  # delivered must NOT appear in response

    def test_returns_total_unread_count(self):
        """Response should include total_unread."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.list_notifications_for_user = AsyncMock(return_value=[])
        mock_repo.count_unread_notifications = AsyncMock(return_value=5)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.get("/api/notifications")
        assert resp.status_code == 200
        assert resp.json()["total_unread"] == 5

    def test_unread_only_filter(self):
        """unread_only=true should pass to repository."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.list_notifications_for_user = AsyncMock(return_value=[])
        mock_repo.count_unread_notifications = AsyncMock(return_value=0)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        client.get("/api/notifications?unread_only=true")

        mock_repo.list_notifications_for_user.assert_called_once_with(
            employee_id=user.id,
            unread_only=True,
            limit=50,
        )

    def test_limit_parameter(self):
        """limit parameter should be passed to repository."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.list_notifications_for_user = AsyncMock(return_value=[])
        mock_repo.count_unread_notifications = AsyncMock(return_value=0)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        client.get("/api/notifications?limit=10")

        mock_repo.list_notifications_for_user.assert_called_once_with(
            employee_id=user.id,
            unread_only=False,
            limit=10,
        )

    def test_limit_validation_max(self):
        """limit > 200 should be rejected."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.list_notifications_for_user = AsyncMock(return_value=[])
        mock_repo.count_unread_notifications = AsyncMock(return_value=0)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.get("/api/notifications?limit=500")
        assert resp.status_code == 422

    def test_queries_current_user_only(self):
        """Should only query notifications for the authenticated user."""
        user = _make_employee(employee_id=7)
        mock_repo = AsyncMock()
        mock_repo.list_notifications_for_user = AsyncMock(return_value=[])
        mock_repo.count_unread_notifications = AsyncMock(return_value=0)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        client.get("/api/notifications")

        mock_repo.list_notifications_for_user.assert_called_once()
        call_args = mock_repo.list_notifications_for_user.call_args
        assert call_args.kwargs["employee_id"] == 7

    def test_requires_authentication(self):
        """Should return 401 without authentication."""
        mock_repo = AsyncMock()
        app = _create_unauthenticated_app(mock_repo)
        client = TestClient(app)

        resp = client.get("/api/notifications")
        assert resp.status_code == 401


# ==================== GET /api/notifications/unread-count ====================


class TestUnreadCount:
    """Tests for GET /api/notifications/unread-count."""

    def test_returns_unread_count(self):
        """Should return the unread count."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.count_unread_notifications = AsyncMock(return_value=5)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.get("/api/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json() == {"unread_count": 5}

    def test_returns_zero_when_no_unread(self):
        """Should return 0 when all notifications are read."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.count_unread_notifications = AsyncMock(return_value=0)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.get("/api/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 0

    def test_queries_current_user(self):
        """Should count only for the authenticated user."""
        user = _make_employee(employee_id=42)
        mock_repo = AsyncMock()
        mock_repo.count_unread_notifications = AsyncMock(return_value=0)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        client.get("/api/notifications/unread-count")
        mock_repo.count_unread_notifications.assert_called_once_with(42)

    def test_requires_authentication(self):
        """Should return 401 without authentication."""
        mock_repo = AsyncMock()
        app = _create_unauthenticated_app(mock_repo)
        client = TestClient(app)

        resp = client.get("/api/notifications/unread-count")
        assert resp.status_code == 401


# ==================== GET /api/notifications/{id} ====================


class TestGetNotification:
    """Tests for GET /api/notifications/{id}."""

    def test_returns_notification(self):
        """Should return a single notification."""
        user = _make_employee(employee_id=7)
        notif = _make_notification(notification_id=42, recipient_id=7, read=False)
        mock_repo = AsyncMock()
        mock_repo.get_notification_by_id = AsyncMock(return_value=notif)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.get("/api/notifications/42")
        assert resp.status_code == 200

        data = resp.json()
        assert data["id"] == 42
        assert data["read"] is False
        assert "delivered" not in data

    def test_404_for_missing(self):
        """Should return 404 for non-existent notification."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.get_notification_by_id = AsyncMock(return_value=None)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.get("/api/notifications/999")
        assert resp.status_code == 404

    def test_403_for_other_users_notification(self):
        """Should return 403 when accessing another user's notification."""
        user = _make_employee(employee_id=7)
        notif = _make_notification(notification_id=42, recipient_id=99)
        mock_repo = AsyncMock()
        mock_repo.get_notification_by_id = AsyncMock(return_value=notif)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.get("/api/notifications/42")
        assert resp.status_code == 403

    def test_requires_authentication(self):
        """Should return 401 without authentication."""
        mock_repo = AsyncMock()
        app = _create_unauthenticated_app(mock_repo)
        client = TestClient(app)

        resp = client.get("/api/notifications/42")
        assert resp.status_code == 401


# ==================== POST /api/notifications/{id}/mark-read ====================


class TestMarkNotificationRead:
    """Tests for POST /api/notifications/{id}/mark-read."""

    def test_marks_as_read(self):
        """Should call mark_notification_read (not mark_notification_delivered)."""
        user = _make_employee(employee_id=7)
        notif_before = _make_notification(notification_id=42, recipient_id=7, read=False)
        now = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
        notif_after = _make_notification(
            notification_id=42, recipient_id=7, read=True, read_at=now
        )
        mock_repo = AsyncMock()
        mock_repo.get_notification_by_id = AsyncMock(
            side_effect=[notif_before, notif_after]
        )
        mock_repo.mark_notification_read = AsyncMock()

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.post("/api/notifications/42/mark-read")
        assert resp.status_code == 200

        # Must call mark_notification_read, NOT mark_notification_delivered
        mock_repo.mark_notification_read.assert_called_once_with(42)
        assert not hasattr(mock_repo, "mark_notification_delivered") or \
            not mock_repo.mark_notification_delivered.called

        data = resp.json()
        assert data["read"] is True
        assert data["read_at"] is not None

    def test_already_read_skips_update(self):
        """Should not call mark_notification_read if already read."""
        user = _make_employee(employee_id=7)
        now = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
        notif = _make_notification(
            notification_id=42, recipient_id=7, read=True, read_at=now
        )
        mock_repo = AsyncMock()
        mock_repo.get_notification_by_id = AsyncMock(return_value=notif)
        mock_repo.mark_notification_read = AsyncMock()

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.post("/api/notifications/42/mark-read")
        assert resp.status_code == 200

        # Should NOT call mark_notification_read since already read
        mock_repo.mark_notification_read.assert_not_called()

    def test_404_for_missing(self):
        """Should return 404 for non-existent notification."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.get_notification_by_id = AsyncMock(return_value=None)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.post("/api/notifications/999/mark-read")
        assert resp.status_code == 404

    def test_403_for_other_users_notification(self):
        """Should return 403 when marking another user's notification."""
        user = _make_employee(employee_id=7)
        notif = _make_notification(notification_id=42, recipient_id=99)
        mock_repo = AsyncMock()
        mock_repo.get_notification_by_id = AsyncMock(return_value=notif)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.post("/api/notifications/42/mark-read")
        assert resp.status_code == 403

    def test_requires_authentication(self):
        """Should return 401 without authentication."""
        mock_repo = AsyncMock()
        app = _create_unauthenticated_app(mock_repo)
        client = TestClient(app)

        resp = client.post("/api/notifications/42/mark-read")
        assert resp.status_code == 401


# ==================== POST /api/notifications/mark-all-read ====================


class TestMarkAllRead:
    """Tests for POST /api/notifications/mark-all-read."""

    def test_marks_all_read(self):
        """Should call mark_all_notifications_read and return count."""
        user = _make_employee(employee_id=7)
        mock_repo = AsyncMock()
        mock_repo.mark_all_notifications_read = AsyncMock(return_value=3)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.post("/api/notifications/mark-all-read")
        assert resp.status_code == 200

        data = resp.json()
        assert data["marked_count"] == 3
        assert data["message"] == "Marked 3 notification(s) as read"

        mock_repo.mark_all_notifications_read.assert_called_once_with(7)

    def test_marks_zero_when_none_unread(self):
        """Should return 0 when no unread notifications."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.mark_all_notifications_read = AsyncMock(return_value=0)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.post("/api/notifications/mark-all-read")
        assert resp.status_code == 200
        assert resp.json()["marked_count"] == 0

    def test_requires_authentication(self):
        """Should return 401 without authentication."""
        mock_repo = AsyncMock()
        app = _create_unauthenticated_app(mock_repo)
        client = TestClient(app)

        resp = client.post("/api/notifications/mark-all-read")
        assert resp.status_code == 401


# ==================== Response schema validation ====================


class TestResponseSchema:
    """Tests that responses match the interface contract schema."""

    def test_notification_response_has_correct_fields(self):
        """Notification response should have exactly the contract fields."""
        user = _make_employee(employee_id=7)
        notif = _make_notification(notification_id=42, recipient_id=7)
        mock_repo = AsyncMock()
        mock_repo.get_notification_by_id = AsyncMock(return_value=notif)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.get("/api/notifications/42")
        data = resp.json()

        expected_fields = {
            "id", "notification_type", "recipient_employee_id",
            "subject", "body", "read", "read_at",
            "related_requirement_id", "related_certificate_id",
            "created_at",
        }
        assert set(data.keys()) == expected_fields

    def test_notification_list_response_shape(self):
        """List response should have notifications array and total_unread."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.list_notifications_for_user = AsyncMock(return_value=[])
        mock_repo.count_unread_notifications = AsyncMock(return_value=0)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.get("/api/notifications")
        data = resp.json()

        assert set(data.keys()) == {"notifications", "total_unread"}
        assert isinstance(data["notifications"], list)
        assert isinstance(data["total_unread"], int)

    def test_mark_read_response_shape(self):
        """Mark-all-read response should have marked_count and message."""
        user = _make_employee()
        mock_repo = AsyncMock()
        mock_repo.mark_all_notifications_read = AsyncMock(return_value=0)

        app = _create_app(mock_repo, user)
        client = TestClient(app)

        resp = client.post("/api/notifications/mark-all-read")
        data = resp.json()

        assert set(data.keys()) == {"marked_count", "message"}
