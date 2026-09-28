"""
Unit tests for SqlRepository.list_all_requirements limit override.

The default behavior caps at _UNBOUNDED_QUERY_CAP (10_000) as a safety
fence. Exports (CSV/XLSX) and the dashboard counter feed must pass
``limit=None`` to bypass the cap so the user does not see silently
truncated data — a pre-fix bug where 12,226 rows in dev were exported
as 10,000 with no warning.

These tests pin the public contract: default = capped, ``limit=None`` = no
limit clause, integer = explicit limit clause.
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

    await repo.list_all_requirements()

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

    await repo.list_all_requirements(limit=None)

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

    await repo.list_all_requirements(limit=42)

    call_args = session.execute.call_args
    stmt = call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT 42" in compiled
