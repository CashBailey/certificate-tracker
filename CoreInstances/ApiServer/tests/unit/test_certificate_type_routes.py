"""
Unit tests for Certificate Type API routes.

Tests cover:
- RBAC: GET endpoints allow any auth user; CUD endpoints Coordinator-only
- GET /certificate-types: list, empty results
- GET /certificate-types/{id}: happy path, 404
- POST /certificate-types: create, duplicate name 400, schema validation
- PATCH /certificate-types/{id}: update, not found, name collision, no-op empty update
- DELETE /certificate-types/{id}: delete, not found, conflict when requirements exist
- Audit event emission on CUD operations
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.deps import get_repository, get_current_user
from src.routes.certificate_types import router
from src.shared.models import CertificateType, Employee, Role


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


def _make_cert_type(
    ct_id: int = 1,
    name: str = "OSHA 30-Hour",
    description: str = "Occupational safety training certificate",
    validity_period_days: int = 365,
) -> CertificateType:
    now = datetime.now(timezone.utc)
    return CertificateType(
        id=ct_id,
        name=name,
        description=description,
        validity_period_days=validity_period_days,
        created_at=now,
        updated_at=now,
    )


def _mock_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.list_certificate_types = AsyncMock(return_value=[])
    repo.get_certificate_type_by_id = AsyncMock(return_value=None)
    repo.get_certificate_type_by_name = AsyncMock(return_value=None)
    repo.create_certificate_type = AsyncMock(return_value=_make_cert_type())
    repo.update_certificate_type = AsyncMock(return_value=_make_cert_type())
    repo.delete_certificate_type = AsyncMock(return_value=True)
    repo.count_requirements_for_cert_type = AsyncMock(return_value=0)
    repo.create_audit_log = AsyncMock()
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


class TestCertTypeRBAC:
    """GET endpoints: any authenticated user. CUD: Coordinator only."""

    # --- GET (any authenticated user) ---

    def test_coordinator_allowed_list(self):
        _, client = _create_app(_coordinator())
        assert client.get("/api/certificate-types").status_code == 200

    def test_admin_allowed_list(self):
        _, client = _create_app(_admin())
        assert client.get("/api/certificate-types").status_code == 200

    def test_employee_allowed_list(self):
        _, client = _create_app(_employee())
        assert client.get("/api/certificate-types").status_code == 200

    def test_coordinator_allowed_get_by_id(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = _make_cert_type()
        _, client = _create_app(_coordinator(), repo)
        assert client.get("/api/certificate-types/1").status_code == 200

    def test_admin_allowed_get_by_id(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = _make_cert_type()
        _, client = _create_app(_admin(), repo)
        assert client.get("/api/certificate-types/1").status_code == 200

    def test_employee_allowed_get_by_id(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = _make_cert_type()
        _, client = _create_app(_employee(), repo)
        assert client.get("/api/certificate-types/1").status_code == 200

    # --- POST (Coordinator only) ---

    def test_coordinator_allowed_create(self):
        repo = _mock_repo()
        _, client = _create_app(_coordinator(), repo)
        resp = client.post(
            "/api/certificate-types",
            json={"name": "CDL Class A", "description": "Commercial driver license"},
        )
        assert resp.status_code == 201

    def test_admin_denied_create(self):
        _, client = _create_app(_admin())
        resp = client.post(
            "/api/certificate-types",
            json={"name": "CDL Class A", "description": "Commercial driver license"},
        )
        assert resp.status_code == 403

    def test_employee_denied_create(self):
        _, client = _create_app(_employee())
        resp = client.post(
            "/api/certificate-types",
            json={"name": "CDL Class A", "description": "Commercial driver license"},
        )
        assert resp.status_code == 403

    # --- PATCH (Coordinator only) ---

    def test_coordinator_allowed_update(self):
        repo = _mock_repo()
        ct = _make_cert_type()
        repo.get_certificate_type_by_id.return_value = ct
        repo.update_certificate_type.return_value = ct
        _, client = _create_app(_coordinator(), repo)
        resp = client.patch("/api/certificate-types/1", json={"name": "Updated Name"})
        assert resp.status_code == 200

    def test_admin_denied_update(self):
        _, client = _create_app(_admin())
        resp = client.patch("/api/certificate-types/1", json={"name": "Updated"})
        assert resp.status_code == 403

    def test_employee_denied_update(self):
        _, client = _create_app(_employee())
        resp = client.patch("/api/certificate-types/1", json={"name": "Updated"})
        assert resp.status_code == 403

    # --- DELETE (Coordinator only) ---

    def test_coordinator_allowed_delete(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = _make_cert_type()
        _, client = _create_app(_coordinator(), repo)
        resp = client.delete("/api/certificate-types/1")
        assert resp.status_code == 204

    def test_admin_denied_delete(self):
        _, client = _create_app(_admin())
        resp = client.delete("/api/certificate-types/1")
        assert resp.status_code == 403

    def test_employee_denied_delete(self):
        _, client = _create_app(_employee())
        resp = client.delete("/api/certificate-types/1")
        assert resp.status_code == 403


# ==================== GET /certificate-types ====================


class TestListCertificateTypes:
    """GET /api/certificate-types."""

    def test_empty_list(self):
        _, client = _create_app(_coordinator())
        resp = client.get("/api/certificate-types")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_entries(self):
        repo = _mock_repo()
        repo.list_certificate_types.return_value = [
            _make_cert_type(ct_id=1, name="OSHA 30"),
            _make_cert_type(ct_id=2, name="CDL Class A"),
        ]
        _, client = _create_app(_coordinator(), repo)

        resp = client.get("/api/certificate-types")
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "OSHA 30"
        assert data[1]["name"] == "CDL Class A"

    def test_response_schema_fields(self):
        repo = _mock_repo()
        ct = _make_cert_type(ct_id=5, validity_period_days=730)
        repo.list_certificate_types.return_value = [ct]
        _, client = _create_app(_coordinator(), repo)

        data = client.get("/api/certificate-types").json()[0]
        assert data["id"] == 5
        assert data["name"] == "OSHA 30-Hour"
        assert data["description"] == "Occupational safety training certificate"
        assert data["validity_period_days"] == 730
        assert "created_at" in data
        assert "updated_at" in data


# ==================== GET /certificate-types/{id} ====================


class TestGetCertificateTypeById:
    """GET /api/certificate-types/{cert_type_id}."""

    def test_found(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = _make_cert_type(ct_id=7, name="EPA Lead")
        _, client = _create_app(_coordinator(), repo)

        resp = client.get("/api/certificate-types/7")
        assert resp.status_code == 200
        assert resp.json()["name"] == "EPA Lead"

    def test_not_found(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = None
        _, client = _create_app(_coordinator(), repo)

        resp = client.get("/api/certificate-types/999")
        assert resp.status_code == 404

    def test_repo_called_with_correct_id(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = None
        _, client = _create_app(_coordinator(), repo)

        client.get("/api/certificate-types/42")
        repo.get_certificate_type_by_id.assert_called_once_with(42)


# ==================== POST /certificate-types ====================


class TestCreateCertificateType:
    """POST /api/certificate-types."""

    def test_create_success(self):
        repo = _mock_repo()
        created = _make_cert_type(ct_id=10, name="CDL Class A", description="Commercial driver")
        repo.create_certificate_type.return_value = created
        _, client = _create_app(_coordinator(), repo)

        resp = client.post(
            "/api/certificate-types",
            json={"name": "CDL Class A", "description": "Commercial driver"},
        )
        assert resp.status_code == 201
        assert resp.json()["id"] == 10
        assert resp.json()["name"] == "CDL Class A"

    def test_create_with_validity_period(self):
        repo = _mock_repo()
        created = _make_cert_type(ct_id=11, validity_period_days=730)
        repo.create_certificate_type.return_value = created
        _, client = _create_app(_coordinator(), repo)

        resp = client.post(
            "/api/certificate-types",
            json={
                "name": "OSHA 30-Hour",
                "description": "Safety training",
                "validity_period_days": 730,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["validity_period_days"] == 730

    def test_duplicate_name_returns_400(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_name.return_value = _make_cert_type(name="OSHA 30-Hour")
        _, client = _create_app(_coordinator(), repo)

        resp = client.post(
            "/api/certificate-types",
            json={"name": "OSHA 30-Hour", "description": "Duplicate"},
        )
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_missing_name_returns_422(self):
        _, client = _create_app(_coordinator())
        resp = client.post(
            "/api/certificate-types",
            json={"description": "No name provided"},
        )
        assert resp.status_code == 422

    def test_missing_description_returns_422(self):
        _, client = _create_app(_coordinator())
        resp = client.post(
            "/api/certificate-types",
            json={"name": "CDL Class A"},
        )
        assert resp.status_code == 422

    def test_validity_period_must_be_positive(self):
        _, client = _create_app(_coordinator())
        resp = client.post(
            "/api/certificate-types",
            json={
                "name": "Test",
                "description": "Test cert",
                "validity_period_days": 0,
            },
        )
        assert resp.status_code == 422

    def test_audit_event_emitted_on_create(self):
        repo = _mock_repo()
        created = _make_cert_type(ct_id=15, name="New Cert")
        repo.create_certificate_type.return_value = created
        _, client = _create_app(_coordinator(), repo)

        client.post(
            "/api/certificate-types",
            json={"name": "New Cert", "description": "Audit test"},
        )
        repo.create_audit_log.assert_called_once()
        audit_call = repo.create_audit_log.call_args[0][0]
        assert audit_call.action == "certificate_type_created"
        assert audit_call.target_type == "certificate_type"
        assert audit_call.target_id == "15"


# ==================== PATCH /certificate-types/{id} ====================


class TestUpdateCertificateType:
    """PATCH /api/certificate-types/{cert_type_id}."""

    def test_update_name(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, name="Old Name")
        updated = _make_cert_type(ct_id=1, name="New Name")
        repo.get_certificate_type_by_id.return_value = existing
        repo.update_certificate_type.return_value = updated
        _, client = _create_app(_coordinator(), repo)

        resp = client.patch("/api/certificate-types/1", json={"name": "New Name"})
        assert resp.status_code == 200

    def test_not_found_returns_404(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = None
        _, client = _create_app(_coordinator(), repo)

        resp = client.patch("/api/certificate-types/999", json={"name": "X"})
        assert resp.status_code == 404

    def test_name_collision_returns_400(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, name="Original")
        repo.get_certificate_type_by_id.return_value = existing
        repo.get_certificate_type_by_name.return_value = _make_cert_type(ct_id=2, name="Taken")
        _, client = _create_app(_coordinator(), repo)

        resp = client.patch("/api/certificate-types/1", json={"name": "Taken"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_empty_update_returns_existing(self):
        """PATCH with no fields set returns the existing entity unchanged."""
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, name="Unchanged")
        repo.get_certificate_type_by_id.return_value = existing
        _, client = _create_app(_coordinator(), repo)

        resp = client.patch("/api/certificate-types/1", json={})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Unchanged"
        # update_certificate_type should NOT be called for empty updates
        repo.update_certificate_type.assert_not_called()

    def test_same_name_no_collision(self):
        """Renaming to the same name should not trigger a collision check."""
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, name="SameName")
        updated = _make_cert_type(ct_id=1, name="SameName")
        repo.get_certificate_type_by_id.return_value = existing
        repo.update_certificate_type.return_value = updated
        _, client = _create_app(_coordinator(), repo)

        resp = client.patch("/api/certificate-types/1", json={"name": "SameName"})
        assert resp.status_code == 200
        # get_certificate_type_by_name should NOT be called when name unchanged
        repo.get_certificate_type_by_name.assert_not_called()

    def test_audit_event_emitted_on_update(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, name="Old", validity_period_days=365)
        updated = _make_cert_type(ct_id=1, name="New", validity_period_days=365)
        repo.get_certificate_type_by_id.return_value = existing
        repo.update_certificate_type.return_value = updated
        _, client = _create_app(_coordinator(), repo)

        client.patch("/api/certificate-types/1", json={"name": "New"})
        repo.create_audit_log.assert_called_once()
        audit_call = repo.create_audit_log.call_args[0][0]
        assert audit_call.action == "certificate_type_updated"
        assert "name" in audit_call.details["updated_fields"]


# ==================== DELETE /certificate-types/{id} ====================


class TestDeleteCertificateType:
    """DELETE /api/certificate-types/{cert_type_id}."""

    def test_delete_success(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = _make_cert_type(ct_id=1)
        repo.count_requirements_for_cert_type.return_value = 0
        _, client = _create_app(_coordinator(), repo)

        resp = client.delete("/api/certificate-types/1")
        assert resp.status_code == 204

    def test_not_found_returns_404(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = None
        _, client = _create_app(_coordinator(), repo)

        resp = client.delete("/api/certificate-types/999")
        assert resp.status_code == 404

    def test_conflict_when_requirements_exist(self):
        """Cannot delete a cert type that has active requirement assignments."""
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = _make_cert_type(ct_id=1)
        repo.count_requirements_for_cert_type.return_value = 3
        _, client = _create_app(_coordinator(), repo)

        resp = client.delete("/api/certificate-types/1")
        assert resp.status_code == 409
        assert "requirement assignments" in resp.json()["detail"]

    def test_repo_called_with_correct_id(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = _make_cert_type(ct_id=42)
        _, client = _create_app(_coordinator(), repo)

        client.delete("/api/certificate-types/42")
        repo.delete_certificate_type.assert_called_once_with(42)

    def test_audit_event_emitted_on_delete(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = _make_cert_type(ct_id=5, name="Deleted Cert")
        _, client = _create_app(_coordinator(), repo)

        client.delete("/api/certificate-types/5")
        repo.create_audit_log.assert_called_once()
        audit_call = repo.create_audit_log.call_args[0][0]
        assert audit_call.action == "certificate_type_deleted"
        assert audit_call.target_id == "5"
        assert audit_call.details["name"] == "Deleted Cert"
