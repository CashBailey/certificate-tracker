"""
City of Laredo Certificate Management System - API Server
"""

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse
from slowapi import _rate_limit_exceeded_handler  # noqa: F401  (kept for backward-compat)
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import structlog

from .auth import router as auth_router
from .auth.router import limiter
from .routes import (
    admin_router,
    alert_config_router,
    audit_logs_router,
    certificate_types_router,
    documents_router,
    employees_router,
    extractions_router,
    notifications_router,
    reports_router,
    requirements_router,
    templates_router,
    verified_records_router,
)
from .routes.errors import register_exception_handlers

logging.basicConfig(format="%(message)s", level=logging.INFO)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security-relevant response headers on every API response."""

    _HEADERS = {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }

    async def dispatch(
        self, request: StarletteRequest, call_next
    ) -> StarletteResponse:
        response = await call_next(request)
        for header, value in self._HEADERS.items():
            response.headers[header] = value
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    logger.info("Starting City of Laredo API Server...")

    # Initialize template registry
    try:
        from .routes.templates import get_template_registry

        registry = get_template_registry()
        logger.info(
            "Template registry loaded: %d templates", len(registry.list_templates())
        )
    except (json.JSONDecodeError, ValueError, OSError, KeyError) as e:
        # JSONDecodeError: Invalid template JSON
        # ValueError: Invalid template structure/values
        # OSError: File read errors
        # KeyError: Missing required template fields
        logger.warning("Could not load template registry: %s", e)

    # CRIT-01: Warn if admin account still uses the default password
    try:
        from sqlalchemy import text as _sa_text

        from .auth.security import verify_password as _verify_pw
        from .deps import AsyncSessionLocal

        async with AsyncSessionLocal() as _session:
            _result = await _session.execute(
                _sa_text(
                    "SELECT password_hash FROM certificates.employees "
                    "WHERE email = 'admin@ci.laredo.tx.us' AND password_hash IS NOT NULL"
                )
            )
            _admin_hash = _result.scalar()
            if _admin_hash and _verify_pw("Admin123!", _admin_hash)[0]:
                logger.critical(
                    "SECURITY: Admin account still uses the default password (CRIT-01). "
                    "Use the forgot-password flow at /forgot-password to set a secure password."
                )
    except Exception:
        # Do not block startup if the check fails (e.g. DB not ready yet)
        logger.warning("Could not verify admin password status (CRIT-01 check)")

    yield

    # Shutdown
    logger.info("Shutting down City of Laredo API Server...")
    from .deps import shutdown_database

    await shutdown_database()


_DEBUG = os.getenv("DEBUG", "false").lower() == "true"

app = FastAPI(
    title="City of Laredo Certificate Management API",
    description="API for managing employee certifications and compliance tracking",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _DEBUG else None,
    redoc_url="/redoc" if _DEBUG else None,
    openapi_url="/openapi.json" if _DEBUG else None,
)

# Prometheus metrics (AUD-42) — exposes /metrics endpoint
Instrumentator().instrument(app).expose(app)

# Rate limiting (slowapi)
app.state.limiter = limiter


def _rate_limit_handler_with_retry_after(request, exc: RateLimitExceeded):
    """SlowAPI's default handler returns 429 without a Retry-After header.
    This wrapper attaches one using the window from the limit rule, so
    clients know when to try again. Regression guard: T-SEC-030.
    """
    from fastapi.responses import JSONResponse

    retry_seconds = getattr(getattr(exc, "limit", None), "per", None) or 60
    # Limit.per is an int (seconds) when populated by slowapi; fall back to 60.
    try:
        retry_seconds = int(retry_seconds)
    except (TypeError, ValueError):
        retry_seconds = 60
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {getattr(exc, 'detail', str(exc))}"},
        headers={"Retry-After": str(retry_seconds)},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler_with_retry_after)
app.add_middleware(SlowAPIMiddleware)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "https://localhost")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Proxy header forwarding (must be outermost to set request.client before
# rate limiter and audit logging read it).
# trusted_hosts="*" is safe: after host port removal, only Docker-internal
# traffic reaches this container — no external client can spoof X-Forwarded-For.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Register exception handlers
register_exception_handlers(app)

# Include routers
app.include_router(auth_router)
app.include_router(admin_router, prefix="/api")
app.include_router(alert_config_router, prefix="/api")
app.include_router(audit_logs_router, prefix="/api")
app.include_router(certificate_types_router, prefix="/api")
app.include_router(employees_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(requirements_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(extractions_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(templates_router, prefix="/api")
app.include_router(verified_records_router, prefix="/api")


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and load balancers."""
    return {
        "status": "healthy",
        "service": "laredo-api",
        "version": "0.1.0",
    }


@app.get("/")
async def root():
    """Root endpoint with API information."""
    response: dict = {
        "message": "City of Laredo Certificate Management API",
        "version": "0.1.0",
    }
    if _DEBUG:
        response["docs_url"] = "/docs"
    return response
