"""
Exception handlers for the API.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from ..shared.protocols import (
    AuthorizationError,
    ConcurrencyError,
    ReviewConflictError,
    TemplateNotFoundError,
    TemplateVersionNotFoundError,
    UploadValidationError,
)


async def authorization_error_handler(
    request: Request,
    exc: AuthorizationError,
) -> JSONResponse:
    """Handle authorization errors."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc)},
    )


async def upload_validation_error_handler(
    request: Request,
    exc: UploadValidationError,
) -> JSONResponse:
    """Handle upload validation errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


async def review_conflict_error_handler(
    request: Request,
    exc: ReviewConflictError,
) -> JSONResponse:
    """Handle review state conflict errors."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


async def concurrency_error_handler(
    request: Request,
    exc: ConcurrencyError,
) -> JSONResponse:
    """Handle optimistic locking errors."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


async def template_not_found_error_handler(
    request: Request,
    exc: TemplateNotFoundError,
) -> JSONResponse:
    """Handle template not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


async def template_version_not_found_error_handler(
    request: Request,
    exc: TemplateVersionNotFoundError,
) -> JSONResponse:
    """Handle template version not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


async def permission_error_handler(
    request: Request,
    exc: PermissionError,
) -> JSONResponse:
    """Handle authorizer PermissionError as 403."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc)},
    )


def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app."""
    app.add_exception_handler(AuthorizationError, authorization_error_handler)
    app.add_exception_handler(UploadValidationError, upload_validation_error_handler)
    app.add_exception_handler(ReviewConflictError, review_conflict_error_handler)
    app.add_exception_handler(ConcurrencyError, concurrency_error_handler)
    app.add_exception_handler(TemplateNotFoundError, template_not_found_error_handler)
    app.add_exception_handler(
        TemplateVersionNotFoundError, template_version_not_found_error_handler
    )
    app.add_exception_handler(PermissionError, permission_error_handler)
