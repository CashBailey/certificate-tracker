"""
Pydantic schemas for authentication requests and responses.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from .config import auth_settings


class LoginRequest(BaseModel):
    """Login request schema."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalize email to lowercase so User@City.GOV matches user@city.gov (MED-26)."""
        if isinstance(v, str):
            return v.lower()
        return v


class TokenPair(BaseModel):
    """Internal type holding both tokens. NOT used as an API response."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class TokenResponse(BaseModel):
    """API response schema -- refresh token is delivered via httpOnly cookie."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class UserResponse(BaseModel):
    """User information response schema."""

    id: int
    employee_number: str
    first_name: str
    last_name: str
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


# Known-bad passwords for City of Laredo deployments.
# Lowercase comparison is used at call sites (.lower() before 'in' check).
_COMMON_PASSWORD_BLOCKLIST: frozenset[str] = frozenset({
    "laredo2024!",
    "laredo2025!",
    "city@12345",
    "password123!",
    "admin@12345",
    "welcome1234!",
    "cityoflaredo1",
    "laredo#1234",
    "texas@2024!",
    "p@ssw0rd123!",
})


class PasswordChangeRequest(BaseModel):
    """Password change request schema."""

    current_password: str
    new_password: str = Field(
        ..., min_length=auth_settings.PASSWORD_MIN_LENGTH, max_length=128
    )

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Validate password complexity per organisation policy.

        Enforces:
        - Minimum length (already checked by Field; re-checked here for a clear error message)
        - At least one digit when PASSWORD_REQUIRE_DIGIT is True
        - At least one special character when PASSWORD_REQUIRE_SPECIAL is True
        - Not in the known-bad municipal password blocklist
        """
        if len(v) < auth_settings.PASSWORD_MIN_LENGTH:
            raise ValueError(
                f"Password must be at least {auth_settings.PASSWORD_MIN_LENGTH} characters"
            )

        if auth_settings.PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit (0-9)")

        if auth_settings.PASSWORD_REQUIRE_SPECIAL and not any(
            c in r"""!@#$%^&*()_+-=[]{}|;':",.<>?/`~\\""" for c in v
        ):
            raise ValueError(
                "Password must contain at least one special character "
                r"(!@#$%^&*()_+-=[]{}|;':\",./<>?`~\\)"
            )

        if v.lower() in _COMMON_PASSWORD_BLOCKLIST:
            raise ValueError(
                "This password is too common. Please choose a more unique password."
            )

        return v


class TokenPayload(BaseModel):
    """JWT token payload schema."""

    sub: str  # employee_id
    email: str
    role: str
    type: str  # "access" or "refresh"
    exp: datetime
    iat: datetime
    token_version: Optional[int] = None
    session_created_at: Optional[datetime] = None  # For SESSION_MAX_HOURS enforcement


class ForgotPasswordRequest(BaseModel):
    """Forgot password request schema."""

    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalize email to lowercase (MED-26)."""
        if isinstance(v, str):
            return v.lower()
        return v


class ResetPasswordRequest(BaseModel):
    """Reset password request schema."""

    token: str
    new_password: str = Field(
        ..., min_length=auth_settings.PASSWORD_MIN_LENGTH, max_length=128
    )

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Validate password complexity per organisation policy.

        Enforces:
        - Minimum length (already checked by Field; re-checked here for a clear error message)
        - At least one digit when PASSWORD_REQUIRE_DIGIT is True
        - At least one special character when PASSWORD_REQUIRE_SPECIAL is True
        - Not in the known-bad municipal password blocklist
        """
        if len(v) < auth_settings.PASSWORD_MIN_LENGTH:
            raise ValueError(
                f"Password must be at least {auth_settings.PASSWORD_MIN_LENGTH} characters"
            )

        if auth_settings.PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit (0-9)")

        if auth_settings.PASSWORD_REQUIRE_SPECIAL and not any(
            c in r"""!@#$%^&*()_+-=[]{}|;':",.<>?/`~\\""" for c in v
        ):
            raise ValueError(
                "Password must contain at least one special character "
                r"(!@#$%^&*()_+-=[]{}|;':\",./<>?`~\\)"
            )

        if v.lower() in _COMMON_PASSWORD_BLOCKLIST:
            raise ValueError(
                "This password is too common. Please choose a more unique password."
            )

        return v
