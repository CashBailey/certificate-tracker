"""
Name matching utilities for certificate holder verification.

Provides fuzzy matching to compare extracted certificate holder names
against employee directory names, accounting for ordering variations
and minor spelling differences.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

MAX_NAME_LENGTH = 200
MAX_NAME_PART_LENGTH = 100
MAX_NAME_PARTS = 8


@dataclass
class NameMatchResult:
    """Result of a name matching comparison."""
    is_match: bool
    confidence: float  # 0.0 to 1.0
    mismatch_reason: Optional[str] = None


def normalize_name(name: str) -> str:
    """
    Normalize a name for comparison.

    - Converts to lowercase
    - Removes accents/diacritics
    - Removes punctuation
    - Normalizes whitespace

    Args:
        name: Name string to normalize

    Returns:
        Normalized name string
    """
    if not name:
        return ""

    # Convert to lowercase
    name = name.lower()

    # Remove accents/diacritics (normalize to ASCII)
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))

    # Remove common suffixes (Jr., Sr., III, etc.)
    name = re.sub(r'\b(jr\.?|sr\.?|iii?|iv|v)\b', '', name, flags=re.IGNORECASE)

    # Remove punctuation but keep spaces
    name = re.sub(r'[^\w\s]', '', name)

    # Normalize whitespace
    name = ' '.join(name.split())

    return name.strip()


def extract_name_parts(name: str) -> set[str]:
    """
    Extract individual name parts as a set.

    Args:
        name: Normalized name string

    Returns:
        Set of name parts
    """
    if not name:
        return set()

    parts = name.split()[:MAX_NAME_PARTS]
    # Filter out very short parts (likely initials)
    return {p for p in parts if len(p) > 1}


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein edit distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Edit distance (number of insertions, deletions, substitutions)
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def fuzzy_part_match(part1: str, part2: str, threshold: float = 0.8) -> bool:
    """
    Check if two name parts are a fuzzy match.

    Uses Levenshtein distance relative to string length.

    Args:
        part1: First name part
        part2: Second name part
        threshold: Minimum similarity ratio (0.0 to 1.0)

    Returns:
        True if parts are similar enough
    """
    if not part1 or not part2:
        return False
    if len(part1) > MAX_NAME_PART_LENGTH or len(part2) > MAX_NAME_PART_LENGTH:
        return False

    # Exact match
    if part1 == part2:
        return True

    # Calculate similarity
    max_len = max(len(part1), len(part2))
    distance = levenshtein_distance(part1, part2)
    similarity = 1.0 - (distance / max_len)

    return similarity >= threshold


def match_names(
    extracted_name: str,
    employee_first_name: str,
    employee_last_name: str,
    strict: bool = False,
) -> NameMatchResult:
    """
    Compare extracted certificate holder name against employee name.

    Handles:
    - Different orderings (First Last, Last First, Last comma First)
    - Case differences
    - Minor spelling variations (via fuzzy matching)
    - Middle names/initials (ignored in matching)

    Args:
        extracted_name: Name extracted from certificate
        employee_first_name: Employee's first name from directory
        employee_last_name: Employee's last name from directory
        strict: If True, require exact match; otherwise use fuzzy matching

    Returns:
        NameMatchResult with match status and confidence
    """
    if not extracted_name:
        return NameMatchResult(
            is_match=False,
            confidence=0.0,
            mismatch_reason="No certificate holder name extracted"
        )

    if (
        len(extracted_name) > MAX_NAME_LENGTH
        or len(employee_first_name) > MAX_NAME_LENGTH
        or len(employee_last_name) > MAX_NAME_LENGTH
    ):
        return NameMatchResult(
            is_match=False,
            confidence=0.0,
            mismatch_reason="Certificate holder name is too long to compare safely",
        )

    if not employee_first_name and not employee_last_name:
        return NameMatchResult(
            is_match=False,
            confidence=0.0,
            mismatch_reason="No employee name available for comparison"
        )

    # Normalize all names
    norm_extracted = normalize_name(extracted_name)
    norm_first = normalize_name(employee_first_name)
    norm_last = normalize_name(employee_last_name)

    # Build expected full name and parts
    expected_full = f"{norm_first} {norm_last}".strip()
    extracted_parts = extract_name_parts(norm_extracted)

    if not extracted_parts:
        return NameMatchResult(
            is_match=False,
            confidence=0.0,
            mismatch_reason="Could not parse certificate holder name"
        )

    # Check for exact full name match (either order)
    if norm_extracted == expected_full:
        return NameMatchResult(is_match=True, confidence=1.0)

    # Check "Last, First" format
    if norm_extracted == f"{norm_last} {norm_first}".strip():
        return NameMatchResult(is_match=True, confidence=1.0)

    # Directory identity is an authorization signal, so only normalized exact
    # first and last name parts can suppress the mismatch control. Fuzzy
    # similarity is useful for reviewer assistance, not identity acceptance.
    first_matched = norm_first in extracted_parts
    last_matched = norm_last in extracted_parts

    # Calculate confidence based on matches
    if first_matched and last_matched:
        return NameMatchResult(is_match=True, confidence=1.0)

    if last_matched and not first_matched:
        # Only last name matches - could be a relative or coincidence
        return NameMatchResult(
            is_match=False,
            confidence=0.3,
            mismatch_reason="Certificate holder first name does not exactly match the employee directory name"
        )

    if first_matched and not last_matched:
        # Only first name matches
        return NameMatchResult(
            is_match=False,
            confidence=0.2,
            mismatch_reason="Certificate holder last name does not exactly match the employee directory name"
        )

    # No match
    return NameMatchResult(
        is_match=False,
        confidence=0.0,
        mismatch_reason="Certificate holder name does not exactly match the employee directory name"
    )


def check_name_mismatch(
    extracted_fields: dict,
    employee_first_name: str,
    employee_last_name: str,
) -> Optional[str]:
    """
    Check if extracted certificate holder name mismatches employee name.

    Convenience function for use in extraction pipeline.

    Args:
        extracted_fields: Dictionary of extracted fields
        employee_first_name: Employee's first name
        employee_last_name: Employee's last name

    Returns:
        Mismatch reason string if names don't match, None if they match
    """
    # Get certificate holder name from extracted fields
    holder_name_field = extracted_fields.get("certificate_holder_name", {})

    if isinstance(holder_name_field, dict):
        holder_name = holder_name_field.get("value")
    else:
        holder_name = holder_name_field

    if not holder_name:
        return None  # No name to compare - don't flag as mismatch

    result = match_names(
        extracted_name=holder_name,
        employee_first_name=employee_first_name,
        employee_last_name=employee_last_name,
    )

    if result.is_match:
        return None

    return result.mismatch_reason
