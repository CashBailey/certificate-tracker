"""
Geometry utilities for the City of Laredo Certificate Management System.

Functions for bounding box calculations, coordinate transformations,
and PDF coordinate system conversions.
"""

def clamp01(value: float) -> float:
    """Clamp value to [0, 1] range."""
    return max(0.0, min(1.0, value))


def bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    """Calculate center point of bounding box."""
    x0, y0, x1, y1 = bbox
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def intersects(
    bbox1: tuple[float, float, float, float], bbox2: tuple[float, float, float, float]
) -> bool:
    """Check if two bounding boxes intersect."""
    x0_1, y0_1, x1_1, y1_1 = bbox1
    x0_2, y0_2, x1_2, y1_2 = bbox2
    return not (x1_1 < x0_2 or x1_2 < x0_1 or y1_1 < y0_2 or y1_2 < y0_1)


def merge_bboxes(
    bboxes: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Merge multiple bounding boxes into one encompassing box."""
    if not bboxes:
        return (0.0, 0.0, 0.0, 0.0)

    x0 = min(b[0] for b in bboxes)
    y0 = min(b[1] for b in bboxes)
    x1 = max(b[2] for b in bboxes)
    y1 = max(b[3] for b in bboxes)

    return (x0, y0, x1, y1)


def span_belongs_to_zone(
    span_bbox: tuple[float, float, float, float],
    zone_bbox: tuple[float, float, float, float],
    tolerance: float = 0.0,
) -> bool:
    """
    Check if a span belongs to a zone, with optional tolerance.

    Args:
        span_bbox: Bounding box of the span
        zone_bbox: Bounding box of the zone
        tolerance: Tolerance for zone boundaries (normalized)

    Returns:
        True if span is within zone (with tolerance)
    """
    x0_s, y0_s, x1_s, y1_s = span_bbox
    x0_z, y0_z, x1_z, y1_z = zone_bbox

    # Expand zone by tolerance
    x0_z -= tolerance
    y0_z -= tolerance
    x1_z += tolerance
    y1_z += tolerance

    # Check if span center is within zone
    cx, cy = bbox_center(span_bbox)
    return x0_z <= cx <= x1_z and y0_z <= cy <= y1_z


def pdf_bbox_to_norm_top_left(
    pdf_bbox: tuple[float, float, float, float],
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float]:
    """
    Convert PDF coordinate system (bottom-left origin) to normalized top-left origin.

    Args:
        pdf_bbox: Bounding box in PDF coordinates (x0, y0, x1, y1) from bottom-left
        page_width: Page width in PDF units
        page_height: Page height in PDF units

    Returns:
        Normalized bounding box (x0, y0, x1, y1) with top-left origin, values in [0, 1]
    """
    x0, y0, x1, y1 = pdf_bbox

    # Normalize coordinates
    x0_norm = clamp01(x0 / page_width)
    x1_norm = clamp01(x1 / page_width)

    # Flip Y-axis (PDF has origin at bottom-left, we want top-left)
    y0_norm = clamp01(1.0 - (y1 / page_height))
    y1_norm = clamp01(1.0 - (y0 / page_height))

    return (x0_norm, y0_norm, x1_norm, y1_norm)


