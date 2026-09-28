"""Extraction workers must not overwrite reviewed or concurrent results."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.shared.models import ReviewState
from src.shared.orm_models import ExtractionRunORM
from src.shared.repository import SqlRepository


def _update_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_stale_result_is_rejected_by_single_guarded_update():
    session = AsyncMock()
    session.execute.return_value = _update_result(None)
    repo = SqlRepository(session)

    updated = await repo.update_extraction_results(
        extraction_id=12,
        extracted_fields={"certificate_type": {"value": "CPR"}},
        needs_review=False,
        needs_review_reasons=[],
        expected_state=ReviewState.PROCESSING,
        expected_version=3,
        new_state=ReviewState.PENDING_REVIEW,
    )

    assert updated is None
    session.execute.assert_awaited_once()
    session.flush.assert_not_awaited()
    sql = str(session.execute.await_args.args[0])
    assert "review_state" in sql
    assert "review_state_version" in sql


@pytest.mark.asyncio
async def test_successful_result_advances_version_and_returns_new_state():
    session = AsyncMock()
    update_result = _update_result(12)
    stored = ExtractionRunORM(
        id=12,
        document_id=21,
        review_state=ReviewState.PENDING_REVIEW.value,
        review_state_version=4,
        extracted_fields={"certificate_type": {"value": "CPR"}},
        needs_review=False,
        needs_review_reasons=[],
    )
    select_result = MagicMock()
    select_result.scalar_one.return_value = stored
    session.execute.side_effect = [update_result, select_result]
    repo = SqlRepository(session)

    updated = await repo.update_extraction_results(
        extraction_id=12,
        extracted_fields=stored.extracted_fields,
        needs_review=False,
        needs_review_reasons=[],
        expected_state=ReviewState.PROCESSING,
        expected_version=3,
        new_state=ReviewState.PENDING_REVIEW,
    )

    assert updated is not None
    assert updated.review_state is ReviewState.PENDING_REVIEW
    assert updated.review_state_version == 4
    session.flush.assert_awaited_once()
