"""
Confidence calculation for extraction results.

Handles confidence math: caps, per-field thresholds, needs_review gating.
"""

from typing import Optional

from shared.models import (
    CONFIDENCE_CAPS,
    DEFAULT_NEEDS_REVIEW_BELOW,
    FIELD_CONFIDENCE_THRESHOLDS,
    ExtractionConfidence,
    ExtractedFieldValue,
)


def cap_component(value: float, component: str) -> float:
    """Cap a confidence component to its maximum value."""
    cap = CONFIDENCE_CAPS.get(component, 1.0)
    return min(max(value, 0.0), cap)


def calculate_overall_confidence(conf: ExtractionConfidence) -> float:
    """
    Calculate overall confidence from components.

    Overall = zone + ocr + parse + validate (each capped)
    """
    return (
        cap_component(conf.zone, "zone") +
        cap_component(conf.ocr, "ocr") +
        cap_component(conf.parse, "parse") +
        cap_component(conf.validate, "validate")
    )


def build_extraction_confidence(
    zone_conf: float = 0.0,
    ocr_conf: float = 0.0,
    parse_conf: float = 0.0,
    validate_conf: float = 0.0,
) -> ExtractionConfidence:
    """
    Build ExtractionConfidence with capped components and calculated overall.
    """
    conf = ExtractionConfidence(
        zone=cap_component(zone_conf, "zone"),
        ocr=cap_component(ocr_conf, "ocr"),
        parse=cap_component(parse_conf, "parse"),
        validate=cap_component(validate_conf, "validate"),
        overall=0.0,  # Will be calculated
    )
    conf = ExtractionConfidence(
        zone=conf.zone,
        ocr=conf.ocr,
        parse=conf.parse,
        validate=conf.validate,
        overall=calculate_overall_confidence(conf),
    )
    return conf


def field_needs_review(field: ExtractedFieldValue) -> bool:
    """
    Determine if a field needs human review based on confidence thresholds.
    """
    threshold = FIELD_CONFIDENCE_THRESHOLDS.get(
        field.field_name,
        DEFAULT_NEEDS_REVIEW_BELOW
    )
    return field.needs_review or field.confidence.overall < threshold


def determine_needs_review(
    extracted_fields: dict[str, ExtractedFieldValue],
    always_review_fields: Optional[set[str]] = None,
) -> tuple[bool, list[str]]:
    """
    Determine if the extraction needs review and collect reasons.

    Returns:
        Tuple of (needs_review, reasons_list)
    """
    reasons: list[str] = []
    always_review_fields = always_review_fields or set()

    for field_name, field_value in extracted_fields.items():
        threshold = FIELD_CONFIDENCE_THRESHOLDS.get(
            field_name, DEFAULT_NEEDS_REVIEW_BELOW,
        )
        if field_name in always_review_fields:
            reasons.append(f"Field '{field_name}' requires review under the template policy")
        elif field_value.parse_success is False:
            reasons.append(f"Field '{field_name}' could not be parsed using the template rule")
        elif field_value.validation_passed is False:
            reasons.append(f"Field '{field_name}' failed template validation")
        elif field_value.needs_review and field_value.confidence.overall >= threshold:
            reasons.append(f"Field '{field_name}' requires human review")
        elif field_needs_review(field_value):
            reasons.append(
                f"Field '{field_name}' confidence {field_value.confidence.overall:.2f} "
                f"below threshold {threshold:.2f}"
            )

    # Check if any required fields are missing
    # (This would be enhanced with template-specific required field checking)

    return len(reasons) > 0, reasons


def confidence_for_generic_extraction(
    pattern_confidence: float,
    match_quality: float,
) -> ExtractionConfidence:
    """
    Build confidence for generic (non-template) extraction.

    Generic extraction doesn't use zones, so zone confidence is 0.
    """
    # Generic uses pattern matching, so we attribute to parse confidence.
    # Zone is always 0 for generic; redistribute its budget across other components
    # so a high-confidence single-candidate match can reach ~0.87+.
    return build_extraction_confidence(
        zone_conf=0.0,
        ocr_conf=0.40 * match_quality,
        parse_conf=0.35 * pattern_confidence,
        validate_conf=0.25 * match_quality,
    )


def confidence_for_zone_extraction(
    zone_match_quality: float,
    ocr_confidence: float,
    parse_success: bool,
    validation_passed: bool,
) -> ExtractionConfidence:
    """
    Build confidence for template zone-based extraction.
    """
    return build_extraction_confidence(
        zone_conf=0.35 * zone_match_quality,
        ocr_conf=0.25 * ocr_confidence,
        parse_conf=0.20 if parse_success else 0.0,
        validate_conf=0.20 if validation_passed else 0.0,
    )
