"""
Authentication configuration settings.
"""

import os
from urllib.parse import urlsplit


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(
            f"{name} must be between {minimum} and {maximum} (got {value})"
        )
    return value


def _validate_secret(value: str) -> str:
    if len(value) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 characters")
    if value.casefold() in {
        "dev-secret-key-change-in-production",
        "change_me_in_production",
        "replace_me_generate_with_openssl_rand_hex_32",
    }:
        raise RuntimeError(
            "SECRET_KEY uses the insecure default placeholder. "
            "Generate a unique value with: openssl rand -hex 32"
        )
    return value


def _validate_origin(value: str) -> str:
    origin = value.rstrip("/")
    parsed = urlsplit(origin)
    local_origin = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in {"http", "https"}
        or (parsed.scheme != "https" and not local_origin)
    ):
        raise RuntimeError(
            "FRONTEND_URL must be an HTTPS origin (HTTP is allowed only for localhost)"
        )
    return origin


class AuthSettings:
    """Authentication settings from environment variables."""

    # JWT Configuration (required - uses SECRET_KEY env var)
    _jwt_secret = os.getenv("SECRET_KEY")
    if not _jwt_secret:
        raise RuntimeError(
            "SECRET_KEY environment variable is required. "
            "Generate with: openssl rand -hex 32"
        )
    JWT_SECRET_KEY: str = _validate_secret(_jwt_secret)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = _bounded_env_int(
        "ACCESS_TOKEN_EXPIRE_MINUTES", 30, 1, 1_440
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = _bounded_env_int(
        "REFRESH_TOKEN_EXPIRE_DAYS", 7, 1, 30
    )

    # Password Requirements
    PASSWORD_MIN_LENGTH: int = 15
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True

    # Session Policy
    SESSION_MAX_HOURS: int = _bounded_env_int("SESSION_MAX_HOURS", 8, 1, 72)

    # Password Reset
    CANONICAL_ORIGIN: str = _validate_origin(
        os.getenv("FRONTEND_URL", "https://localhost")
    )
    RESET_TOKEN_EXPIRE_MINUTES: int = _bounded_env_int(
        "RESET_TOKEN_EXPIRE_MINUTES", 30, 5, 1_440
    )

    # Refresh token cookie settings (CRIT-04)
    REFRESH_COOKIE_NAME: str = "laredo_refresh"
    REFRESH_COOKIE_PATH: str = "/"
    COOKIE_SECURE: bool = CANONICAL_ORIGIN.startswith("https://")
    COOKIE_SAMESITE: str = "strict"
    COOKIE_DOMAIN: str | None = os.getenv("COOKIE_DOMAIN")


auth_settings = AuthSettings()
