"""
Unit tests for Audit Logs API routes.

Tests cover:
- RBAC: Admin-only access (require_admin); Coordinator and Employee denied
- GET /audit-logs: list with filters, pagination, empty results
- Response schema: dual timestamps, correlation_id, source_service, outcome
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.deps import get_repository, get_current_user
from src.routes.audit_logs import router
from src.shared.models import AuditActorType, AuditLog, Employee, Role


# ==================== Helpers ====================


def _make_user(role: Role, employee_id: int = 1) -> Employee:
    return Employee(
        id=employee_id,
        employee_number=f"E{employee_id:05d}",
        first_name="Test",
        last_name="User",
        email=f"test{employee_id}@ci.laredo.tx.us",
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _coordinator() -> Employee:
    return _make_user(Role.COORDINATOR, employee_id=10)


def _admin() -> Employee:
    return _make_user(Role.ADMIN, employee_id=20)


def _employee() -> Employee:
    return _make_user(Role.EMPLOYEE, employee_id=30)


def _make_audit_log(
    log_id: int = 1,
    action: str = "extraction_approved",
    target_type: str = "extraction",
    target_id: str = "42",
    employee_id: int = 10,
    **overrides,
) -> AuditLog:
    """Create a test AuditLog with Iteration 2 dual-timestamp fields."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=log_id,
        actor_type=AuditActorType.EMPLOYEE,
        employee_id=employee_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details={"corrections": {}},
        initiated_by_id=None,
        occurred_at_utc=now,
        recorded_at_utc=now,
        actor_role="Coordinator",
        correlation_id="corr-abc-123",
        source_service="api-server",
        outcome="success",
        ip_address="10.0.0.1",
    )
    defaults.update(overrides)
    return AuditLog(**defaults)


def _mock_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.list_audit_logs = AsyncMock(return_value=([], 0))
    repo.list_employees = AsyncMock(return_value=[])
    return repo


def _create_app(user: Employee, repo: AsyncMock = None) -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    if repo is None:
        repo = _mock_repo()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: user
    return app, TestClient(app)


# ==================== RBAC Tests ====================


class TestAuditLogRBAC:
    """Admin-only access; Coordinator and Employee denied."""

    def test_coordinator_denied_list(self):
        _, client = _create_app(_coordinator())
        resp = client.get("/api/audit-logs")
        assert resp.status_code == 403

    def test_admin_allowed_list(self):
        _, client = _create_app(_admin())
        resp = client.get("/api/audit-logs")
        assert resp.status_code == 200

    def test_employee_denied_list(self):
        _, client = _create_app(_employee())
        resp = client.get("/api/audit-logs")
        assert resp.status_code == 403

# ==================== GET /audit-logs ====================


class TestListAuditLogs:
    """GET /api/audit-logs with filters and pagination."""

    def test_empty_list(self):
        _, client = _create_app(_admin())
        resp = client.get("/api/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_returns_entries(self):
        repo = _mock_repo()
        logs = [_make_audit_log(log_id=1), _make_audit_log(log_id=2, action="requirement_waived")]
        repo.list_audit_logs.return_value = (logs, 2)
        _, client = _create_app(_admin(), repo)

        resp = client.get("/api/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["id"] == 1
        assert data["items"][1]["id"] == 2
        assert data["total"] == 2

    def test_filter_by_target_type(self):
        repo = _mock_repo()
        _, client = _create_app(_admin(), repo)

        client.get("/api/audit-logs?target_type=extraction")
        repo.list_audit_logs.assert_called_once_with(
            target_type="extraction",
            target_id=None,
            action=None,
            employee_id=None,
            created_after=None,
            created_before=None,
            source_service=None,
            outcome=None,
            actor_role=None,
            skip=0,
            limit=100,
        )

    def test_filter_by_target_id(self):
        repo = _mock_repo()
        _, client = _create_app(_admin(), repo)

        client.get("/api/audit-logs?target_id=42")
        repo.list_audit_logs.assert_called_once_with(
            target_type=None,
            target_id="42",
            action=None,
            employee_id=None,
            created_after=None,
            created_before=None,
            source_service=None,
            outcome=None,
            actor_role=None,
            skip=0,
            limit=100,
        )

    def test_filter_by_action(self):
        repo = _mock_repo()
        _, client = _create_app(_admin(), repo)

        client.get("/api/audit-logs?action=extraction_approved")
        repo.list_audit_logs.assert_called_once_with(
            target_type=None,
            target_id=None,
            action="extraction_approved",
            employee_id=None,
            created_after=None,
            created_before=None,
            source_service=None,
            outcome=None,
            actor_role=None,
            skip=0,
            limit=100,
        )

    def test_filter_by_employee_id(self):
        repo = _mock_repo()
        _, client = _create_app(_admin(), repo)

        client.get("/api/audit-logs?employee_id=10")
        repo.list_audit_logs.assert_called_once_with(
            target_type=None,
            target_id=None,
            action=None,
            employee_id=10,
            created_after=None,
            created_before=None,
            source_service=None,
            outcome=None,
            actor_role=None,
            skip=0,
            limit=100,
        )

    def test_all_filters_combined(self):
        repo = _mock_repo()
        _, client = _create_app(_admin(), repo)

        client.get(
            "/api/audit-logs?target_type=requirement&target_id=5&action=requirement_waived&employee_id=10"
        )
        repo.list_audit_logs.assert_called_once_with(
            target_type="requirement",
            target_id="5",
            action="requirement_waived",
            employee_id=10,
            created_after=None,
            created_before=None,
            source_service=None,
            outcome=None,
            actor_role=None,
            skip=0,
            limit=100,
        )

    def test_pagination_skip_and_limit(self):
        repo = _mock_repo()
        _, client = _create_app(_admin(), repo)

        client.get("/api/audit-logs?skip=20&limit=50")
        repo.list_audit_logs.assert_called_once_with(
            target_type=None,
            target_id=None,
            action=None,
            employee_id=None,
            created_after=None,
            created_before=None,
            source_service=None,
            outcome=None,
            actor_role=None,
            skip=20,
            limit=50,
        )

    def test_pagination_default_values(self):
        """Default skip=0, limit=100."""
        repo = _mock_repo()
        _, client = _create_app(_admin(), repo)

        client.get("/api/audit-logs")
        repo.list_audit_logs.assert_called_once_with(
            target_type=None,
            target_id=None,
            action=None,
            employee_id=None,
            created_after=None,
            created_before=None,
            source_service=None,
            outcome=None,
            actor_role=None,
            skip=0,
            limit=100,
        )

    def test_limit_validation_max_1000(self):
        """FastAPI validates limit <= 1000."""
        _, client = _create_app(_admin())
        resp = client.get("/api/audit-logs?limit=1001")
        assert resp.status_code == 422

    def test_skip_validation_non_negative(self):
        """FastAPI validates skip >= 0."""
        _, client = _create_app(_admin())
        resp = client.get("/api/audit-logs?skip=-1")
        assert resp.status_code == 422


# ==================== Response Schema ====================


class TestAuditLogResponseSchema:
    """Verify Iteration 2 audit fields are present in API responses."""

    def test_dual_timestamps_present(self):
        """QA-13: occurred_at_utc and recorded_at_utc must both be in response."""
        repo = _mock_repo()
        log = _make_audit_log(log_id=1)
        repo.list_audit_logs.return_value = ([log], 1)
        _, client = _create_app(_admin(), repo)

        resp = client.get("/api/audit-logs")
        data = resp.json()["items"][0]
        assert "occurred_at_utc" in data
        assert "recorded_at_utc" in data
        assert data["occurred_at_utc"] is not None
        assert data["recorded_at_utc"] is not None

    def test_correlation_id_present(self):
        repo = _mock_repo()
        log = _make_audit_log(log_id=1, correlation_id="corr-xyz-789")
        repo.list_audit_logs.return_value = ([log], 1)
        _, client = _create_app(_admin(), repo)

        data = client.get("/api/audit-logs").json()["items"][0]
        assert data["correlation_id"] == "corr-xyz-789"

    def test_source_service_present(self):
        repo = _mock_repo()
        log = _make_audit_log(log_id=1, source_service="extraction-worker")
        repo.list_audit_logs.return_value = ([log], 1)
        _, client = _create_app(_admin(), repo)

        data = client.get("/api/audit-logs").json()["items"][0]
        assert data["source_service"] == "extraction-worker"

    def test_outcome_present(self):
        repo = _mock_repo()
        log = _make_audit_log(log_id=1, outcome="failure")
        repo.list_audit_logs.return_value = ([log], 1)
        _, client = _create_app(_admin(), repo)

        data = client.get("/api/audit-logs").json()["items"][0]
        assert data["outcome"] == "failure"

    def test_actor_role_present(self):
        repo = _mock_repo()
        log = _make_audit_log(log_id=1, actor_role="Admin")
        repo.list_audit_logs.return_value = ([log], 1)
        _, client = _create_app(_admin(), repo)

        data = client.get("/api/audit-logs").json()["items"][0]
        assert data["actor_role"] == "Admin"

    def test_ip_address_present(self):
        repo = _mock_repo()
        log = _make_audit_log(log_id=1, ip_address="192.168.1.100")
        repo.list_audit_logs.return_value = ([log], 1)
        _, client = _create_app(_admin(), repo)

        data = client.get("/api/audit-logs").json()["items"][0]
        assert data["ip_address"] == "192.168.1.100"

    def test_actor_type_serialized_as_string(self):
        """actor_type enum is serialized as its string value."""
        repo = _mock_repo()
        log = _make_audit_log(log_id=1)
        repo.list_audit_logs.return_value = ([log], 1)
        _, client = _create_app(_admin(), repo)

        data = client.get("/api/audit-logs").json()["items"][0]
        assert data["actor_type"] == "Employee"

    def test_nullable_fields_can_be_none(self):
        """Optional fields are null when not set."""
        repo = _mock_repo()
        log = _make_audit_log(
            log_id=1,
            details=None,
            initiated_by_id=None,
            correlation_id=None,
            source_service=None,
            outcome=None,
            ip_address=None,
        )
        repo.list_audit_logs.return_value = ([log], 1)
        _, client = _create_app(_admin(), repo)

        data = client.get("/api/audit-logs").json()["items"][0]
        assert data["details"] is None
        assert data["initiated_by_id"] is None
        assert data["correlation_id"] is None
        assert data["source_service"] is None
        assert data["outcome"] is None
        assert data["ip_address"] is None
