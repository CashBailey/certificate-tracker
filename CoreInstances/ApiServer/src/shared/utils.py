"""
Pure utility functions for the City of Laredo Certificate Management System.

This module re-exports functions from domain-specific modules for backward compatibility.
New code should import directly from the specific modules:

- file_validation: sanitize_filename, detect_mime_from_bytes, validate_upload_bytes_and_type
  and build_content_disposition
- geometry: bbox_*, intersects, merge_bboxes, span_belongs_to_zone, pdf_bbox_to_norm_top_left
- text_processing: cluster_tokens_into_lines, join_tokens_reading_order, build_searchable_text
- status_computation: compute_requirement_status, compute_certificate_lifecycle_status, etc.
"""

# File validation
from .file_validation import (
    sanitize_filename,
    build_content_disposition,
    detect_mime_from_bytes,
    validate_upload_bytes_and_type,
    ALLOWED_UPLOAD_TYPES,
    MAX_UPLOAD_SIZE_BYTES,
)

# Geometry utilities
from .geometry import (
    clamp01,
    bbox_center,
    intersects,
    merge_bboxes,
    span_belongs_to_zone,
    pdf_bbox_to_norm_top_left,
)

# Text processing
from .text_processing import (
    cluster_tokens_into_lines,
    join_tokens_reading_order,
    build_searchable_text,
    LINE_HEIGHT_THRESHOLD,
)

# Status computation
from .status_computation import (
    compute_requirement_status,
    certificate_has_expiration,
    compute_certificate_lifecycle_status,
    compute_requirement_compliance_status,
    get_certificate_lifecycle_status_enum,
    DEFAULT_SOON_DAYS,
)

# Re-export everything for backward compatibility
__all__ = [
    # File validation
    "sanitize_filename",
    "build_content_disposition",
    "detect_mime_from_bytes",
    "validate_upload_bytes_and_type",
    "ALLOWED_UPLOAD_TYPES",
    "MAX_UPLOAD_SIZE_BYTES",
    # Geometry
    "clamp01",
    "bbox_center",
    "intersects",
    "merge_bboxes",
    "span_belongs_to_zone",
    "pdf_bbox_to_norm_top_left",
    # Text processing
    "cluster_tokens_into_lines",
    "join_tokens_reading_order",
    "build_searchable_text",
    "LINE_HEIGHT_THRESHOLD",
    # Status computation
    "compute_requirement_status",
    "certificate_has_expiration",
    "compute_certificate_lifecycle_status",
    "compute_requirement_compliance_status",
    "get_certificate_lifecycle_status_enum",
    "DEFAULT_SOON_DAYS",
]
