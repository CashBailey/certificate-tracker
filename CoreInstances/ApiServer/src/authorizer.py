"""
Authorization for the City of Laredo Certificate Management System.

RBAC enforcement: Coordinator-only for certificate operations,
Admin limited to role management.
"""

from typing import Optional

from .shared.models import Employee, Role


class Authorizer:
    """Role-based authorization enforcement."""

    # --- Upload ---
    def can_upload(self, uploader: Employee, target_employee_id: int) -> bool:
        return uploader.role == Role.COORDINATOR

    def require_can_upload(self, uploader: Employee, target_employee_id: int) -> None:
        if not self.can_upload(uploader, target_employee_id):
            raise PermissionError("Only Coordinators can upload documents")

    # --- Review Extraction ---
    def can_review_extraction(
        self,
        reviewer: Employee,
        employee_id: Optional[int] = None,
    ) -> bool:
        if reviewer.role != Role.COORDINATOR:
            return False
        if employee_id is None:
            return True
        return reviewer.id != employee_id

    def require_can_review_extraction(
        self,
        reviewer: Employee,
        employee_id: Optional[int] = None,
    ) -> None:
        if not self.can_review_extraction(reviewer, employee_id):
            if reviewer.role != Role.COORDINATOR:
                raise PermissionError("Only Coordinators can review extractions")
            raise PermissionError("Cannot review your own certificate")

    # --- View Extraction ---
    def can_view_extraction(self, viewer: Employee, document_employee_id: int) -> bool:
        return viewer.role == Role.COORDINATOR

    def require_can_view_extraction(self, viewer: Employee, document_employee_id: int) -> None:
        if not self.can_view_extraction(viewer, document_employee_id):
            raise PermissionError("Only Coordinators can view extractions")

    # --- View Reports ---
    def can_view_reports(self, viewer: Employee) -> bool:
        return viewer.role == Role.COORDINATOR

    def require_can_view_reports(self, viewer: Employee) -> None:
        if not self.can_view_reports(viewer):
            raise PermissionError("Only Coordinators can view reports")


# Singleton authorizer instance
authorizer = Authorizer()
