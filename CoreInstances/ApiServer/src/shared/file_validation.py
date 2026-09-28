"""
File validation utilities for the City of Laredo Certificate Management System.

Functions for sanitizing filenames, detecting MIME types from magic bytes,
validating uploaded files, and safely building download headers.
"""

from typing import Optional
from urllib.parse import quote


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing dangerous characters.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for storage
    """
    # Remove path separators, null bytes, newlines, and HTTP header injection characters
    filename = (
        filename.replace("/", "_")
        .replace("\\", "_")
        .replace("\x00", "")
        .replace("\n", "_")
        .replace("\r", "_")
        .replace('"', "")
        .replace(";", "_")
    )
    # Remove leading dots to prevent hidden files
    filename = filename.lstrip(".")
    # Truncate to reasonable length
    if len(filename) > 255:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        max_name_len = 255 - len(ext) - 1
        filename = name[:max_name_len] + ("." + ext if ext else "")
    return filename or "unnamed"


def build_content_disposition(disposition_type: str, filename: str) -> str:
    """
    Build a Content-Disposition header value safely.

    Uses a sanitized quoted ASCII fallback plus RFC 5987 UTF-8 filename* so
    clients can preserve unicode names without header injection risk.

    Args:
        disposition_type: Either "attachment" or "inline"
        filename: User-supplied filename

    Returns:
        Header value suitable for Content-Disposition
    """
    if disposition_type not in {"attachment", "inline"}:
        raise ValueError(
            f"Invalid disposition type '{disposition_type}'. Must be attachment or inline."
        )

    safe_filename = sanitize_filename(filename)

    # Quoted fallback for older clients.
    ascii_fallback = safe_filename.encode("ascii", errors="ignore").decode("ascii")
    if not ascii_fallback:
        ascii_fallback = "download"
    escaped_fallback = ascii_fallback.replace("\\", "\\\\").replace('"', '\\"')

    # UTF-8 filename* for modern clients.
    encoded_filename = quote(safe_filename, safe="")

    return (
        f'{disposition_type}; filename="{escaped_fallback}"; '
        f"filename*=UTF-8''{encoded_filename}"
    )


def detect_mime_from_bytes(file_bytes: bytes) -> Optional[str]:
    """
    Detect MIME type from file magic bytes.

    Args:
        file_bytes: File content bytes

    Returns:
        MIME type string or None if unknown
    """
    if len(file_bytes) < 4:
        return None

    # PDF
    if file_bytes.startswith(b"%PDF"):
        return "application/pdf"

    # PNG
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    # JPEG
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    # TIFF
    if file_bytes.startswith(b"II\x2a\x00") or file_bytes.startswith(b"MM\x00\x2a"):
        return "image/tiff"

    return None


# Default allowed MIME types for uploads
ALLOWED_UPLOAD_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}

# Default maximum upload size (20 MB) - standardized across frontend, API, and workers
MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024


def validate_upload_bytes_and_type(
    file_bytes: bytes,
    filename: str,
    allowed_types: set[str] = ALLOWED_UPLOAD_TYPES,
    max_size_bytes: int = MAX_UPLOAD_SIZE_BYTES,
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Validate uploaded file bytes and type.

    Args:
        file_bytes: File content bytes
        filename: Original filename
        allowed_types: Set of allowed MIME types
        max_size_bytes: Maximum file size in bytes

    Returns:
        Tuple of (is_valid, mime_type, error_message)
    """
    # Check size
    if len(file_bytes) > max_size_bytes:
        return (
            False,
            None,
            f"File too large: {len(file_bytes)} bytes (max {max_size_bytes})",
        )

    if len(file_bytes) == 0:
        return False, None, "File is empty"

    # Detect MIME type
    mime_type = detect_mime_from_bytes(file_bytes)
    if not mime_type:
        return False, None, "Could not detect file type"

    # Check against allowed types
    if mime_type not in allowed_types:
        return False, mime_type, f"File type {mime_type} not allowed"

    return True, mime_type, None
