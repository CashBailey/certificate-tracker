"""
API routes for the City of Laredo Certificate Management System.
"""

from .admin import router as admin_router
from .alert_config import router as alert_config_router
from .audit_logs import router as audit_logs_router
from .certificate_types import router as certificate_types_router
from .documents import router as documents_router
from .employees import router as employees_router
from .extractions import router as extractions_router
from .notifications import router as notifications_router
from .reports import router as reports_router
from .requirements import router as requirements_router
from .templates import router as templates_router
from .verified_records import router as verified_records_router

__all__ = [
    "admin_router",
    "alert_config_router",
    "audit_logs_router",
    "certificate_types_router",
    "documents_router",
    "employees_router",
    "extractions_router",
    "notifications_router",
    "reports_router",
    "requirements_router",
    "templates_router",
    "verified_records_router",
]
