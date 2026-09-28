"""
Unit tests for Repository.find_open_requirement_by_cert_type fuzzy matching.

The function tries an exact name match first, then falls back to a
case-insensitive substring (LIKE) match. The ambiguity contract is the
critical behavior: when the fuzzy fallback returns 2+ candidates the
function MUST return None (fail-stop) so a Coordinator must explicitly
link via request.requirement_id rather than risking auto-link to the
wrong requirement (e.g. "First Aid - Basic" vs "First Aid - Advanced").
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.shared.repository import SqlRepository


def _make_session_with_results(*results: MagicMock) -> AsyncMock:
    """Build an AsyncMock session whose .execute() yields the given Result mocks
    in order."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=list(results))
    return session


def _exact_result(rid: int | None) -> MagicMock:
    """Result returned by the exact-match query: scalar_one_or_none() -> rid."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = rid
    return result


def _fuzzy_result(rids: list[int]) -> MagicMock:
    """Result returned by the fuzzy-match query: scalars().all() -> [rid, ...]."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rids
    result.scalars.return_value = scalars
    return result


@pytest.mark.asyncio
async def test_exact_match_returns_id() -> None:
    """Exact name match short-circuits and returns the requirement id without
    issuing the fuzzy fallback query."""
    session = _make_session_with_results(_exact_result(42))
    repo = SqlRepository(session)

    rid = await repo.find_open_requirement_by_cert_type(
        employee_id=1, certificate_type_name="First Aid - Basic"
    )

    assert rid == 42
    # Exact-match path must not issue the fuzzy fallback.
    assert session.execute.call_count == 1


@pytest.mark.asyncio
async def test_no_match_returns_none() -> None:
    """When neither exact nor fuzzy queries find anything, return None."""
    session = _make_session_with_results(
        _exact_result(None),
        _fuzzy_result([]),
    )
    repo = SqlRepository(session)

    rid = await repo.find_open_requirement_by_cert_type(
        employee_id=1, certificate_type_name="Nonexistent Certificate"
    )

    assert rid is None
    # Both exact and fuzzy were attempted.
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_single_fuzzy_match_returns_id() -> None:
    """Substring match with exactly one open requirement returns its id."""
    session = _make_session_with_results(
        _exact_result(None),
        _fuzzy_result([99]),
    )
    repo = SqlRepository(session)

    rid = await repo.find_open_requirement_by_cert_type(
        employee_id=1, certificate_type_name="HIPAA"
    )

    assert rid == 99


@pytest.mark.asyncio
async def test_ambiguous_fuzzy_match_returns_none() -> None:
    """KEY contract: when the substring matches 2+ open requirements the
    function returns None (fail-stop) so the Coordinator must explicitly
    pick the right requirement via request.requirement_id.

    Scenario: employee has both "First Aid - Basic" and "First Aid - Advanced"
    open. Searching for "First Aid" matches both; auto-linking would risk
    silently satisfying the wrong requirement.
    """
    session = _make_session_with_results(
        _exact_result(None),
        _fuzzy_result([101, 102]),  # both "First Aid - Basic" and "Advanced"
    )
    repo = SqlRepository(session)

    rid = await repo.find_open_requirement_by_cert_type(
        employee_id=1, certificate_type_name="First Aid"
    )

    assert rid is None, (
        "Ambiguous fuzzy match must return None — auto-linking the wrong "
        "requirement is worse than forcing manual disambiguation."
    )
