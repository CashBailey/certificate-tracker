"""
Unit tests for certificate type CRUD API routes.

Tests the endpoints in src/routes/certificate_types.py using FastAPI's TestClient
with dependency overrides for repository and authentication.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.deps import get_repository, get_current_user
from src.routes.certificate_types import router
from src.shared.models import AuditLog, AuditActorType, CertificateType, Employee, Role


# ==================== Helpers ====================


def _make_coordinator(employee_id: int = 10) -> Employee:
    """Create a test Coordinator employee."""
    return Employee(
        id=employee_id,
        employee_number="E00010",
        first_name="Coord",
        last_name="User",
        email="coord@ci.laredo.tx.us",
        role=Role.COORDINATOR,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_employee(employee_id: int = 30) -> Employee:
    """Create a test Employee-role user."""
    return Employee(
        id=employee_id,
        employee_number="E00030",
        first_name="Regular",
        last_name="Employee",
        email="employee@ci.laredo.tx.us",
        role=Role.EMPLOYEE,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_admin(employee_id: int = 20) -> Employee:
    """Create a test Admin employee."""
    return Employee(
        id=employee_id,
        employee_number="E00020",
        first_name="Admin",
        last_name="User",
        email="admin@ci.laredo.tx.us",
        role=Role.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


_NOW = datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc)


def _make_cert_type(
    ct_id: int = 1,
    name: str = "First Aid & CPR Certification",
    description: str = "American Red Cross or equivalent",
    validity_period_days: int | None = 730,
) -> CertificateType:
    """Create a test CertificateType."""
    return CertificateType(
        id=ct_id,
        name=name,
        description=description,
        validity_period_days=validity_period_days,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _mock_repo() -> AsyncMock:
    """Create a mock repository with default behaviors."""
    repo = AsyncMock()
    repo.list_certificate_types = AsyncMock(return_value=[])
    repo.get_certificate_type_by_id = AsyncMock(return_value=None)
    repo.get_certificate_type_by_name = AsyncMock(return_value=None)
    repo.create_certificate_type = AsyncMock()
    repo.update_certificate_type = AsyncMock()
    repo.delete_certificate_type = AsyncMock(return_value=True)
    repo.count_requirements_for_cert_type = AsyncMock(return_value=0)
    repo.create_audit_log = AsyncMock(
        return_value=AuditLog(
            id=1,
            actor_type=AuditActorType.EMPLOYEE,
            employee_id=10,
            action="test",
            target_type="certificate_type",
            target_id="1",
        )
    )
    return repo


def _create_app(mock_repo: AsyncMock, user: Employee) -> FastAPI:
    """Create a FastAPI app with overridden dependencies."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_repository] = lambda: mock_repo
    app.dependency_overrides[get_current_user] = lambda: user
    return app


# ==================== List Tests ====================


class TestListCertificateTypes:
    """Tests for GET /api/certificate-types"""

    def test_list_empty(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.get("/api/certificate-types")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_all(self):
        repo = _mock_repo()
        ct1 = _make_cert_type(ct_id=1, name="CDL", description="Commercial Driver License")
        ct2 = _make_cert_type(ct_id=2, name="CPR", description="CPR Cert", validity_period_days=730)
        repo.list_certificate_types.return_value = [ct1, ct2]

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.get("/api/certificate-types")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "CDL"
        assert data[1]["name"] == "CPR"

    def test_list_accessible_by_employee(self):
        """Any authenticated user can list cert types."""
        repo = _mock_repo()
        app = _create_app(repo, _make_employee())
        client = TestClient(app)

        resp = client.get("/api/certificate-types")
        assert resp.status_code == 200

    def test_list_accessible_by_admin(self):
        """Admin can list cert types."""
        repo = _mock_repo()
        app = _create_app(repo, _make_admin())
        client = TestClient(app)

        resp = client.get("/api/certificate-types")
        assert resp.status_code == 200


# ==================== Get By ID Tests ====================


class TestGetCertificateType:
    """Tests for GET /api/certificate-types/{id}"""

    def test_get_existing(self):
        repo = _mock_repo()
        ct = _make_cert_type(ct_id=5)
        repo.get_certificate_type_by_id.return_value = ct

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.get("/api/certificate-types/5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 5
        assert data["name"] == "First Aid & CPR Certification"
        assert data["validity_period_days"] == 730

    def test_get_not_found(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.get("/api/certificate-types/999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_accessible_by_employee(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_id.return_value = _make_cert_type()
        app = _create_app(repo, _make_employee())
        client = TestClient(app)

        resp = client.get("/api/certificate-types/1")
        assert resp.status_code == 200


# ==================== Create Tests ====================


class TestCreateCertificateType:
    """Tests for POST /api/certificate-types"""

    def test_create_success(self):
        repo = _mock_repo()
        created = _make_cert_type(ct_id=7, name="New Cert", description="New desc", validity_period_days=365)
        repo.create_certificate_type.return_value = created

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.post("/api/certificate-types", json={
            "name": "New Cert",
            "description": "New desc",
            "validity_period_days": 365,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == 7
        assert data["name"] == "New Cert"
        assert data["validity_period_days"] == 365

    def test_create_non_expiring(self):
        """Create cert type with null validity_period_days."""
        repo = _mock_repo()
        created = _make_cert_type(ct_id=8, name="LMS", description="LMS cert", validity_period_days=None)
        repo.create_certificate_type.return_value = created

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.post("/api/certificate-types", json={
            "name": "LMS",
            "description": "LMS cert",
        })
        assert resp.status_code == 201
        assert resp.json()["validity_period_days"] is None

    def test_create_duplicate_name(self):
        repo = _mock_repo()
        repo.get_certificate_type_by_name.return_value = _make_cert_type()

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.post("/api/certificate-types", json={
            "name": "First Aid & CPR Certification",
            "description": "Duplicate",
        })
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_create_forbidden_for_employee(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_employee())
        client = TestClient(app)

        resp = client.post("/api/certificate-types", json={
            "name": "Test",
            "description": "Test",
        })
        assert resp.status_code == 403

    def test_create_forbidden_for_admin(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_admin())
        client = TestClient(app)

        resp = client.post("/api/certificate-types", json={
            "name": "Test",
            "description": "Test",
        })
        assert resp.status_code == 403

    def test_create_validation_empty_name(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.post("/api/certificate-types", json={
            "name": "",
            "description": "Desc",
        })
        assert resp.status_code == 422

    def test_create_validation_name_too_long(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.post("/api/certificate-types", json={
            "name": "x" * 201,
            "description": "Desc",
        })
        assert resp.status_code == 422

    def test_create_validation_validity_zero(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.post("/api/certificate-types", json={
            "name": "Test",
            "description": "Desc",
            "validity_period_days": 0,
        })
        assert resp.status_code == 422

    def test_create_validation_validity_negative(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.post("/api/certificate-types", json={
            "name": "Test",
            "description": "Desc",
            "validity_period_days": -1,
        })
        assert resp.status_code == 422


# ==================== Update Tests ====================


class TestUpdateCertificateType:
    """Tests for PATCH /api/certificate-types/{id}"""

    def test_update_name(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, name="Old Name")
        updated = _make_cert_type(ct_id=1, name="New Name")
        repo.get_certificate_type_by_id.return_value = existing
        repo.update_certificate_type.return_value = updated

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.patch("/api/certificate-types/1", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_update_validity_period(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, validity_period_days=730)
        updated = _make_cert_type(ct_id=1, validity_period_days=365)
        repo.get_certificate_type_by_id.return_value = existing
        repo.update_certificate_type.return_value = updated

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.patch("/api/certificate-types/1", json={"validity_period_days": 365})
        assert resp.status_code == 200
        assert resp.json()["validity_period_days"] == 365

    def test_update_not_found(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.patch("/api/certificate-types/999", json={"name": "X"})
        assert resp.status_code == 404

    def test_update_duplicate_name(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, name="Old Name")
        collision = _make_cert_type(ct_id=2, name="Taken Name")
        repo.get_certificate_type_by_id.return_value = existing
        repo.get_certificate_type_by_name.return_value = collision

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.patch("/api/certificate-types/1", json={"name": "Taken Name"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_update_same_name_no_collision(self):
        """Updating with the same name should not trigger uniqueness check."""
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, name="Same Name")
        updated = _make_cert_type(ct_id=1, name="Same Name")
        repo.get_certificate_type_by_id.return_value = existing
        repo.update_certificate_type.return_value = updated

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.patch("/api/certificate-types/1", json={"name": "Same Name"})
        assert resp.status_code == 200
        # Should not have called get_by_name since name didn't change
        repo.get_certificate_type_by_name.assert_not_called()

    def test_update_empty_body_returns_existing(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1)
        repo.get_certificate_type_by_id.return_value = existing

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.patch("/api/certificate-types/1", json={})
        assert resp.status_code == 200
        assert resp.json()["id"] == 1
        # Should not have called update since no fields changed
        repo.update_certificate_type.assert_not_called()

    def test_update_forbidden_for_employee(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_employee())
        client = TestClient(app)

        resp = client.patch("/api/certificate-types/1", json={"name": "X"})
        assert resp.status_code == 403

    def test_update_forbidden_for_admin(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_admin())
        client = TestClient(app)

        resp = client.patch("/api/certificate-types/1", json={"name": "X"})
        assert resp.status_code == 403


# ==================== Delete Tests ====================


class TestDeleteCertificateType:
    """Tests for DELETE /api/certificate-types/{id}"""

    def test_delete_success(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1)
        repo.get_certificate_type_by_id.return_value = existing

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.delete("/api/certificate-types/1")
        assert resp.status_code == 204

    def test_delete_not_found(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.delete("/api/certificate-types/999")
        assert resp.status_code == 404

    def test_delete_with_active_requirements(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1)
        repo.get_certificate_type_by_id.return_value = existing
        repo.count_requirements_for_cert_type.return_value = 3

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        resp = client.delete("/api/certificate-types/1")
        assert resp.status_code == 409
        assert "requirement assignments" in resp.json()["detail"].lower()

    def test_delete_forbidden_for_employee(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_employee())
        client = TestClient(app)

        resp = client.delete("/api/certificate-types/1")
        assert resp.status_code == 403

    def test_delete_forbidden_for_admin(self):
        repo = _mock_repo()
        app = _create_app(repo, _make_admin())
        client = TestClient(app)

        resp = client.delete("/api/certificate-types/1")
        assert resp.status_code == 403


# ==================== Audit Tests ====================


class TestCertificateTypeAudit:
    """Tests that mutations emit audit events."""

    def test_create_emits_audit(self):
        repo = _mock_repo()
        created = _make_cert_type(ct_id=7, name="Audited Cert")
        repo.create_certificate_type.return_value = created

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        client.post("/api/certificate-types", json={
            "name": "Audited Cert",
            "description": "Desc",
        })

        repo.create_audit_log.assert_called_once()
        audit_arg = repo.create_audit_log.call_args[0][0]
        assert audit_arg.action == "certificate_type_created"
        assert audit_arg.target_type == "certificate_type"
        assert audit_arg.target_id == "7"

    def test_update_emits_audit(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, name="Old")
        updated = _make_cert_type(ct_id=1, name="New")
        repo.get_certificate_type_by_id.return_value = existing
        repo.update_certificate_type.return_value = updated

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        client.patch("/api/certificate-types/1", json={"name": "New"})

        repo.create_audit_log.assert_called_once()
        audit_arg = repo.create_audit_log.call_args[0][0]
        assert audit_arg.action == "certificate_type_updated"
        assert "name" in audit_arg.details["updated_fields"]

    def test_delete_emits_audit(self):
        repo = _mock_repo()
        existing = _make_cert_type(ct_id=1, name="Deleted Cert")
        repo.get_certificate_type_by_id.return_value = existing

        app = _create_app(repo, _make_coordinator())
        client = TestClient(app)

        client.delete("/api/certificate-types/1")

        repo.create_audit_log.assert_called_once()
        audit_arg = repo.create_audit_log.call_args[0][0]
        assert audit_arg.action == "certificate_type_deleted"
        assert audit_arg.details["name"] == "Deleted Cert"
