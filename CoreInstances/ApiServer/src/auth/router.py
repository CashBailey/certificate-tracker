"""
Authentication API endpoints.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..deps import get_current_user, get_redis, get_repository
from ..shared.models import Employee
from ..shared.repository import SqlRepository
from .config import auth_settings
from .schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    PasswordChangeRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from .service import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger(__name__)

LOGIN_RATE_LIMIT = os.getenv("AUTH_LOGIN_RATE_LIMIT", "60/minute")
FORGOT_PASSWORD_RATE_LIMIT = os.getenv("AUTH_FORGOT_PASSWORD_RATE_LIMIT", "5/hour")
RESET_PASSWORD_RATE_LIMIT = os.getenv("AUTH_RESET_PASSWORD_RATE_LIMIT", "5/minute")

def _slowapi_storage_uri() -> str:
    """Build a storage_uri for SlowAPI that works with the project's TLS Redis.

    SlowAPI delegates to the `limits` library, which uses its own Redis client
    rather than the one we configure in `shared/tls.py`. For `rediss://` URLs
    we must append ssl_* query params so `limits` can construct an SSL
    context that trusts our internal CA — otherwise every rate-limited
    request 500s with `CERTIFICATE_VERIFY_FAILED`.

    For non-TLS URLs (`redis://`) or when `REDIS_URL` is unset, no extras
    needed; we fall back to in-memory storage in the latter case.
    """
    base = os.getenv("REDIS_URL")
    if not base:
        return "memory://"
    if base.startswith("rediss://"):
        ca_path = os.getenv("TLS_CA_CERT", "/tls/ca.crt")
        client_cert = os.getenv("TLS_CLIENT_CERT", "/tls/client.crt")
        client_key = os.getenv("TLS_CLIENT_KEY", "/tls/client.key")
        sep = "&" if "?" in base else "?"
        return (
            f"{base}{sep}ssl_cert_reqs=required"
            f"&ssl_ca_certs={ca_path}"
            f"&ssl_certfile={client_cert}"
            f"&ssl_keyfile={client_key}"
        )
    return base


# storage_uri makes per-IP rate limits global across replicas. Without it,
# SlowAPI defaults to in-memory storage — each Gunicorn worker has its own
# counter, so with N workers the effective limit is N×declared.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_slowapi_storage_uri(),
)


def get_auth_service(
    repository: SqlRepository = Depends(get_repository),
    redis=Depends(get_redis),
) -> AuthService:
    """Dependency to get auth service."""
    return AuthService(repository, redis=redis)


def _delete_refresh_cookie(response: JSONResponse, auth_service: AuthService) -> None:
    cookie_params = auth_service.build_refresh_cookie_params()
    delete_params = {key: value for key, value in cookie_params.items() if key != "max_age"}
    response.delete_cookie(**delete_params)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
async def login(
    request: Request,
    credentials: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Authenticate user and return JWT tokens.

    - **email**: User's email address
    - **password**: User's password

    Returns access and refresh tokens on success.
    Rate limited per IP to absorb automated login bursts without
    disrupting ordinary multi-tab browsing or QA verification.
    """
    employee, error = await auth_service.authenticate(
        credentials.email,
        credentials.password,
    )

    if error:
        await auth_service.log_auth_event(
            action="login_failed",
            employee_id=None,
            details={
                "email": credentials.email,
                "reason": error,
                "ip_address": request.client.host if request.client else None,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_pair = await auth_service.create_tokens(employee)

    await auth_service.log_auth_event(
        action="login_success",
        employee_id=employee.id,
        details={
            "ip_address": request.client.host if request.client else None,
        },
        actor=employee,
    )

    response = JSONResponse(content=token_pair.model_dump(exclude={"refresh_token"}))

    cookie_params = auth_service.build_refresh_cookie_params()
    response.set_cookie(value=token_pair.refresh_token, **cookie_params)

    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Refresh access token using httpOnly refresh cookie.

    Returns new access token in body and rotates refresh cookie.

    Deliberately not rate limited:
    - browser tabs legitimately bootstrap or recover sessions by calling refresh
    - the endpoint is cookie-backed rather than credential-guessable
    - per-account invalidation still happens via token_version/logout/session checks

    Keeping the tight login limiter here caused browser-visible 429s during
    legitimate long-lived sessions and multi-tab refresh bursts.
    """
    refresh_token_value = request.cookies.get(auth_settings.REFRESH_COOKIE_NAME)
    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_pair, error = await auth_service.refresh_tokens(refresh_token_value)

    if error:
        response = JSONResponse(content={"detail": error}, status_code=401)
        _delete_refresh_cookie(response, auth_service)
        return response

    response = JSONResponse(content=token_pair.model_dump(exclude={"refresh_token"}))

    cookie_params = auth_service.build_refresh_cookie_params()
    response.set_cookie(value=token_pair.refresh_token, **cookie_params)

    return response


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Employee = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Get current authenticated user information.

    Requires valid access token in Authorization header.
    """
    return auth_service.to_user_response(current_user)


@router.post("/logout")
async def logout(
    request: Request,
    current_user: Employee = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Logout current user.

    Sets last_logout_at so all existing refresh tokens are immediately invalidated.
    Clears the httpOnly refresh cookie.
    """
    try:
        await auth_service.record_logout(current_user.id)
        await auth_service.log_auth_event(
            action="logout",
            employee_id=current_user.id,
            details={
                "ip_address": request.client.host if request.client else None,
            },
            actor=current_user,
        )
        response = JSONResponse(content={"message": "Successfully logged out"})
    except Exception:
        logger.exception(
            "Failed to persist logout revocation",
            extra={"employee_id": current_user.id},
        )
        response = JSONResponse(
            content={"detail": "Logout revocation could not be persisted"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    _delete_refresh_cookie(response, auth_service)
    return response


@router.post("/clear-session")
async def clear_session_cookie(
    auth_service: AuthService = Depends(get_auth_service),
):
    """Delete the browser refresh cookie without restoring a stale session."""
    response = JSONResponse(content={"message": "Browser session cleared"})
    _delete_refresh_cookie(response, auth_service)
    return response


@router.post("/change-password")
async def change_password(
    body: PasswordChangeRequest,
    current_user: Employee = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Change current user's password.

    - **current_password**: Current password for verification
    - **new_password**: New password (minimum 15 characters)
    """
    success, error = await auth_service.change_password(
        current_user,
        body.current_password,
        body.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    await auth_service.log_auth_event(
        action="password_changed",
        employee_id=current_user.id,
        details={},
        actor=current_user,
    )

    return {"message": "Password changed successfully"}


@router.post("/forgot-password", status_code=202)
@limiter.limit(FORGOT_PASSWORD_RATE_LIMIT)
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Request a password reset email.

    Always returns 202 Accepted to avoid account enumeration.
    Rate limited to 5 requests per hour per IP — Cloudflare-style threat
    model where the relevant abuse window for password-reset spam is hours,
    not seconds. Per-email throttle (3/hour) is applied separately in the
    auth service for full anti-flood coverage.
    """
    await auth_service.forgot_password(body.email)
    return {"message": "If the email exists, a reset link has been sent."}


@router.post("/reset-password")
@limiter.limit(RESET_PASSWORD_RATE_LIMIT)
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Complete password reset with a one-time token.

    - **token**: Reset token from the email link
    - **new_password**: New password (minimum 15 characters)
    """
    success, error = await auth_service.reset_password(body.token, body.new_password)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return {"message": "Password reset successfully. Please log in with your new password."}
