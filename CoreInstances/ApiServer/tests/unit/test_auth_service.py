"""
Unit tests for authentication service session and credential checks.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

import src.auth.service as auth_service_module
from src.auth.schemas import TokenPair, TokenPayload
from src.auth.service import AuthService
from src.shared.models import Employee, Role


def _employee(
    *,
    employee_id: int = 1,
    token_version: int = 1,
    last_logout_at: datetime | None = None,
    is_active: bool = True,
    password_hash: str | None = "hash",
    role: Role = Role.COORDINATOR,
) -> Employee:
    return Employee(
        id=employee_id,
        employee_number=f"E{employee_id:05d}",
        first_name="Test",
        last_name="User",
        email=f"user{employee_id}@ci.laredo.tx.us",
        role=role,
        password_hash=password_hash,
        is_active=is_active,
        token_version=token_version,
        last_logout_at=last_logout_at,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _refresh_payload(
    *,
    employee_id: int = 1,
    token_version: int = 1,
    iat: datetime | None = None,
    session_created_at: datetime | None = None,
) -> TokenPayload:
    now = datetime.now(timezone.utc)
    return TokenPayload(
        sub=str(employee_id),
        email=f"user{employee_id}@ci.laredo.tx.us",
        role=Role.COORDINATOR.value,
        type="refresh",
        exp=now + timedelta(hours=1),
        iat=iat or now,
        token_version=token_version,
        session_created_at=session_created_at,
    )


@pytest.mark.asyncio
async def test_refresh_tokens_rejects_token_version_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = AsyncMock()
    service = AuthService(repo)

    payload = _refresh_payload(token_version=1)
    repo.get_employee_by_id = AsyncMock(return_value=_employee(token_version=2))
    monkeypatch.setattr(auth_service_module, "decode_token", lambda _: payload)
    monkeypatch.setattr(auth_service_module, "is_token_expired", lambda _: False)

    tokens, error = await service.refresh_tokens("token")

    assert tokens is None
    assert error == "Session invalidated"


@pytest.mark.asyncio
async def test_refresh_tokens_rejects_token_issued_before_logout(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = AsyncMock()
    service = AuthService(repo)

    logout_time = datetime.now(timezone.utc)
    payload = _refresh_payload(iat=logout_time)
    repo.get_employee_by_id = AsyncMock(
        return_value=_employee(token_version=1, last_logout_at=logout_time)
    )
    monkeypatch.setattr(auth_service_module, "decode_token", lambda _: payload)
    monkeypatch.setattr(auth_service_module, "is_token_expired", lambda _: False)

    tokens, error = await service.refresh_tokens("token")

    assert tokens is None
    assert error == "Session invalidated"


@pytest.mark.asyncio
async def test_refresh_tokens_rejects_session_over_max_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = AsyncMock()
    service = AuthService(repo)

    session_started = datetime.now(timezone.utc) - timedelta(hours=3)
    payload = _refresh_payload(session_created_at=session_started)
    repo.get_employee_by_id = AsyncMock(return_value=_employee(token_version=1))
    monkeypatch.setattr(auth_service_module, "decode_token", lambda _: payload)
    monkeypatch.setattr(auth_service_module, "is_token_expired", lambda _: False)
    monkeypatch.setattr(auth_service_module.auth_settings, "SESSION_MAX_HOURS", 1)

    tokens, error = await service.refresh_tokens("token")

    assert tokens is None
    assert error == "Session expired"


@pytest.mark.asyncio
async def test_refresh_tokens_forwards_original_session_created_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = AsyncMock()
    service = AuthService(repo)

    session_started = datetime.now(timezone.utc) - timedelta(minutes=15)
    payload = _refresh_payload(session_created_at=session_started)
    employee = _employee(token_version=1)
    repo.get_employee_by_id = AsyncMock(return_value=employee)
    monkeypatch.setattr(auth_service_module, "decode_token", lambda _: payload)
    monkeypatch.setattr(auth_service_module, "is_token_expired", lambda _: False)

    expected = TokenPair(
        access_token="access",
        refresh_token="refresh",
        token_type="Bearer",
        expires_in=1800,
    )
    create_tokens_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(service, "create_tokens", create_tokens_mock)

    tokens, error = await service.refresh_tokens("token")

    assert error is None
    assert tokens == expected
    create_tokens_mock.assert_awaited_once_with(
        employee,
        session_created_at=session_started,
    )


@pytest.mark.asyncio
async def test_authenticate_missing_user_uses_dummy_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = AsyncMock()
    repo.get_employee_by_email = AsyncMock(return_value=None)
    service = AuthService(repo)

    dummy_verify = Mock()
    monkeypatch.setattr(auth_service_module, "verify_password_dummy", dummy_verify)

    employee, error = await service.authenticate("nobody@ci.laredo.tx.us", "irrelevant")

    assert employee is None
    assert error == "Invalid email or password"
    dummy_verify.assert_called_once()


@pytest.mark.asyncio
async def test_authenticate_upgrades_legacy_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = AsyncMock()
    employee = _employee(password_hash="legacy-hash")
    repo.get_employee_by_email = AsyncMock(return_value=employee)
    repo.update_password_hash_only = AsyncMock()
    service = AuthService(repo)

    monkeypatch.setattr(auth_service_module, "verify_password", lambda plain, hashed: (True, "argon2-hash"))

    authenticated, error = await service.authenticate(employee.email, "correct-password")

    assert error is None
    assert authenticated == employee
    repo.update_password_hash_only.assert_awaited_once_with(employee.id, "argon2-hash")


# =============================================================================
# CRIT-01: forgot_password() with NULL hash
# =============================================================================


@pytest.mark.asyncio
async def test_forgot_password_sends_setup_email_for_null_hash_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NULL-hash coordinator account receives setup email, not reset email."""
    repo = AsyncMock()
    employee = _employee(password_hash=None, role=Role.COORDINATOR)
    repo.get_employee_by_email = AsyncMock(return_value=employee)
    repo.create_password_reset_token = AsyncMock()
    service = AuthService(repo)

    send_email_mock = AsyncMock()
    monkeypatch.setattr(auth_service_module, "_send_email", send_email_mock)
    monkeypatch.setattr(auth_service_module, "_os", Mock(urandom=lambda n: b"\xab" * n))

    await service.forgot_password(employee.email)

    send_email_mock.assert_awaited_once()
    call_kwargs = send_email_mock.call_args[1]
    assert "Set Up" in call_kwargs["subject"]


@pytest.mark.asyncio
async def test_forgot_password_sends_reset_email_for_existing_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Account with existing hash receives standard reset wording."""
    repo = AsyncMock()
    employee = _employee(password_hash="argon2-hash", role=Role.ADMIN)
    repo.get_employee_by_email = AsyncMock(return_value=employee)
    repo.create_password_reset_token = AsyncMock()
    service = AuthService(repo)

    send_email_mock = AsyncMock()
    monkeypatch.setattr(auth_service_module, "_send_email", send_email_mock)
    monkeypatch.setattr(auth_service_module, "_os", Mock(urandom=lambda n: b"\xab" * n))

    await service.forgot_password(employee.email)

    send_email_mock.assert_awaited_once()
    call_kwargs = send_email_mock.call_args[1]
    assert call_kwargs["subject"] == "Password Reset Request"


@pytest.mark.asyncio
async def test_forgot_password_silent_return_for_nonexistent_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-existent email returns None without sending email (anti-enumeration)."""
    repo = AsyncMock()
    repo.get_employee_by_email = AsyncMock(return_value=None)
    service = AuthService(repo)

    send_email_mock = AsyncMock()
    monkeypatch.setattr(auth_service_module, "_send_email", send_email_mock)

    result = await service.forgot_password("nobody@ci.laredo.tx.us")

    assert result is None
    send_email_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_forgot_password_silent_return_for_inactive_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inactive account returns None without sending email."""
    repo = AsyncMock()
    employee = _employee(is_active=False, password_hash=None)
    repo.get_employee_by_email = AsyncMock(return_value=employee)
    service = AuthService(repo)

    send_email_mock = AsyncMock()
    monkeypatch.setattr(auth_service_module, "_send_email", send_email_mock)

    result = await service.forgot_password(employee.email)

    assert result is None
    send_email_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_forgot_password_silent_return_for_employee_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Employee-role account returns None (INV-06 guard)."""
    repo = AsyncMock()
    employee = _employee(role=Role.EMPLOYEE, password_hash=None)
    repo.get_employee_by_email = AsyncMock(return_value=employee)
    service = AuthService(repo)

    send_email_mock = AsyncMock()
    monkeypatch.setattr(auth_service_module, "_send_email", send_email_mock)

    result = await service.forgot_password(employee.email)

    assert result is None
    send_email_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_forgot_password_invalidates_pending_tokens_before_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pending tokens are invalidated before creating a new one (MED-27)."""
    repo = AsyncMock()
    employee = _employee(password_hash="hash", role=Role.COORDINATOR)
    repo.get_employee_by_email = AsyncMock(return_value=employee)
    repo.create_password_reset_token = AsyncMock()
    # session.execute is needed for _invalidate_pending_reset_tokens
    repo.session = AsyncMock()
    service = AuthService(repo)

    send_email_mock = AsyncMock()
    monkeypatch.setattr(auth_service_module, "_send_email", send_email_mock)
    monkeypatch.setattr(auth_service_module, "_os", Mock(urandom=lambda n: b"\xab" * n))

    call_order = []
    original_invalidate = service._invalidate_pending_reset_tokens

    async def track_invalidate(eid):
        call_order.append("invalidate")
        await original_invalidate(eid)

    async def track_create(*args, **kwargs):
        call_order.append("create")

    monkeypatch.setattr(service, "_invalidate_pending_reset_tokens", track_invalidate)
    repo.create_password_reset_token = track_create

    await service.forgot_password(employee.email)

    assert call_order == ["invalidate", "create"]


# =============================================================================
# CRIT-01: authenticate() with NULL hash
# =============================================================================


@pytest.mark.asyncio
async def test_authenticate_rejects_null_password_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NULL password_hash returns generic error with timing equalization."""
    repo = AsyncMock()
    employee = _employee(password_hash=None)
    repo.get_employee_by_email = AsyncMock(return_value=employee)
    service = AuthService(repo)

    dummy_verify = Mock()
    monkeypatch.setattr(auth_service_module, "verify_password_dummy", dummy_verify)

    result, error = await service.authenticate(employee.email, "anything")

    assert result is None
    assert error == "Invalid email or password"
    dummy_verify.assert_called_once()


@pytest.mark.asyncio
async def test_authenticate_rejects_empty_string_password_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty string password_hash (falsy but not None) returns generic error."""
    repo = AsyncMock()
    employee = _employee(password_hash="")
    repo.get_employee_by_email = AsyncMock(return_value=employee)
    service = AuthService(repo)

    dummy_verify = Mock()
    monkeypatch.setattr(auth_service_module, "verify_password_dummy", dummy_verify)

    result, error = await service.authenticate(employee.email, "anything")

    assert result is None
    assert error == "Invalid email or password"
    dummy_verify.assert_called_once()


@pytest.mark.asyncio
async def test_login_with_old_hardcoded_password_fails_after_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin with NULL hash (post-migration) rejects Admin123!."""
    repo = AsyncMock()
    employee = _employee(password_hash=None, role=Role.ADMIN)
    employee.email = "admin@ci.laredo.tx.us"
    repo.get_employee_by_email = AsyncMock(return_value=employee)
    service = AuthService(repo)

    dummy_verify = Mock()
    monkeypatch.setattr(auth_service_module, "verify_password_dummy", dummy_verify)

    result, error = await service.authenticate("admin@ci.laredo.tx.us", "Admin123!")

    assert result is None
    assert error == "Invalid email or password"


# =============================================================================
# CRIT-01: reset_password() for NULL-hash accounts
# =============================================================================


@pytest.mark.asyncio
async def test_reset_password_works_for_null_hash_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reset_password() sets a new hash even when current hash is NULL."""
    repo = AsyncMock()
    token_record = Mock()
    token_record.id = 42
    token_record.employee_id = 1
    token_record.used_at = None
    token_record.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    repo.get_password_reset_token_by_hash = AsyncMock(return_value=token_record)
    repo.claim_password_reset_token = AsyncMock(return_value=True)
    repo.update_employee_password = AsyncMock()
    repo.update_employee_last_logout_at = AsyncMock()
    repo.create_audit_log = AsyncMock()
    service = AuthService(repo)

    monkeypatch.setattr(auth_service_module, "hash_password", lambda pw: "new-argon2-hash")

    success, error = await service.reset_password("raw-token", "SecurePassword123!@#")

    assert success is True
    assert error is None
    repo.update_employee_password.assert_awaited_once_with(1, "new-argon2-hash")
    repo.update_employee_last_logout_at.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_account_setup_email_works_without_existing_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_account_setup_email() works for employees with NULL password_hash."""
    repo = AsyncMock()
    repo.create_password_reset_token = AsyncMock()
    repo.session = AsyncMock()
    service = AuthService(repo)

    send_email_mock = AsyncMock()
    monkeypatch.setattr(auth_service_module, "_send_email", send_email_mock)
    monkeypatch.setattr(auth_service_module, "_os", Mock(urandom=lambda n: b"\xab" * n))

    await service.send_account_setup_email(1, "test@ci.laredo.tx.us", "Test")

    send_email_mock.assert_awaited_once()
    call_kwargs = send_email_mock.call_args[1]
    assert "Welcome" in call_kwargs["subject"]
    assert "/reset-password#token=" in call_kwargs["body"]
    assert "/reset-password?token=" not in call_kwargs["body"]
    repo.create_password_reset_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_account_setup_email_reports_delivery_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = AsyncMock()
    repo.create_password_reset_token = AsyncMock()
    repo.session = AsyncMock()
    service = AuthService(repo)
    monkeypatch.setattr(auth_service_module, "_send_email", AsyncMock(return_value=False))

    with pytest.raises(RuntimeError, match="delivery failed"):
        await service.send_account_setup_email(
            1,
            "test@ci.laredo.tx.us",
            "Test",
        )


# =============================================================================
# CRIT-01: Security regression guards
# =============================================================================


def test_no_hardcoded_password_in_migration_003() -> None:
    """Migration 003 must not contain the hardcoded Admin123! hash."""
    import pathlib

    # Resolve relative to this test file's location
    test_dir = pathlib.Path(__file__).resolve().parent
    repo_root = test_dir.parent.parent  # tests/unit -> tests -> ApiServer
    migration_path = repo_root / "alembic" / "versions" / "003_add_password_hash.py"
    content = migration_path.read_text()
    assert "Admin123" not in content
    assert "$2b$12$mqmN5b4He23" not in content


def test_no_hardcoded_password_in_readme() -> None:
    """README must not contain the hardcoded Admin123! password."""
    import pathlib

    test_dir = pathlib.Path(__file__).resolve().parent
    # Navigate up to project root: tests/unit -> tests -> ApiServer -> CoreInstances -> project
    repo_root = test_dir.parent.parent.parent.parent
    readme_path = repo_root / "README.md"
    if readme_path.exists():
        content = readme_path.read_text()
        assert "Admin123" not in content


# =============================================================================
# CRIT-01: Edge cases
# =============================================================================


@pytest.mark.asyncio
async def test_concurrent_reset_token_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second reset_password() call with same token fails."""
    repo = AsyncMock()
    token_record = Mock()
    token_record.id = 42
    token_record.employee_id = 1
    token_record.used_at = None
    token_record.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    repo.get_password_reset_token_by_hash = AsyncMock(return_value=token_record)
    # First claim succeeds, second fails
    repo.claim_password_reset_token = AsyncMock(side_effect=[True, False])
    repo.update_employee_password = AsyncMock()
    repo.update_employee_last_logout_at = AsyncMock()
    repo.create_audit_log = AsyncMock()
    service = AuthService(repo)

    monkeypatch.setattr(auth_service_module, "hash_password", lambda pw: "new-hash")

    success1, error1 = await service.reset_password("raw-token", "SecurePassword123!@#")
    assert success1 is True
    assert error1 is None

    success2, error2 = await service.reset_password("raw-token", "SecurePassword123!@#")
    assert success2 is False
    assert error2 == "Invalid or expired reset token"


@pytest.mark.asyncio
async def test_expired_reset_token_rejected() -> None:
    """Expired reset token returns failure."""
    repo = AsyncMock()
    token_record = Mock()
    token_record.id = 42
    token_record.employee_id = 1
    token_record.used_at = None
    token_record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

    repo.get_password_reset_token_by_hash = AsyncMock(return_value=token_record)
    service = AuthService(repo)

    success, error = await service.reset_password("raw-token", "SecurePassword123!@#")

    assert success is False
    assert error == "Invalid or expired reset token"


def test_admin123_rejected_by_password_policy() -> None:
    """Admin123! is too short (9 chars) for the 15-char minimum password policy."""
    from pydantic import ValidationError

    from src.auth.schemas import ResetPasswordRequest

    with pytest.raises(ValidationError):
        ResetPasswordRequest(token="x", new_password="Admin123!")


@pytest.mark.asyncio
async def test_forgot_password_smtp_failure_returns_none_not_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SMTP failure is suppressed — forgot_password() returns None, not 500."""
    repo = AsyncMock()
    employee = _employee(password_hash="hash", role=Role.COORDINATOR)
    repo.get_employee_by_email = AsyncMock(return_value=employee)
    repo.create_password_reset_token = AsyncMock()
    repo.session = AsyncMock()
    service = AuthService(repo)

    send_email_mock = AsyncMock(side_effect=Exception("SMTP connection refused"))
    monkeypatch.setattr(auth_service_module, "_send_email", send_email_mock)
    monkeypatch.setattr(auth_service_module, "_os", Mock(urandom=lambda n: b"\xab" * n))

    # Must not raise
    result = await service.forgot_password(employee.email)

    assert result is None
    # Token was still created before the email send attempt
    repo.create_password_reset_token.assert_awaited_once()
