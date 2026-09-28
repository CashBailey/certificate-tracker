"""Regression tests for reliable browser-session cookie clearing."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.requests import Request

from src.auth.router import clear_session_cookie, logout
from src.shared.models import Employee, Role


def _cookie_params():
    return {
        "key": "laredo_refresh",
        "httponly": True,
        "secure": True,
        "samesite": "strict",
        "path": "/",
        "max_age": 604_800,
        "domain": None,
    }


@pytest.mark.asyncio
async def test_clear_session_expires_http_only_refresh_cookie_without_authentication():
    service = Mock()
    service.build_refresh_cookie_params.return_value = _cookie_params()

    response = await clear_session_cookie(service)

    cookie = response.headers["set-cookie"]
    assert "laredo_refresh=" in cookie
    assert "Max-Age=0" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie


@pytest.mark.asyncio
async def test_logout_db_failure_still_expires_refresh_cookie():
    now = datetime.now(timezone.utc)
    employee = Employee(
        id=1,
        employee_number="C00001",
        first_name="Test",
        last_name="Coordinator",
        email="coordinator@ci.laredo.tx.us",
        role=Role.COORDINATOR,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    service = Mock()
    service.record_logout = AsyncMock(side_effect=RuntimeError("database unavailable"))
    service.log_auth_event = AsyncMock()
    service.build_refresh_cookie_params.return_value = _cookie_params()
    request = Request({"type": "http", "method": "POST", "path": "/auth/logout"})

    response = await logout(request, employee, service)

    assert response.status_code == 503
    assert "Max-Age=0" in response.headers["set-cookie"]
    service.log_auth_event.assert_not_awaited()
