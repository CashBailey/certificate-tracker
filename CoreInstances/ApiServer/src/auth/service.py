"""
Authentication service with business logic.
"""

import hashlib
import logging
import os as _os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import update

from ..shared.email_sender import send_email as _send_email
from ..shared.audit import audit as _audit
from ..shared.models import Employee, Role
from ..shared.orm_models import PasswordResetTokenORM
from ..shared.repository import SqlRepository
from .config import auth_settings
from .schemas import TokenPair, UserResponse
from .security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    is_token_expired,
    verify_password,
    verify_password_dummy,
)

# Per-account lockout configuration
_LOCKOUT_MAX_FAILURES: int = 5
_LOCKOUT_TTL_SECONDS: int = 15 * 60  # 15 minutes


class AuthService:
    """Authentication service."""

    def __init__(self, repository: SqlRepository, redis=None):
        self.repository = repository
        self._redis = redis

    def _lockout_key(self, employee_id: int) -> str:
        """Redis key for per-account login failure counter."""
        return f"login_failures:{employee_id}"

    def _check_and_increment_failures(self, employee_id: int) -> bool:
        """
        Increment the per-account failure counter and return True if the account
        is now locked (>= _LOCKOUT_MAX_FAILURES failures within the TTL window).

        No-ops silently when Redis is unavailable so a Redis outage does not
        block all logins. The caller must still run verify_password_dummy() for
        timing equalization before returning if True is returned.
        """
        if self._redis is None:
            return False
        try:
            key = self._lockout_key(employee_id)
            count = self._redis.incr(key)
            if count == 1:
                # First failure: set the TTL so the window is bounded
                self._redis.expire(key, _LOCKOUT_TTL_SECONDS)
            return count >= _LOCKOUT_MAX_FAILURES
        except Exception:
            # Redis unavailable: fail open (do not lock out)
            return False

    def _is_locked_out(self, employee_id: int) -> bool:
        """Return True if the account currently has >= _LOCKOUT_MAX_FAILURES failures."""
        if self._redis is None:
            return False
        try:
            key = self._lockout_key(employee_id)
            raw = self._redis.get(key)
            if raw is None:
                return False
            return int(raw) >= _LOCKOUT_MAX_FAILURES
        except Exception:
            return False

    def _clear_failures(self, employee_id: int) -> None:
        """Delete the failure counter on successful login."""
        if self._redis is None:
            return
        try:
            self._redis.delete(self._lockout_key(employee_id))
        except Exception:
            pass

    async def _invalidate_pending_reset_tokens(self, employee_id: int) -> None:
        """
        Mark all unused, unexpired password reset tokens for an employee as used.

        Called before creating a new reset token so that at most one valid
        token exists at any time (MED-27).
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(PasswordResetTokenORM)
            .where(
                PasswordResetTokenORM.employee_id == employee_id,
                PasswordResetTokenORM.used_at.is_(None),
                PasswordResetTokenORM.expires_at > now,
            )
            .values(used_at=now)
        )
        await self.repository.session.execute(stmt)

    async def authenticate(
        self, email: str, password: str
    ) -> Tuple[Optional[Employee], Optional[str]]:
        """
        Authenticate user with email and password.

        Anti-enumeration: all non-credential failure paths call verify_password_dummy()
        to equalize timing. All failure cases return the same generic error message.

        Per-account lockout: after _LOCKOUT_MAX_FAILURES consecutive failures within
        the _LOCKOUT_TTL_SECONDS window the account is locked; the generic error message
        is returned without disclosing the lock. A successful login clears the counter.

        Returns:
            Tuple of (Employee, None) on success
            Tuple of (None, error_message) on failure
        """
        employee = await self.repository.get_employee_by_email(email)

        # Timing equalization + no account-existence disclosure for all pre-verify paths
        if not employee:
            verify_password_dummy()
            return None, "Invalid email or password"

        if not employee.is_active:
            verify_password_dummy()
            return None, "Invalid email or password"

        if not employee.password_hash:
            verify_password_dummy()
            return None, "Invalid email or password"

        # Employees do not have web access (INV-06) — same generic message
        if employee.role == Role.EMPLOYEE:
            verify_password_dummy()
            return None, "Invalid email or password"

        # Per-account lockout check (pre-verify, after employee is confirmed to exist)
        # Generic message — do not disclose that the account is locked.
        if self._is_locked_out(employee.id):
            verify_password_dummy()
            return None, "Invalid email or password"

        is_valid, new_hash = verify_password(password, employee.password_hash)
        if not is_valid:
            # Increment failure counter; lock if threshold reached
            self._check_and_increment_failures(employee.id)
            return None, "Invalid email or password"

        # Successful login — clear failure counter
        self._clear_failures(employee.id)

        # Transparent Argon2id upgrade for legacy bcrypt hashes (no token_version bump)
        if new_hash:
            await self.repository.update_password_hash_only(employee.id, new_hash)

        return employee, None

    def build_refresh_cookie_params(self) -> dict:
        """Return kwargs for Response.set_cookie().

        For delete_cookie(), strip 'max_age' from this dict.
        The path, domain, samesite, secure, and httponly flags MUST match
        between set_cookie() and delete_cookie() -- if any differ, the
        browser treats it as a different cookie and won't delete it.
        """
        return {
            "key": auth_settings.REFRESH_COOKIE_NAME,
            "httponly": True,
            "secure": auth_settings.COOKIE_SECURE,
            "samesite": auth_settings.COOKIE_SAMESITE,
            "path": auth_settings.REFRESH_COOKIE_PATH,
            "max_age": auth_settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            "domain": auth_settings.COOKIE_DOMAIN,
        }

    async def create_tokens(
        self,
        employee: Employee,
        session_created_at: Optional[datetime] = None,
    ) -> TokenPair:
        """Create access and refresh tokens for an employee."""
        access_token, _ = create_access_token(
            employee.id,
            employee.email,
            employee.role.value,
            employee.token_version,
        )

        refresh_token, _ = create_refresh_token(
            employee.id,
            employee.email,
            employee.role.value,
            employee.token_version,
            session_created_at=session_created_at,
        )

        expires_in = auth_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=expires_in,
        )

    async def refresh_tokens(
        self, refresh_token: str
    ) -> Tuple[Optional[TokenPair], Optional[str]]:
        """
        Refresh access token using refresh token.

        Enforces:
        - token_version check (password-change revocation)
        - last_logout_at check (explicit-logout revocation, SEC-09)
        - SESSION_MAX_HOURS check (wall-clock session limit, SEC-10)

        Returns:
            Tuple of (TokenPair, None) on success
            Tuple of (None, error_message) on failure
        """
        payload = decode_token(refresh_token)

        if not payload:
            return None, "Invalid refresh token"

        if payload.type != "refresh":
            return None, "Invalid token type"

        if is_token_expired(payload):
            return None, "Refresh token expired"

        employee = await self.repository.get_employee_by_id(int(payload.sub))

        if not employee:
            return None, "User not found"

        if not employee.is_active:
            return None, "Account is disabled"

        # Reject tokens issued before a password change
        if (
            payload.token_version is not None
            and payload.token_version != employee.token_version
        ):
            return None, "Session invalidated"

        # Reject tokens issued at or before last explicit logout (SEC-09)
        if employee.last_logout_at and payload.iat and payload.iat <= employee.last_logout_at:
            return None, "Session invalidated"

        # Enforce SESSION_MAX_HOURS wall-clock limit (SEC-10)
        if payload.session_created_at:
            now = datetime.now(timezone.utc)
            sess = payload.session_created_at
            if sess.tzinfo is None:
                sess = sess.replace(tzinfo=timezone.utc)
            elapsed_hours = (now - sess).total_seconds() / 3600
            if elapsed_hours > auth_settings.SESSION_MAX_HOURS:
                return None, "Session expired"

        # Forward session_created_at unchanged so SESSION_MAX_HOURS uses original start
        tokens = await self.create_tokens(
            employee, session_created_at=payload.session_created_at
        )

        return tokens, None

    async def get_user_from_token(
        self, token: str
    ) -> Tuple[Optional[Employee], Optional[str]]:
        """
        Get employee from access token.

        Enforces:
        - token_version check (password-change revocation)
        - last_logout_at check (explicit-logout revocation, AUD-02/AUD-32)

        Returns:
            Tuple of (Employee, None) on success
            Tuple of (None, error_message) on failure
        """
        payload = decode_token(token)

        if not payload:
            return None, "Invalid token"

        if payload.type != "access":
            return None, "Invalid token type"

        if is_token_expired(payload):
            return None, "Token expired"

        employee = await self.repository.get_employee_by_id(int(payload.sub))

        if not employee:
            return None, "User not found"

        if not employee.is_active:
            return None, "Account is disabled"

        # Reject tokens issued at or before last explicit logout (AUD-32)
        if employee.last_logout_at and payload.iat and payload.iat <= employee.last_logout_at:
            return None, "Session invalidated"

        # Reject tokens with stale version — password changed or forced logout (AUD-32)
        if (
            payload.token_version is not None
            and payload.token_version != employee.token_version
        ):
            return None, "Session invalidated"

        return employee, None

    async def change_password(
        self,
        employee: Employee,
        current_password: str,
        new_password: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Change user password.

        Returns:
            Tuple of (True, None) on success
            Tuple of (False, error_message) on failure
        """
        if not employee.password_hash:
            return False, "Account not configured for password change"

        is_valid, _ = verify_password(current_password, employee.password_hash)
        if not is_valid:
            return False, "Current password is incorrect"

        new_hash = hash_password(new_password)
        await self.repository.update_employee_password(employee.id, new_hash)

        return True, None

    async def record_logout(self, employee_id: int) -> None:
        """Record explicit logout to invalidate all current refresh tokens (SEC-09)."""
        await self.repository.update_employee_last_logout_at(
            employee_id, datetime.now(timezone.utc)
        )

    async def send_account_setup_email(
        self, employee_id: int, email: str, first_name: str
    ) -> None:
        """
        Send a welcome email with a one-time link for new employees to set their password.

        Unlike forgot_password(), this does NOT require a pre-existing password_hash.
        """
        # Invalidate any existing unused reset tokens before issuing a new one (MED-27)
        await self._invalidate_pending_reset_tokens(employee_id)

        raw_token = _os.urandom(32).hex()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=auth_settings.RESET_TOKEN_EXPIRE_MINUTES
        )

        await self.repository.create_password_reset_token(employee_id, token_hash, expires_at)

        # Fragments are not sent in HTTP requests or access logs. The SPA reads
        # and immediately removes this one-time bearer from the address bar.
        setup_url = f"{auth_settings.CANONICAL_ORIGIN}/reset-password#token={raw_token}"
        body = (
            f"Hello {first_name},\n\n"
            f"Your City of Laredo account has been created.\n\n"
            f"Click the link below to set your password and activate your account "
            f"(expires in {auth_settings.RESET_TOKEN_EXPIRE_MINUTES} minutes):\n\n"
            f"{setup_url}\n\n"
            f"If you did not expect this email, please contact your administrator."
        )

        sent = await _send_email(
            to=email,
            subject="Welcome \u2014 Set Up Your City of Laredo Account",
            body=body,
        )
        if not sent:
            raise RuntimeError("Account setup email delivery failed")

    async def forgot_password(self, email: str) -> None:
        """
        Initiate forgot-password flow.

        Always returns None (no enumeration — callers return 202 regardless).
        Sends reset email only when a valid web-login account exists.
        """
        employee = await self.repository.get_employee_by_email(email)
        if not employee or not employee.is_active:
            return

        # Employees do not have web access (INV-06) — silently skip
        if employee.role == Role.EMPLOYEE:
            return

        # Invalidate any existing unused reset tokens before issuing a new one (MED-27)
        await self._invalidate_pending_reset_tokens(employee.id)

        raw_token = _os.urandom(32).hex()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=auth_settings.RESET_TOKEN_EXPIRE_MINUTES
        )

        await self.repository.create_password_reset_token(
            employee.id, token_hash, expires_at
        )

        reset_url = f"{auth_settings.CANONICAL_ORIGIN}/reset-password#token={raw_token}"

        if employee.password_hash:
            # Existing account — standard reset wording
            subject = "Password Reset Request"
            body = (
                f"A password reset was requested for your account.\n\n"
                f"Click the link below to set a new password "
                f"(expires in {auth_settings.RESET_TOKEN_EXPIRE_MINUTES} minutes):\n\n"
                f"{reset_url}\n\n"
                f"If you did not request this, you can safely ignore this email."
            )
        else:
            # No password set — first-time setup wording (CRIT-01)
            subject = "Set Up Your City of Laredo Account Password"
            body = (
                f"Hello {employee.first_name},\n\n"
                f"Your account requires a password to be set.\n\n"
                f"Click the link below to set your password "
                f"(expires in {auth_settings.RESET_TOKEN_EXPIRE_MINUTES} minutes):\n\n"
                f"{reset_url}\n\n"
                f"If you did not expect this email, please contact your administrator."
            )

        try:
            sent = await _send_email(to=employee.email, subject=subject, body=body)
            if not sent:
                logging.getLogger(__name__).warning(
                    "Password reset email delivery failed",
                    extra={"employee_id": employee.id},
                )
        except Exception:
            logging.getLogger(__name__).exception(
                "Password reset email delivery raised an exception",
                extra={"employee_id": employee.id},
            )

    async def reset_password(
        self, raw_token: str, new_password: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Complete password reset using a one-time token.

        Returns:
            (True, None) on success
            (False, error_message) on failure
        """
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        record = await self.repository.get_password_reset_token_by_hash(token_hash)

        if (
            not record
            or record.used_at is not None
            or datetime.now(timezone.utc) > record.expires_at
        ):
            return False, "Invalid or expired reset token"

        # Atomically claim the token — rejects a concurrent second request
        claimed = await self.repository.claim_password_reset_token(record.id)
        if not claimed:
            return False, "Invalid or expired reset token"

        new_hash = hash_password(new_password)

        # Update password (increments token_version — invalidates all existing sessions)
        await self.repository.update_employee_password(record.employee_id, new_hash)
        # Do not touch last_logout_at here. token_version already revokes every
        # existing access/refresh token, and mutating last_logout_at can
        # invalidate a fresh login that lands in the same JWT iat second.

        await self.log_auth_event("password_reset_completed", record.employee_id, {})
        return True, None

    async def log_auth_event(
        self,
        action: str,
        employee_id: Optional[int],
        details: dict,
        actor: Optional[Employee] = None,
    ) -> None:
        """Log authentication event to audit log."""
        await _audit(
            repository=self.repository,
            action=action,
            target_type="auth",
            target_id=str(employee_id) if employee_id else "system",
            actor=actor,
            details=details,
            source_service="api",
        )

    def to_user_response(self, employee: Employee) -> UserResponse:
        """Convert Employee to UserResponse."""
        return UserResponse(
            id=employee.id,
            employee_number=employee.employee_number,
            first_name=employee.first_name,
            last_name=employee.last_name,
            email=employee.email,
            role=employee.role.value,
            is_active=employee.is_active,
        )
