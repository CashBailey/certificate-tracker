"""
Unit tests for Alert Configuration API routes.

Tests cover:
- RBAC: GET/PUT require Coordinator role; Admin and Employee denied
- GET /alert-config: returns config, 404 when missing
- PUT /alert-config: update, validation errors, audit emission
- Validation: day ranges, duplicates, descending sort, send time bounds
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.deps import get_repository, get_current_user
from src.routes.alert_config import router
from src.shared.models import AlertConfiguration, Employee, Role


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


def _make_config(
    req_days: list[int] | None = None,
    cert_days: list[int] | None = None,
    daily_overdue: bool = True,
    send_hour: int = 6,
    send_minute: int = 0,
    updated_by_id: int | None = 10,
) -> AlertConfiguration:
    return AlertConfiguration(
        id=1,
        requirement_reminder_days=req_days or [30, 14, 7],
        certificate_reminder_days=cert_days or [60, 30, 14],
        daily_overdue_enabled=daily_overdue,
        global_send_hour=send_hour,
        global_send_minute=send_minute,
        updated_at=datetime.now(timezone.utc),
        updated_by_id=updated_by_id,
    )


def _mock_repo(config: AlertConfiguration | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_alert_configuration = AsyncMock(
        return_value=config if config is not None else _make_config()
    )
    repo.update_alert_configuration = AsyncMock(
        return_value=config if config is not None else _make_config()
    )
    repo.create_audit_log = AsyncMock()
    return repo


def _valid_update_body() -> dict:
    return {
        "requirement_reminder_days": [30, 14, 7],
        "certificate_reminder_days": [60, 30, 14],
        "daily_overdue_enabled": True,
        "global_send_hour": 6,
        "global_send_minute": 0,
    }


def _create_app(user: Employee, repo: AsyncMock = None) -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    if repo is None:
        repo = _mock_repo()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: user
    return app, TestClient(app)


# ==================== RBAC Tests ====================


class TestAlertConfigRBAC:
    """GET/PUT require Coordinator. Admin and Employee are denied."""

    def test_coordinator_allowed_get(self):
        _, client = _create_app(_coordinator())
        assert client.get("/api/alert-config").status_code == 200

    def test_admin_denied_get(self):
        _, client = _create_app(_admin())
        assert client.get("/api/alert-config").status_code == 403

    def test_employee_denied_get(self):
        _, client = _create_app(_employee())
        assert client.get("/api/alert-config").status_code == 403

    def test_coordinator_allowed_put(self):
        _, client = _create_app(_coordinator())
        resp = client.put("/api/alert-config", json=_valid_update_body())
        assert resp.status_code == 200

    def test_admin_denied_put(self):
        _, client = _create_app(_admin())
        resp = client.put("/api/alert-config", json=_valid_update_body())
        assert resp.status_code == 403

    def test_employee_denied_put(self):
        _, client = _create_app(_employee())
        resp = client.put("/api/alert-config", json=_valid_update_body())
        assert resp.status_code == 403


# ==================== GET Tests ====================


class TestGetAlertConfig:
    """GET /alert-config: success and 404 paths."""

    def test_returns_config(self):
        config = _make_config(req_days=[30, 14, 7], cert_days=[60, 30])
        repo = _mock_repo(config)
        _, client = _create_app(_coordinator(), repo)

        resp = client.get("/api/alert-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["requirement_reminder_days"] == [30, 14, 7]
        assert data["certificate_reminder_days"] == [60, 30]
        assert data["daily_overdue_enabled"] is True
        assert data["global_send_hour"] == 6
        assert data["global_send_minute"] == 0

    def test_returns_404_when_missing(self):
        repo = _mock_repo()
        repo.get_alert_configuration.return_value = None
        _, client = _create_app(_coordinator(), repo)

        resp = client.get("/api/alert-config")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_returns_updated_by_id(self):
        config = _make_config(updated_by_id=42)
        repo = _mock_repo(config)
        _, client = _create_app(_coordinator(), repo)

        resp = client.get("/api/alert-config")
        assert resp.json()["updated_by_id"] == 42


# ==================== PUT Tests ====================


class TestUpdateAlertConfig:
    """PUT /alert-config: happy path and edge cases."""

    def test_update_success(self):
        updated = _make_config(
            req_days=[60, 30, 14],
            cert_days=[90, 60, 30],
            daily_overdue=False,
            send_hour=8,
            send_minute=30,
        )
        repo = _mock_repo()
        repo.update_alert_configuration.return_value = updated
        _, client = _create_app(_coordinator(), repo)

        body = {
            "requirement_reminder_days": [60, 30, 14],
            "certificate_reminder_days": [90, 60, 30],
            "daily_overdue_enabled": False,
            "global_send_hour": 8,
            "global_send_minute": 30,
        }
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["requirement_reminder_days"] == [60, 30, 14]
        assert data["daily_overdue_enabled"] is False
        assert data["global_send_hour"] == 8
        assert data["global_send_minute"] == 30

    def test_update_404_when_config_missing(self):
        repo = _mock_repo()
        repo.get_alert_configuration.return_value = None
        _, client = _create_app(_coordinator(), repo)

        resp = client.put("/api/alert-config", json=_valid_update_body())
        assert resp.status_code == 404

    def test_update_emits_audit_when_changed(self):
        old = _make_config(req_days=[30, 14, 7], daily_overdue=True)
        new = _make_config(req_days=[60, 30], daily_overdue=False)
        repo = _mock_repo(old)
        repo.update_alert_configuration.return_value = new
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["requirement_reminder_days"] = [60, 30]
        body["daily_overdue_enabled"] = False
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 200
        repo.create_audit_log.assert_called_once()

    def test_update_no_audit_when_unchanged(self):
        config = _make_config()
        repo = _mock_repo(config)
        repo.update_alert_configuration.return_value = config
        _, client = _create_app(_coordinator(), repo)

        resp = client.put("/api/alert-config", json=_valid_update_body())
        assert resp.status_code == 200
        repo.create_audit_log.assert_not_called()

    def test_update_calls_repository(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        client.put("/api/alert-config", json=_valid_update_body())
        repo.update_alert_configuration.assert_called_once()


# ==================== Validation Tests ====================


class TestAlertConfigValidation:
    """Day offset validation: range, duplicates, sort order, send time."""

    def test_day_below_1_rejected(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["requirement_reminder_days"] = [30, 0]
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_day_above_365_rejected(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["requirement_reminder_days"] = [366, 30]
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_duplicate_days_rejected(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["requirement_reminder_days"] = [30, 30, 7]
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_ascending_order_rejected(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["requirement_reminder_days"] = [7, 14, 30]
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_cert_days_validation_also_applies(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["certificate_reminder_days"] = [14, 14]
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_empty_days_list_rejected(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["requirement_reminder_days"] = []
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_send_hour_negative_rejected(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["global_send_hour"] = -1
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_send_hour_above_23_rejected(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["global_send_hour"] = 24
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_send_minute_negative_rejected(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["global_send_minute"] = -1
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_send_minute_above_59_rejected(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["global_send_minute"] = 60
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_missing_required_field_rejected(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        del body["daily_overdue_enabled"]
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 422

    def test_single_day_value_accepted(self):
        config = _make_config(req_days=[7], cert_days=[14])
        repo = _mock_repo(config)
        repo.update_alert_configuration.return_value = config
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["requirement_reminder_days"] = [7]
        body["certificate_reminder_days"] = [14]
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 200

    def test_boundary_day_values_accepted(self):
        config = _make_config(req_days=[365, 1], cert_days=[365, 1])
        repo = _mock_repo(config)
        repo.update_alert_configuration.return_value = config
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["requirement_reminder_days"] = [365, 1]
        body["certificate_reminder_days"] = [365, 1]
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 200

    def test_send_time_boundaries_accepted(self):
        config = _make_config(send_hour=23, send_minute=59)
        repo = _mock_repo(config)
        repo.update_alert_configuration.return_value = config
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["global_send_hour"] = 23
        body["global_send_minute"] = 59
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 200

    def test_send_time_zero_accepted(self):
        config = _make_config(send_hour=0, send_minute=0)
        repo = _mock_repo(config)
        repo.update_alert_configuration.return_value = config
        _, client = _create_app(_coordinator(), repo)

        body = _valid_update_body()
        body["global_send_hour"] = 0
        body["global_send_minute"] = 0
        resp = client.put("/api/alert-config", json=body)
        assert resp.status_code == 200
