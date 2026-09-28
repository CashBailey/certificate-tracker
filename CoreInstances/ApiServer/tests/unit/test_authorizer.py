"""
Unit tests for authorizer — verifies RBAC enforcement.

Coordinator: allowed for all certificate operations.
Employee/Admin/Reviewer: denied for certificate operations.
"""

import pytest
from datetime import datetime, timezone

from src.authorizer import Authorizer
from src.shared.models import Employee, Role


@pytest.fixture
def authorizer():
    return Authorizer()


def _make_employee(role: Role, id: int = 1) -> Employee:
    return Employee(
        id=id, employee_number=f"E{id:03d}", first_name="Test", last_name="User",
        email=f"test{id}@dept.test", role=role, is_active=True,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def coordinator():
    return _make_employee(Role.COORDINATOR, id=2)


# ==================== Coordinator Allowed ====================


class TestCoordinatorAllowed:
    """Coordinator passes all certificate-operation checks."""

    def test_can_upload(self, authorizer, coordinator):
        assert authorizer.can_upload(coordinator, 999) is True

    def test_require_can_upload(self, authorizer, coordinator):
        authorizer.require_can_upload(coordinator, 999)

    def test_can_review_extraction(self, authorizer, coordinator):
        assert authorizer.can_review_extraction(coordinator) is True

    def test_can_review_extraction_other_employee(self, authorizer, coordinator):
        assert authorizer.can_review_extraction(coordinator, employee_id=999) is True

    def test_can_review_extraction_uploader_can_review_others_cert(self, authorizer, coordinator):
        """Coordinator who uploaded a cert for another employee CAN review it."""
        assert authorizer.can_review_extraction(coordinator, employee_id=999) is True

    def test_can_review_extraction_denies_own_certificate(self, authorizer, coordinator):
        """Coordinator cannot review a certificate that belongs to them."""
        assert authorizer.can_review_extraction(coordinator, employee_id=coordinator.id) is False

    def test_require_can_review_extraction_denies_own_certificate(self, authorizer, coordinator):
        with pytest.raises(PermissionError, match="Cannot review your own certificate"):
            authorizer.require_can_review_extraction(coordinator, employee_id=coordinator.id)

    def test_require_can_review_extraction(self, authorizer, coordinator):
        authorizer.require_can_review_extraction(coordinator)

    def test_can_view_extraction(self, authorizer, coordinator):
        assert authorizer.can_view_extraction(coordinator, 999) is True

    def test_require_can_view_extraction(self, authorizer, coordinator):
        authorizer.require_can_view_extraction(coordinator, 999)

    def test_can_view_reports(self, authorizer, coordinator):
        assert authorizer.can_view_reports(coordinator) is True

    def test_require_can_view_reports(self, authorizer, coordinator):
        authorizer.require_can_view_reports(coordinator)


# ==================== Non-Coordinator Denied ====================


class TestNonCoordinatorDenied:
    """Employee and Admin are denied certificate operations."""

    @pytest.fixture(params=[Role.EMPLOYEE, Role.ADMIN])
    def non_coordinator(self, request):
        return _make_employee(request.param)

    def test_can_upload_denied(self, authorizer, non_coordinator):
        assert authorizer.can_upload(non_coordinator, 999) is False

    def test_require_can_upload_denied(self, authorizer, non_coordinator):
        with pytest.raises(PermissionError, match="Only Coordinators"):
            authorizer.require_can_upload(non_coordinator, 999)

    def test_can_review_denied(self, authorizer, non_coordinator):
        assert authorizer.can_review_extraction(non_coordinator) is False

    def test_require_can_review_denied(self, authorizer, non_coordinator):
        with pytest.raises(PermissionError, match="Only Coordinators"):
            authorizer.require_can_review_extraction(non_coordinator)

    def test_can_view_extraction_denied(self, authorizer, non_coordinator):
        assert authorizer.can_view_extraction(non_coordinator, 999) is False

    def test_require_can_view_extraction_denied(self, authorizer, non_coordinator):
        with pytest.raises(PermissionError, match="Only Coordinators"):
            authorizer.require_can_view_extraction(non_coordinator, 999)

    def test_can_view_reports_denied(self, authorizer, non_coordinator):
        assert authorizer.can_view_reports(non_coordinator) is False

    def test_require_can_view_reports_denied(self, authorizer, non_coordinator):
        with pytest.raises(PermissionError, match="Only Coordinators"):
            authorizer.require_can_view_reports(non_coordinator)


