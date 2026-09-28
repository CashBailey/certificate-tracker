"""
Unit tests for SqlRepository.list_all_extractions limit override.

Same contract as list_all_requirements: default applies the 10,000-row
safety cap, ``limit=None`` bypasses it (for callers that compute aggregate
state from the full table), explicit integer respected.

Mirrors test_repository_list_all_requirements_cap.py.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.shared.repository import SqlRepository, _UNBOUNDED_QUERY_CAP


@pytest.mark.asyncio
async def test_default_applies_safety_cap():
    """Default call (no kwarg) builds a SELECT with .limit(_UNBOUNDED_QUERY_CAP)."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: iter([])))
    repo = SqlRepository(session)

    await repo.list_all_extractions()

    call_args = session.execute.call_args
    stmt = call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert f"LIMIT {_UNBOUNDED_QUERY_CAP}" in compiled


@pytest.mark.asyncio
async def test_limit_none_bypasses_cap():
    """``limit=None`` builds a SELECT WITHOUT any LIMIT clause."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: iter([])))
    repo = SqlRepository(session)

    await repo.list_all_extractions(limit=None)

    call_args = session.execute.call_args
    stmt = call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT" not in compiled.upper()


@pytest.mark.asyncio
async def test_explicit_limit_used_verbatim():
    """An integer limit is passed straight to the SELECT."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: iter([])))
    repo = SqlRepository(session)

    await repo.list_all_extractions(limit=42)

    call_args = session.execute.call_args
    stmt = call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT 42" in compiled
