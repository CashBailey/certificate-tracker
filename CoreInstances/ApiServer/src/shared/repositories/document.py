"""
Document repository for the City of Laredo Certificate Management System.

Handles all document-related database operations.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update, delete, and_

from ..models import CertificateDocument, DeletionTombstone, IntakeChannel
from ..orm_models import CertificateDocumentORM, DeletionTombstoneORM
from .base import BaseRepository


class DocumentRepository(BaseRepository):
    """Repository for CertificateDocument domain operations."""

    async def create(self, document: CertificateDocument) -> CertificateDocument:
        """Create a new document record."""
        orm_obj = CertificateDocumentORM(
            employee_id=document.employee_id,
            storage_key=document.storage_key,
            file_name=document.file_name,
            file_type=document.file_type,
            file_size_bytes=document.file_size_bytes,
            uploaded_by_id=document.uploaded_by_id,
            acting_as=document.acting_as,
            intake_channel=document.intake_channel.value,
            source_email_message_id=document.source_email_message_id,
            target_requirement_id=document.target_requirement_id,
            file_hash=document.file_hash,
        )
        self.session.add(orm_obj)
        await self.flush()
        await self.refresh(orm_obj)
        return self._to_model(orm_obj)

    async def get_by_id(self, document_id: int) -> Optional[CertificateDocument]:
        """Get non-deleted document by ID."""
        stmt = select(CertificateDocumentORM).where(
            and_(
                CertificateDocumentORM.id == document_id,
                CertificateDocumentORM.deleted_at == None,
            )
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._to_model(orm_obj) if orm_obj else None

    async def get_by_employee_and_hash(
        self,
        employee_id: int,
        file_hash: str,
    ) -> Optional[CertificateDocument]:
        """
        Find existing document by employee and file hash for deduplication.

        Only returns non-deleted documents.

        Args:
            employee_id: Employee ID
            file_hash: SHA-256 hash of file content

        Returns:
            Existing document if found, None otherwise
        """
        stmt = select(CertificateDocumentORM).where(
            and_(
                CertificateDocumentORM.employee_id == employee_id,
                CertificateDocumentORM.file_hash == file_hash,
                CertificateDocumentORM.deleted_at == None,
            )
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._to_model(orm_obj) if orm_obj else None

    async def list_for_employee(self, employee_id: int) -> list[CertificateDocument]:
        """List non-deleted documents for an employee."""
        stmt = (
            select(CertificateDocumentORM)
            .where(
                and_(
                    CertificateDocumentORM.employee_id == employee_id,
                    CertificateDocumentORM.deleted_at == None,
                )
            )
            .order_by(CertificateDocumentORM.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._to_model(orm_obj) for orm_obj in result.scalars()]

    async def soft_delete(
        self,
        document_id: int,
        retention_days: int = 90,
    ) -> bool:
        """
        Soft delete a document by setting deleted_at timestamp.

        Will fail if the document is under legal hold.

        Args:
            document_id: ID of the document to delete
            retention_days: Days to retain the document before hard delete

        Returns:
            True if document was soft deleted, False if under legal hold or not found

        Raises:
            ValueError: If document is under legal hold
        """
        stmt = select(CertificateDocumentORM).where(
            CertificateDocumentORM.id == document_id
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            return False

        if doc.legal_hold:
            raise ValueError(
                f"Document {document_id} is under legal hold and cannot be deleted"
            )

        if doc.deleted_at is not None:
            return False  # Already deleted

        retention_expires = datetime.now(timezone.utc) + timedelta(days=retention_days)

        stmt = (
            update(CertificateDocumentORM)
            .where(
                and_(
                    CertificateDocumentORM.id == document_id,
                    CertificateDocumentORM.legal_hold == False,
                    CertificateDocumentORM.deleted_at == None,
                )
            )
            .values(
                deleted_at=datetime.now(timezone.utc),
                retention_expires_at=retention_expires,
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1

    async def set_legal_hold(self, document_id: int, hold: bool) -> bool:
        """
        Set or remove legal hold on a document.

        Args:
            document_id: ID of the document
            hold: True to set legal hold, False to remove

        Returns:
            True if the hold status was updated, False if document not found
        """
        stmt = (
            update(CertificateDocumentORM)
            .where(CertificateDocumentORM.id == document_id)
            .values(legal_hold=hold)
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1

    async def list_for_retention_purge(
        self,
        cutoff_date: datetime,
        limit: int = 100,
    ) -> list[CertificateDocument]:
        """
        List soft-deleted documents past their retention period for hard deletion.

        Only returns documents that:
        - Have been soft deleted (deleted_at is set)
        - Are past their retention expiration date
        - Are NOT under legal hold

        Args:
            cutoff_date: Purge documents with retention_expires_at before this date
            limit: Maximum number of documents to return

        Returns:
            List of documents eligible for hard deletion
        """
        stmt = (
            select(CertificateDocumentORM)
            .where(
                and_(
                    CertificateDocumentORM.deleted_at != None,
                    CertificateDocumentORM.retention_expires_at != None,
                    CertificateDocumentORM.retention_expires_at <= cutoff_date,
                    CertificateDocumentORM.legal_hold == False,
                )
            )
            .order_by(CertificateDocumentORM.retention_expires_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [self._to_model(orm_obj) for orm_obj in result.scalars()]

    async def hard_delete(
        self,
        document_id: int,
        deleted_by_id: Optional[int] = None,
        deletion_reason: Optional[str] = None,
    ) -> Optional[DeletionTombstone]:
        """
        Hard delete a document and create a tombstone record.

        Only works for documents that:
        - Have been soft deleted
        - Are NOT under legal hold

        Args:
            document_id: ID of the document to delete
            deleted_by_id: ID of employee performing deletion
            deletion_reason: Reason for deletion

        Returns:
            Tombstone record if deleted, None if document not found or not eligible
        """
        stmt = select(CertificateDocumentORM).where(
            and_(
                CertificateDocumentORM.id == document_id,
                CertificateDocumentORM.deleted_at != None,
                CertificateDocumentORM.legal_hold == False,
            )
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        # Capture metadata for tombstone
        metadata = {
            "employee_id": doc.employee_id,
            "storage_key": doc.storage_key,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "file_size_bytes": doc.file_size_bytes,
            "uploaded_by_id": doc.uploaded_by_id,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "deleted_at": doc.deleted_at.isoformat() if doc.deleted_at else None,
        }

        # Create tombstone
        tombstone_orm = DeletionTombstoneORM(
            entity_type="document",
            entity_id=document_id,
            deleted_by_id=deleted_by_id,
            deletion_reason=deletion_reason,
            entity_metadata=metadata,
        )
        self.session.add(tombstone_orm)
        await self.flush()
        await self.refresh(tombstone_orm)

        # Hard delete the document
        stmt = delete(CertificateDocumentORM).where(
            CertificateDocumentORM.id == document_id
        )
        await self.session.execute(stmt)

        return DeletionTombstone(
            id=tombstone_orm.id,
            entity_type=tombstone_orm.entity_type,
            entity_id=tombstone_orm.entity_id,
            deleted_at=tombstone_orm.deleted_at,
            deleted_by_id=tombstone_orm.deleted_by_id,
            deletion_reason=tombstone_orm.deletion_reason,
            entity_metadata=tombstone_orm.entity_metadata,
        )

    def _to_model(self, orm_obj: CertificateDocumentORM) -> CertificateDocument:
        """Convert ORM object to domain model."""
        return CertificateDocument(
            id=orm_obj.id,
            employee_id=orm_obj.employee_id,
            storage_key=orm_obj.storage_key,
            file_name=orm_obj.file_name,
            file_type=orm_obj.file_type,
            file_size_bytes=orm_obj.file_size_bytes,
            uploaded_by_id=orm_obj.uploaded_by_id,
            acting_as=orm_obj.acting_as,
            intake_channel=IntakeChannel(orm_obj.intake_channel),
            source_email_message_id=orm_obj.source_email_message_id,
            target_requirement_id=orm_obj.target_requirement_id,
            file_hash=orm_obj.file_hash,
            created_at=orm_obj.created_at,
        )
