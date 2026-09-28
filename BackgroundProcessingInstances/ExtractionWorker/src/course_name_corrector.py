"""
Course/certificate type name correction against known canonical names.

Matches noisy OCR-extracted certificate_type text against a pool of known
course names using substring containment and word-overlap scoring.
"""

import re
import unicodedata
from typing import Optional

from shared.models import ExtractedFieldValue


# Canonical course names from City of Laredo Public Health Department
# Source: SimulationForTesting/config/roles.json + DB seed data (migrations 002/004)
CANONICAL_COURSE_NAMES = [
    "Sexual Harassment & Other Harassment Prevention Training",
    "Workplace Violence Prevention Training",
    "HIPAA Privacy & Security Training",
    "Bloodborne Pathogens Training",
    "CPR / Basic Life Support (BLS)",
    "Registered Nurse (RN) License",
    "Licensed Vocational Nurse (LVN) License",
    "Texas Community Health Worker (CHW) Certification",
    "Registered Sanitarian (RS) / REHS License",
    "Commercial Pesticide Applicator License",
    "FEMA ICS / NIMS Training",
    "Hazard Communication (HazCom) Training",
    "Respiratory Protection & N95 Fit Testing",
    "WIC Civil Rights Training",
    "Vaccines for Children (VFC) Program Training",
    "Commercial Driver License (CDL)",
    "First Aid & CPR Certification",
    "Hazmat Transportation Certification",
]

NEGATION_PATTERN = re.compile(
    r"\b(?:not|no|without|exclude[ds]?|excluding|incomplete|did\s+not)\b",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison.

    Lowercase, remove accents/diacritics, remove punctuation, normalize whitespace.
    """
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text)
    text = " ".join(text.split())
    return text.strip()


def find_best_course_match(
    extracted_text: str,
    canonical_names: Optional[list[str]] = None,
    word_overlap_threshold: float = 0.7,
) -> tuple[Optional[str], float]:
    """
    Find the best matching canonical course name for extracted text.

    Strategy:
    1. Substring containment (highest confidence) — pick longest match
    2. Word-overlap scoring (fallback) — fraction of canonical words in extracted text

    Args:
        extracted_text: Raw extracted certificate_type text
        canonical_names: List of canonical names (defaults to CANONICAL_COURSE_NAMES)
        word_overlap_threshold: Minimum word overlap ratio for fallback matching

    Returns:
        (canonical_name, confidence) or (None, 0.0) if no match
    """
    if not extracted_text:
        return None, 0.0

    if canonical_names is None:
        canonical_names = CANONICAL_COURSE_NAMES

    norm_extracted = normalize_text(extracted_text)
    if not norm_extracted:
        return None, 0.0
    if NEGATION_PATTERN.search(norm_extracted):
        return None, 0.0

    # Phase 1: Substring containment — check if canonical name appears inside extracted text
    substring_matches: list[tuple[str, int]] = []
    for canonical in canonical_names:
        norm_canonical = normalize_text(canonical)
        if norm_canonical and norm_canonical == norm_extracted:
            return canonical, 1.0
        if norm_canonical and norm_canonical in norm_extracted:
            substring_matches.append((canonical, len(norm_canonical)))

    if substring_matches:
        # Pick the longest match (most specific)
        substring_matches.sort(key=lambda x: x[1], reverse=True)
        return substring_matches[0][0], 0.9

    # Phase 2: Word-overlap scoring
    extracted_words = set(norm_extracted.split())
    best_match: Optional[str] = None
    best_score = 0.0

    for canonical in canonical_names:
        norm_canonical = normalize_text(canonical)
        canonical_words = set(norm_canonical.split())
        if not canonical_words:
            continue

        # Count how many canonical words appear in extracted text
        overlap = canonical_words & extracted_words
        score = len(overlap) / len(canonical_words)

        if score >= word_overlap_threshold and score > best_score:
            best_score = score
            best_match = canonical

    if best_match:
        return best_match, best_score

    return None, 0.0


def correct_certificate_type_field(
    extracted_fields: dict[str, ExtractedFieldValue],
) -> dict[str, ExtractedFieldValue]:
    """
    Correct certificate_type field value against known course names.

    Modifies the ExtractedFieldValue in place if a match is found.

    Args:
        extracted_fields: Dict of field_name -> ExtractedFieldValue

    Returns:
        Same dict (modified in place)
    """
    if "certificate_type" not in extracted_fields:
        return extracted_fields

    field = extracted_fields["certificate_type"]
    if not field.value:
        return extracted_fields

    canonical_name, match_confidence = find_best_course_match(field.value)
    if canonical_name and match_confidence == 1.0:
        field.value = canonical_name
    elif canonical_name or NEGATION_PATTERN.search(normalize_text(field.value)):
        field.needs_review = True

    return extracted_fields
