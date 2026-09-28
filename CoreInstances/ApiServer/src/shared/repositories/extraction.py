"""
Extraction repository for the City of Laredo Certificate Management System.

Handles all extraction-related database operations.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update, and_

from ..models import ExtractionRun, ReviewState
from ..orm_models import ExtractionRunORM
from .base import BaseRepository


class ExtractionRepository(BaseRepository):
    """Repository for ExtractionRun domain operations."""

    async def create(self, extraction: ExtractionRun) -> ExtractionRun:
        """Create a new extraction run."""
        orm_obj = ExtractionRunORM(
            document_id=extraction.document_id,
            review_state=extraction.review_state.value,
            extracted_fields=extraction.extracted_fields,
            needs_review=extraction.needs_review,
            needs_review_reasons=extraction.needs_review_reasons,
            template_id=extraction.template_id,
            template_version=extraction.template_version,
            template_match_evidence=extraction.template_match_evidence,
            review_assist=extraction.review_assist,
            field_evidence=extraction.field_evidence,
        )
        self.session.add(orm_obj)
        await self.flush()
        await self.refresh(orm_obj)
        return self._to_model(orm_obj)

    async def get_by_id(self, extraction_id: int) -> Optional[ExtractionRun]:
        """Get extraction by ID."""
        stmt = select(ExtractionRunORM).where(ExtractionRunORM.id == extraction_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._to_model(orm_obj) if orm_obj else None

    async def get_by_document_id(self, document_id: int) -> Optional[ExtractionRun]:
        """Get the most recent extraction for a document."""
        stmt = (
            select(ExtractionRunORM)
            .where(ExtractionRunORM.document_id == document_id)
            .order_by(ExtractionRunORM.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return self._to_model(orm_obj) if orm_obj else None

    async def update_results(
        self,
        extraction_id: int,
        extracted_fields: dict,
        needs_review: bool,
        needs_review_reasons: list[str],
        template_id: Optional[str] = None,
        template_version: Optional[int] = None,
        template_match_evidence: Optional[dict] = None,
        review_assist: Optional[dict] = None,
        field_evidence: Optional[dict] = None,
    ) -> Optional[ExtractionRun]:
        """Update extraction with pipeline results."""
        stmt = select(ExtractionRunORM).where(ExtractionRunORM.id == extraction_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()

        if not orm_obj:
            return None

        orm_obj.extracted_fields = extracted_fields
        orm_obj.needs_review = needs_review
        orm_obj.needs_review_reasons = needs_review_reasons
        orm_obj.template_id = template_id
        orm_obj.template_version = template_version
        orm_obj.template_match_evidence = template_match_evidence
        orm_obj.review_assist = review_assist
        orm_obj.field_evidence = field_evidence

        await self.flush()
        await self.refresh(orm_obj)
        return self._to_model(orm_obj)

    async def list_by_state(self, state: ReviewState) -> list[ExtractionRun]:
        """List extractions by review state."""
        stmt = (
            select(ExtractionRunORM)
            .where(ExtractionRunORM.review_state == state.value)
            .order_by(ExtractionRunORM.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._to_model(orm_obj) for orm_obj in result.scalars()]

    async def try_transition_review_state(
        self,
        extraction_id: int,
        expected_state: ReviewState,
        expected_version: int,
        new_state: ReviewState,
        reviewed_by_id: Optional[int] = None,
    ) -> bool:
        """
        Attempt to transition extraction review state with optimistic locking.

        Args:
            extraction_id: ID of the extraction
            expected_state: Current state expected for transition
            expected_version: Current version expected for optimistic lock
            new_state: Target state for transition
            reviewed_by_id: ID of the reviewer (optional)

        Returns:
            True if transition succeeded, False if version conflict
        """
        stmt = (
            update(ExtractionRunORM)
            .where(
                and_(
                    ExtractionRunORM.id == extraction_id,
                    ExtractionRunORM.review_state == expected_state.value,
                    ExtractionRunORM.review_state_version == expected_version,
                )
            )
            .values(
                review_state=new_state.value,
                review_state_version=expected_version + 1,
                reviewed_by_id=reviewed_by_id,
                reviewed_at=datetime.now(timezone.utc) if reviewed_by_id else None,
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1

    async def update_extracted_fields(
        self,
        extraction_id: int,
        extracted_fields: dict,
    ) -> Optional[ExtractionRun]:
        """
        Update only the extracted fields for an extraction.

        Args:
            extraction_id: ID of the extraction
            extracted_fields: New extracted fields data

        Returns:
            Updated extraction or None if not found
        """
        stmt = select(ExtractionRunORM).where(ExtractionRunORM.id == extraction_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()

        if not orm_obj:
            return None

        orm_obj.extracted_fields = extracted_fields
        await self.flush()
        await self.refresh(orm_obj)
        return self._to_model(orm_obj)

    def _to_model(self, orm_obj: ExtractionRunORM) -> ExtractionRun:
        """Convert ORM object to domain model."""
        return ExtractionRun(
            id=orm_obj.id,
            document_id=orm_obj.document_id,
            review_state=ReviewState(orm_obj.review_state),
            extracted_fields=orm_obj.extracted_fields,
            needs_review=orm_obj.needs_review,
            needs_review_reasons=orm_obj.needs_review_reasons,
            template_id=orm_obj.template_id,
            template_version=orm_obj.template_version,
            template_match_evidence=orm_obj.template_match_evidence,
            review_assist=orm_obj.review_assist,
            field_evidence=orm_obj.field_evidence,
            reviewed_by_id=orm_obj.reviewed_by_id,
            reviewed_at=orm_obj.reviewed_at,
            review_state_version=orm_obj.review_state_version,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at,
        )
