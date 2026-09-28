"""
Security utilities for JWT tokens and password hashing.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import bcrypt as _bcrypt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from jwt.exceptions import PyJWTError
from pydantic import ValidationError

from .config import auth_settings
from .schemas import TokenPayload


# ---------------------------------------------------------------------------
# Password hashing — Argon2id primary, bcrypt accepted for legacy rehash
#
# passlib is intentionally NOT used here: passlib 1.7.4 (last release 2020)
# breaks with bcrypt 4.0+ because it accesses bcrypt.__about__.__version__
# and uses a 73-byte test password in detect_wrap_bug(), which bcrypt 4.0+
# rejects.  Using argon2-cffi and bcrypt directly avoids the incompatibility.
# ---------------------------------------------------------------------------

_argon2 = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB — OWASP Argon2id recommended
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Pre-computed for timing equalization — never changes at runtime.
_DUMMY_HASH: str = _argon2.hash("dummy_constant_for_timing_equalization")


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    return _argon2.hash(password)


def verify_password(plain: str, hashed: str) -> Tuple[bool, Optional[str]]:
    """
    Verify password against stored hash.

    Returns:
        (is_valid, new_hash_if_needs_rehash)
        new_hash is non-None when a legacy bcrypt hash needs upgrading to
        Argon2id.  Caller must save new_hash WITHOUT incrementing
        token_version.
    """
    # Argon2id hashes (primary scheme)
    if hashed.startswith("$argon2"):
        try:
            _argon2.verify(hashed, plain)
            new_hash = _argon2.hash(plain) if _argon2.check_needs_rehash(hashed) else None
            return True, new_hash
        except (VerifyMismatchError, VerificationError, Exception):
            return False, None

    # Legacy bcrypt hashes — verify then rehash to Argon2id
    if hashed.startswith(("$2b$", "$2a$", "$2y$")):
        try:
            valid = _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
            if valid:
                return True, _argon2.hash(plain)
            return False, None
        except Exception:
            return False, None

    return False, None


def verify_password_dummy() -> None:
    """Perform equivalent Argon2id work to equalize timing for missing/ineligible users."""
    try:
        _argon2.verify(_DUMMY_HASH, "dummy")
    except (VerifyMismatchError, VerificationError):
        pass  # Expected — "dummy" does not match the pre-computed hash


# ---------------------------------------------------------------------------
# JWT token creation and decoding
# ---------------------------------------------------------------------------


def create_access_token(
    employee_id: int,
    email: str,
    role: str,
    token_version: int = 1,
) -> Tuple[str, datetime]:
    """
    Create a new JWT access token.

    Returns:
        Tuple of (token_string, expiry_datetime)
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=auth_settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(employee_id),
        "email": email,
        "role": role,
        "type": "access",
        "exp": expires,
        "iat": now,
        "token_version": token_version,
    }

    token = jwt.encode(
        payload, auth_settings.JWT_SECRET_KEY, algorithm=auth_settings.JWT_ALGORITHM
    )

    return token, expires


def create_refresh_token(
    employee_id: int,
    email: str,
    role: str,
    token_version: int = 1,
    session_created_at: Optional[datetime] = None,
) -> Tuple[str, datetime]:
    """
    Create a new JWT refresh token.

    session_created_at is embedded and forwarded unchanged on each refresh
    to enforce SESSION_MAX_HOURS wall-clock limit.

    Returns:
        Tuple of (token_string, expiry_datetime)
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=auth_settings.REFRESH_TOKEN_EXPIRE_DAYS)
    sess_start = session_created_at or now

    payload = {
        "sub": str(employee_id),
        "email": email,
        "role": role,
        "type": "refresh",
        "exp": expires,
        "iat": now,
        "token_version": token_version,
        "session_created_at": sess_start.isoformat(),
    }

    token = jwt.encode(
        payload, auth_settings.JWT_SECRET_KEY, algorithm=auth_settings.JWT_ALGORITHM
    )

    return token, expires


def create_doc_view_token(employee_id: int, doc_id: int) -> str:
    """
    Create a short-lived, single-purpose document view token.

    The token is valid for 60 seconds and is scoped to a single document_id.
    It is rejected by all standard Bearer-auth dependencies because its
    'type' claim is 'doc_view', not 'access'.

    Returns:
        Signed JWT string
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=60)

    payload = {
        "sub": str(employee_id),
        "type": "doc_view",
        "doc_id": doc_id,
        "exp": expires,
        "iat": now,
    }

    return jwt.encode(
        payload, auth_settings.JWT_SECRET_KEY, algorithm=auth_settings.JWT_ALGORITHM
    )


def decode_token(token: str) -> Optional[TokenPayload]:
    """
    Decode and validate a JWT token.

    Returns:
        TokenPayload if valid, None if invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            auth_settings.JWT_SECRET_KEY,
            algorithms=[auth_settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )

        # Guard required claims before use — payload.get() returns None for absent
        # claims, and datetime.fromtimestamp(None) raises TypeError which is NOT
        # caught by the except JWTError block below (HIGH-01).
        sub = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")
        token_type = payload.get("type")
        exp_raw = payload.get("exp")
        iat_raw = payload.get("iat")
        if (
            not isinstance(sub, str)
            or not sub.isdecimal()
            or int(sub) <= 0
            or not isinstance(email, str)
            or not email
            or not isinstance(role, str)
            or not role
            or token_type not in {"access", "refresh"}
            or isinstance(exp_raw, bool)
            or not isinstance(exp_raw, (int, float))
            or isinstance(iat_raw, bool)
            or not isinstance(iat_raw, (int, float))
        ):
            return None

        token_version = payload.get("token_version")
        if token_version is not None and (
            isinstance(token_version, bool)
            or not isinstance(token_version, int)
            or token_version < 0
        ):
            return None

        # Parse optional session_created_at from ISO string
        raw_sess = payload.get("session_created_at")
        session_created_at: Optional[datetime] = None
        if raw_sess:
            try:
                session_created_at = datetime.fromisoformat(raw_sess)
                if session_created_at.tzinfo is None:
                    session_created_at = session_created_at.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                return None
        if token_type == "refresh" and session_created_at is None:
            return None

        return TokenPayload(
            sub=sub,
            email=email,
            role=role,
            type=token_type,
            exp=datetime.fromtimestamp(exp_raw, tz=timezone.utc),
            iat=datetime.fromtimestamp(iat_raw, tz=timezone.utc),
            token_version=token_version,
            session_created_at=session_created_at,
        )
    except (PyJWTError, ValidationError, TypeError, ValueError, OverflowError, OSError):
        return None


def is_token_expired(payload: TokenPayload) -> bool:
    """Check if a token payload is expired."""
    return datetime.now(timezone.utc) > payload.exp
