"""
Domain-specific repository modules for the City of Laredo Certificate Management System.

This package provides focused repository classes that can be used instead of
the monolithic SqlRepository. The SqlRepository class remains available for
backward compatibility but new code should prefer the domain-specific repositories.

Usage:
    from src.shared.repositories import EmployeeRepository, DocumentRepository

    async def get_user(session: AsyncSession):
        repo = EmployeeRepository(session)
        return await repo.get_by_id(user_id)

    async def get_document(session: AsyncSession, doc_id: int):
        repo = DocumentRepository(session)
        return await repo.get_by_id(doc_id)
"""

from .base import BaseRepository
from .document import DocumentRepository
from .employee import EmployeeRepository
from .extraction import ExtractionRepository

__all__ = [
    "BaseRepository",
    "DocumentRepository",
    "EmployeeRepository",
    "ExtractionRepository",
]
