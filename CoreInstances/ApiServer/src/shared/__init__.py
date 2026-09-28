"""
Shared models, protocols, and utilities for the Certificate Management System.

Import directly from specific modules for better code clarity:
- from src.shared.models import Employee, CertificateDocument, ...
- from src.shared.protocols import Repository, Storage, ...
- from src.shared.utils import sanitize_filename, ...
"""

from .clock import RealClock
from .uuid_gen import RealUuidGenerator

__all__ = [
    "RealClock",
    "RealUuidGenerator",
]
