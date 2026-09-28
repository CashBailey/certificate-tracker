"""
Unit tests for Admin boundary enforcement across all API routes.

Verifies the working model:
- Coordinator: full operational access (certificate workflows, configuration)
- Admin: governance/oversight only (employees, audit logs). NO certificate operations.
- Employee: no web API access except notifications.

Tests use FastAPI TestClient with dependency overrides to verify that the
require_coordinator, require_coordinator_or_admin, and require_admin
dependencies correctly enforce role boundaries at the route level.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.deps import get_db_session, get_repository, get_current_user
from src.shared.models import Employee, Role


# ==================== Helpers ====================


def _make_user(role: Role, employee_id: int = 1) -> Employee:
    """Create a test employee with the given role."""
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


def _mock_repo() -> AsyncMock:
    """Create a mock repository that returns empty results for all queries."""
    repo = AsyncMock()
    repo.list_certificate_types = AsyncMock(return_value=[])
    repo.list_requirements = AsyncMock(return_value=[])
    repo.list_requirements_paged = AsyncMock(return_value=([], 0))
    repo.list_extractions = AsyncMock(return_value=[])
    repo.list_audit_logs = AsyncMock(return_value=([], 0))
    repo.list_verified_records = AsyncMock(return_value=[])
    repo.list_templates = AsyncMock(return_value=([], 0))
    repo.list_employees = AsyncMock(return_value=[])
    repo.count_employees = AsyncMock(return_value=0)
    repo.get_compliance_report = AsyncMock(return_value=[])
    return repo


def _create_app_with_user(user: Employee) -> tuple[FastAPI, TestClient]:
    """Create a FastAPI app with all routers and the given user."""
    from src.routes.documents import router as documents_router
    from src.routes.requirements import router as requirements_router
    from src.routes.extractions import router as extractions_router
    from src.routes.templates import router as templates_router
    from src.routes.verified_records import router as verified_records_router
    from src.routes.reports import router as reports_router
    from src.routes.audit_logs import router as audit_logs_router
    from src.routes.employees import router as employees_router
    from src.routes.admin import router as admin_router
    from src.routes.certificate_types import router as cert_types_router

    app = FastAPI()

    app.include_router(documents_router, prefix="/api")
    app.include_router(requirements_router, prefix="/api")
    app.include_router(extractions_router, prefix="/api")
    app.include_router(templates_router, prefix="/api")
    app.include_router(verified_records_router, prefix="/api")
    app.include_router(reports_router, prefix="/api")
    app.include_router(audit_logs_router, prefix="/api")
    app.include_router(employees_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(cert_types_router, prefix="/api")

    repo = _mock_repo()
    # Mock DB session for routes that use get_db_session directly (e.g. employees).
    # scalars() and scalar() are sync methods on the Result object, so use MagicMock.
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar_one_or_none.return_value = 0
    mock_result.scalar.return_value = 0
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: mock_db

    return app, TestClient(app)


# ==================== Coordinator-Only Routes (require_coordinator) ====================
# Admin and Employee must get 403.


class TestCoordinatorOnlyRoutes:
    """Routes using require_coordinator — Admin and Employee denied."""

    # --- Requirements ---

    def test_admin_denied_list_requirements(self):
        _, client = _create_app_with_user(_admin())
        resp = client.get("/api/requirements")
        assert resp.status_code == 403

    def test_employee_denied_list_requirements(self):
        _, client = _create_app_with_user(_employee())
        resp = client.get("/api/requirements")
        assert resp.status_code == 403

    def test_coordinator_allowed_list_requirements(self):
        _, client = _create_app_with_user(_coordinator())
        resp = client.get("/api/requirements")
        assert resp.status_code == 200

    # --- Extractions ---

    def test_admin_denied_list_extractions(self):
        _, client = _create_app_with_user(_admin())
        resp = client.get("/api/extractions")
        assert resp.status_code == 403

    def test_employee_denied_list_extractions(self):
        _, client = _create_app_with_user(_employee())
        resp = client.get("/api/extractions")
        assert resp.status_code == 403

    def test_coordinator_allowed_list_extractions(self):
        _, client = _create_app_with_user(_coordinator())
        resp = client.get("/api/extractions")
        assert resp.status_code == 200

    # --- Templates ---

    def test_admin_denied_list_templates(self):
        _, client = _create_app_with_user(_admin())
        resp = client.get("/api/templates")
        assert resp.status_code == 403

    def test_employee_denied_list_templates(self):
        _, client = _create_app_with_user(_employee())
        resp = client.get("/api/templates")
        assert resp.status_code == 403

    def test_coordinator_allowed_list_templates(self):
        from unittest.mock import patch, MagicMock as _MagicMock

        mock_registry = _MagicMock()
        mock_registry.list_templates.return_value = []
        mock_registry.get_registry_hash.return_value = "testhash"
        with patch("src.routes.templates.get_template_registry", return_value=mock_registry):
            _, client = _create_app_with_user(_coordinator())
            resp = client.get("/api/templates")
        assert resp.status_code == 200

    # --- Verified Records ---

    def test_admin_denied_list_verified_records(self):
        _, client = _create_app_with_user(_admin())
        resp = client.get("/api/verified-records")
        assert resp.status_code == 403

    def test_employee_denied_list_verified_records(self):
        _, client = _create_app_with_user(_employee())
        resp = client.get("/api/verified-records")
        assert resp.status_code == 403

    def test_coordinator_allowed_list_verified_records(self):
        _, client = _create_app_with_user(_coordinator())
        resp = client.get("/api/verified-records")
        assert resp.status_code == 200

    # --- Reports ---

    def test_admin_denied_requirements_report(self):
        _, client = _create_app_with_user(_admin())
        resp = client.get("/api/reports/requirements")
        assert resp.status_code == 403

    def test_employee_denied_requirements_report(self):
        _, client = _create_app_with_user(_employee())
        resp = client.get("/api/reports/requirements")
        assert resp.status_code == 403

    def test_coordinator_allowed_requirements_report(self):
        _, client = _create_app_with_user(_coordinator())
        resp = client.get("/api/reports/requirements")
        assert resp.status_code == 200


# ==================== Admin-Only Routes (Audit Logs) ====================
# Only Admin allowed; Coordinator and Employee denied.


class TestAdminOnlyAuditLogs:
    """Audit log routes use require_admin — only Admin allowed."""

    def test_coordinator_denied_list_audit_logs(self):
        _, client = _create_app_with_user(_coordinator())
        resp = client.get("/api/audit-logs")
        assert resp.status_code == 403

    def test_admin_allowed_list_audit_logs(self):
        _, client = _create_app_with_user(_admin())
        resp = client.get("/api/audit-logs")
        assert resp.status_code == 200

    def test_employee_denied_list_audit_logs(self):
        _, client = _create_app_with_user(_employee())
        resp = client.get("/api/audit-logs")
        assert resp.status_code == 403


# ==================== Coordinator-or-Admin Routes ====================
# Employee must get 403; both Coordinator and Admin allowed.


class TestCoordinatorOrAdminRoutes:
    """Routes using require_coordinator_or_admin — Employee denied."""

    # --- Employees ---

    def test_coordinator_allowed_list_employees(self):
        _, client = _create_app_with_user(_coordinator())
        resp = client.get("/api/employees")
        assert resp.status_code == 200

    def test_admin_allowed_list_employees(self):
        _, client = _create_app_with_user(_admin())
        resp = client.get("/api/employees")
        assert resp.status_code == 200

    def test_employee_denied_list_employees(self):
        _, client = _create_app_with_user(_employee())
        resp = client.get("/api/employees")
        assert resp.status_code == 403


# ==================== Admin-Only Routes ====================
# Coordinator and Employee must get 403.


class TestAdminOnlyRoutes:
    """Routes using require_admin — only Admin allowed."""

    def test_admin_allowed_gal_import(self):
        """Admin can access GAL import."""
        from src.routes.admin import router as admin_router

        app = FastAPI()
        app.include_router(admin_router, prefix="/api")

        repo = _mock_repo()
        app.dependency_overrides[get_repository] = lambda: repo
        app.dependency_overrides[get_current_user] = lambda: _admin()

        # GAL import needs a DB session dependency too — we just check
        # that the role gate passes (will get a different error if deps missing)
        client = TestClient(app)
        resp = client.post("/api/admin/gal/import")
        # 403 means role was denied; anything else means role was accepted
        assert resp.status_code != 403

    def test_coordinator_denied_gal_import(self):
        """Coordinator cannot access GAL import."""
        from src.routes.admin import router as admin_router

        app = FastAPI()
        app.include_router(admin_router, prefix="/api")

        repo = _mock_repo()
        app.dependency_overrides[get_repository] = lambda: repo
        app.dependency_overrides[get_current_user] = lambda: _coordinator()

        client = TestClient(app)
        resp = client.post("/api/admin/gal/import")
        assert resp.status_code == 403

    def test_employee_denied_gal_import(self):
        """Employee cannot access GAL import."""
        from src.routes.admin import router as admin_router

        app = FastAPI()
        app.include_router(admin_router, prefix="/api")

        repo = _mock_repo()
        app.dependency_overrides[get_repository] = lambda: repo
        app.dependency_overrides[get_current_user] = lambda: _employee()

        client = TestClient(app)
        resp = client.post("/api/admin/gal/import")
        assert resp.status_code == 403


# ==================== Certificate Type Routes ====================
# Currently uses get_current_user (any authenticated user).


class TestCertificateTypeAccess:
    """Certificate type routes — currently any authenticated user."""

    def test_coordinator_allowed_list_cert_types(self):
        _, client = _create_app_with_user(_coordinator())
        resp = client.get("/api/certificate-types")
        assert resp.status_code == 200

    def test_admin_allowed_list_cert_types(self):
        _, client = _create_app_with_user(_admin())
        resp = client.get("/api/certificate-types")
        assert resp.status_code == 200

    def test_employee_allowed_list_cert_types(self):
        """Employee can list cert types (read-only, needed for context)."""
        _, client = _create_app_with_user(_employee())
        resp = client.get("/api/certificate-types")
        assert resp.status_code == 200
