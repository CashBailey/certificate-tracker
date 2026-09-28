"""
Dependency injection for FastAPI.

Provides dependency functions for all services and utilities.
"""

import os
from datetime import datetime, timezone
from typing import AsyncGenerator

import jwt
from jwt.exceptions import PyJWTError

from fastapi import Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from .shared.clock import RealClock
from .shared.models import Employee, Role
from .shared.protocols import Clock, Repository, Storage, UuidGenerator
from .shared.repository import SqlRepository
from .shared.storage import MinioStorageClient
from .shared.tls import build_ssl_context, redis_tls_kwargs
from .shared.uuid_gen import RealUuidGenerator


# ==================== DATABASE ====================

# Database URL from environment (required)
_raw_database_url = os.getenv("DATABASE_URL")
if not _raw_database_url:
    raise RuntimeError(
        "DATABASE_URL environment variable is required. "
        "Example: postgresql://user:password@host:5432/dbname"
    )

# Ensure we use asyncpg driver for async SQLAlchemy
if _raw_database_url.startswith("postgresql://"):
    DATABASE_URL = _raw_database_url.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
else:
    DATABASE_URL = _raw_database_url

# Build SSL context for mTLS (returns None when TLS_ENABLED != true)
_db_ssl_ctx = build_ssl_context()

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"ssl": _db_ssl_ctx} if _db_ssl_ctx else {},
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for database session.

    Yields:
        AsyncSession for database operations
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_repository(session: AsyncSession = Depends(get_db_session)) -> Repository:
    """
    Dependency for repository.

    Args:
        session: Database session

    Returns:
        Repository instance
    """
    return SqlRepository(session)


# ==================== STORAGE ====================

_storage_client: Storage | None = None


def get_storage() -> Storage:
    """
    Dependency for storage client.

    Returns:
        Storage instance (singleton)
    """
    global _storage_client
    if _storage_client is None:
        _storage_client = MinioStorageClient()
    return _storage_client


# ==================== REDIS ====================

import redis as redis_client

_redis: redis_client.Redis | None = None


def get_redis() -> redis_client.Redis:
    """
    Dependency for Redis client.

    Returns:
        Redis instance (singleton)
    """
    global _redis
    if _redis is None:
        redis_url = os.getenv("REDIS_URL", "rediss://redis:6380/0")
        _redis = redis_client.from_url(redis_url, **redis_tls_kwargs())
    return _redis


# ==================== UTILITIES ====================

_clock: Clock | None = None


def get_clock() -> Clock:
    """
    Dependency for clock.

    Returns:
        Clock instance (singleton)
    """
    global _clock
    if _clock is None:
        _clock = RealClock()
    return _clock


_uuid_generator: UuidGenerator | None = None


def get_uuid_generator() -> UuidGenerator:
    """
    Dependency for UUID generator.

    Returns:
        UuidGenerator instance (singleton)
    """
    global _uuid_generator
    if _uuid_generator is None:
        _uuid_generator = RealUuidGenerator()
    return _uuid_generator


# ==================== AUTHENTICATION ====================

from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def _authenticate_token(token: str, repository: Repository) -> Employee:
    """
    Shared helper: decode a JWT access token and return the authenticated employee.

    Extracted from get_current_user / get_current_user_from_token to eliminate
    duplicated auth logic (MED-24).

    Raises:
        HTTPException 401/403 on any validation failure.
    """
    from .auth.security import decode_token, is_token_expired

    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if is_token_expired(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    employee = await repository.get_employee_by_id(int(payload.sub))

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Reject tokens issued at or before the last explicit logout (AUD-02)
    if employee.last_logout_at and payload.iat and payload.iat <= employee.last_logout_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalidated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject tokens whose version doesn't match — issued before a password change (AUD-02)
    if payload.token_version is not None and payload.token_version != employee.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalidated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return employee


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    repository: Repository = Depends(get_repository),
) -> Employee:
    """
    Dependency for current user from JWT token.

    Validates the JWT token from Authorization header and returns
    the authenticated employee.

    Args:
        token: JWT token from Authorization header
        repository: Repository instance

    Returns:
        Current authenticated employee

    Raises:
        HTTPException: If authentication fails
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await _authenticate_token(token, repository)


async def get_doc_view_token_user(
    document_id: int = Path(...),
    view_token: str | None = Query(None, alias="token"),
    repository: Repository = Depends(get_repository),
) -> Employee:
    """
    Dependency for the document content endpoint.

    Accepts ONLY a short-lived 'doc_view' JWT from the query parameter.
    Rejects standard 'access' tokens — they must never appear in URLs.
    Also asserts that the token's doc_id claim matches the requested document_id
    so a captured token cannot be reused to access a different document.

    Note: token_version and last_logout_at checks are intentionally omitted.
    The 60-second TTL makes post-logout invalidation a non-issue in practice.
    """
    if not view_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from .auth.config import auth_settings

    try:
        raw_payload = jwt.decode(
            view_token,
            auth_settings.JWT_SECRET_KEY,
            algorithms=[auth_settings.JWT_ALGORITHM],
            options={"verify_exp": False},  # manual expiry check below
        )
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid view token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Manual expiry check — consistent with is_token_expired() in auth/security.py
    exp = raw_payload.get("exp")
    try:
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid view token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="View token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if raw_payload.get("type") != "doc_view":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type for document content",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if raw_payload.get("doc_id") != document_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="View token is not valid for this document",
        )

    employee_id_str = raw_payload.get("sub")
    if (
        not isinstance(employee_id_str, str)
        or not employee_id_str.isdecimal()
        or int(employee_id_str) <= 0
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid view token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    employee = await repository.get_employee_by_id(int(employee_id_str))

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    return employee


# ==================== ROLE-BASED ACCESS CONTROL ====================


def require_roles(*allowed_roles: Role):
    """
    Dependency factory for role-based access control.

    Returns a FastAPI dependency that checks the current user's role
    against the allowed roles list, raising HTTP 403 if unauthorized.
    """

    async def role_checker(
        current_user: Employee = Depends(get_current_user),
    ) -> Employee:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not authorized for this action",
            )
        return current_user

    return role_checker


# Convenience dependencies for common role requirements
require_admin = require_roles(Role.ADMIN)
require_coordinator = require_roles(Role.COORDINATOR)
require_coordinator_or_admin = require_roles(Role.COORDINATOR, Role.ADMIN)


# ==================== SHUTDOWN ====================


async def shutdown_database():
    """Shutdown database connection pool."""
    await engine.dispose()
