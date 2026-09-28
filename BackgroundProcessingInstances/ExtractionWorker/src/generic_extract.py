"""
Generic field extraction using regex patterns.

Fallback extraction when no template matches or to supplement zone extraction.
"""

import re
from typing import Optional

from shared.models import (
    CANONICAL_FIELDS,
    DEFAULT_NEEDS_REVIEW_BELOW,
    MULTIPLE_CANDIDATE_MATCH_QUALITY,
    ExtractedFieldValue,
    GenericExtractionResult,
    GenericFieldCandidate,
    NormalizedDocument,
)

from .confidence import confidence_for_generic_extraction

MAX_GENERIC_TEXT_CHARS = 200_000
MAX_GENERIC_CANDIDATES_PER_FIELD = 25
MAX_GENERIC_PAGES = 50


# Words that should not be extracted as field values (common labels/headers)
INVALID_VALUE_WORDS = {
    "name", "holder", "issued", "to", "by", "certificate", "certification",
    "license", "credential", "number", "no", "date", "type", "class",
    "endorsements", "expiration", "expires", "valid", "until", "thru",
    "authority", "authorized", "training", "hours", "of", "the", "and",
    "for", "in", "this", "that", "certifies", "completion", "awarded",
}


def _is_valid_extracted_value(field_name: str, value: str) -> bool:
    """
    Check if an extracted value is valid (not just a label word).

    Args:
        field_name: Name of the field being extracted
        value: Extracted value to validate

    Returns:
        True if value appears valid, False if it's likely just a label
    """
    if not value or len(value.strip()) < 2:
        return False

    # Clean and lowercase for comparison
    cleaned = value.strip().lower()

    # Reject single words that are common labels
    words = cleaned.split()
    if len(words) == 1 and words[0] in INVALID_VALUE_WORDS:
        return False

    # Reject if all words are invalid label words
    if all(w in INVALID_VALUE_WORDS for w in words):
        return False

    # Field-specific validations
    if field_name == "certificate_holder_name":
        # Names should have at least 2 words (first + last)
        if len(words) < 2:
            return False
        # Names shouldn't start with common header words
        if words[0] in {"certificate", "certification", "this", "the"}:
            return False

    if field_name == "certificate_number":
        # Numbers should contain at least one digit
        if not any(c.isdigit() for c in value):
            return False
        # Reject partial word matches from "CERTIFICATE"
        if cleaned in {"ificate", "icate", "cate", "ertificate", "rtificate", "tificate"}:
            return False

    if field_name in {"issue_date", "expiration_date"}:
        # Dates must contain digits
        if not any(c.isdigit() for c in value):
            return False

    if field_name == "training_hours":
        # Hours must be numeric
        try:
            float(value.replace(",", ""))
        except ValueError:
            return False

    return True


def _clean_extracted_value(field_name: str, value: str) -> str:
    """
    Clean up an extracted value.

    Args:
        field_name: Name of the field
        value: Raw extracted value

    Returns:
        Cleaned value
    """
    # Remove leading/trailing whitespace and newlines
    cleaned = value.strip()

    # For most fields, take only the first line
    if field_name in {"issuing_authority", "certificate_type", "certificate_holder_name"}:
        cleaned = cleaned.split("\n")[0].strip()

    # Remove trailing punctuation for names and authorities
    if field_name in {"certificate_holder_name", "issuing_authority"}:
        cleaned = cleaned.rstrip(".,;:")

    return cleaned


# Regex patterns for each canonical field
# Patterns are ordered by specificity/confidence - higher confidence patterns first
# Each pattern is (regex, base_confidence)
GENERIC_FIELD_PATTERNS = {
    "certificate_holder_name": [
        # Explicit label followed by proper name (First Middle? Last)
        (r"(?:NAME|HOLDER|ISSUED TO|AWARDED TO)[:\s]+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", 0.9),
        # "certifies that" followed by name on same or next line
        (r"(?:CERTIFIES THAT|THIS IS TO CERTIFY THAT)[:\s\n]*([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)", 0.85),
        # Name pattern: First Last or First Middle Last (standalone line)
        (r"^([A-Z][a-z]+\s+(?:[A-Z]\.?\s+)?[A-Z][a-z]+)$", 0.6),
    ],
    "certificate_type": [
        # Known certificate type names (highest confidence)
        (r"\b(COMMERCIAL\s+DRIVER(?:'?S)?\s+LICENSE|CDL\s+CLASS\s+[ABC]|CDL)\b", 0.95),
        (r"\b(CPR(?:\s+AND\s+AED)?|FIRST\s+AID(?:\s+AND\s+CPR)?|BLS|ACLS)\b", 0.95),
        (r"\b(HAZMAT|HAZARDOUS\s+MATERIALS?)\b", 0.95),
        (r"\b(FORKLIFT|OSHA\s+\d+|CONFINED\s+SPACE)\b", 0.9),
        # CERTIFICATION/CERTIFICATE followed by type (stop at newline)
        (r"(?:CERTIFICATION|CERTIFICATE)[:\s]+(?:OF|FOR|IN)?[:\s]*([A-Za-z][A-Za-z\s\-&]{3,40}?)(?:\n|$)", 0.75),
    ],
    "certificate_number": [
        # Common certificate number formats (highest priority)
        (r"\b(CERT-\d{4}-\d{4,6})\b", 0.95),
        (r"\b([A-Z]{2,4}-\d{4}-\d{4,6})\b", 0.9),
        (r"\b(TX-CDL-\d{6,10})\b", 0.95),
        # Explicit "NO", "NUMBER", or "#" label (require the label word)
        (r"(?:CERT(?:IFICATE)?|LICENSE|CREDENTIAL)\s*(?:NO\.?|NUMBER|#)[:\s]*([A-Z0-9][\w\-]{4,19})", 0.9),
        (r"(?:NO\.?|NUMBER|#)[:\s]*([A-Z0-9][\w\-]{4,19})", 0.85),
        # ID/Credential number patterns
        (r"(?:ID|CREDENTIAL)\s*(?:NO\.?|NUMBER|#)?[:\s]*([A-Z0-9][\w\-]{5,15})", 0.8),
    ],
    "issuing_authority": [
        # Known issuing organizations (highest confidence)
        (r"\b(AMERICAN RED CROSS)\b", 0.95),
        (r"\b(AMERICAN HEART ASSOCIATION)\b", 0.95),
        (r"\b(TEXAS\s+DEPARTMENT\s+OF\s+[A-Z][A-Za-z\s]+)", 0.9),
        (r"\b(DEPARTMENT\s+OF\s+[A-Z][A-Za-z\s]{5,30})", 0.85),
        (r"\b([A-Z][A-Za-z]+\s+COMMISSION)\b", 0.8),
        # Explicit label followed by org name (stop at newline)
        (r"(?:ISSUED BY|ISSUING AUTHORITY|AUTHORIZED BY|ISSUED UNDER)[:\s]+([A-Za-z][A-Za-z\s\-&,]{4,60}?)(?:\n|$)", 0.85),
    ],
    "issue_date": [
        # Explicit date labels with MM/DD/YYYY or MM-DD-YYYY format
        (r"(?:ISSUE\s*DATE|DATE\s*ISSUED|ISSUED|EFFECTIVE\s*DATE)[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", 0.95),
        # Date labels with Month DD, YYYY format
        (r"(?:ISSUE\s*DATE|DATE\s*ISSUED|ISSUED)[:\s]*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", 0.9),
        # ISO format YYYY-MM-DD with label
        (r"(?:ISSUE\s*DATE|DATE\s*ISSUED|ISSUED)[:\s]*(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})", 0.85),
    ],
    "expiration_date": [
        # Explicit expiration labels with MM/DD/YYYY format
        (r"(?:EXPIR(?:ATION)?\s*DATE|EXPIRES?|VALID\s*(?:UNTIL|THRU|THROUGH))[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", 0.95),
        # Expiration with Month DD, YYYY format
        (r"(?:EXPIR(?:ATION)?\s*DATE|EXPIRES?|VALID\s*(?:UNTIL|THRU))[:\s]*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", 0.9),
        # ISO format YYYY-MM-DD with label
        (r"(?:EXPIR(?:ATION)?\s*DATE|EXPIRES?)[:\s]*(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})", 0.85),
    ],
    "training_hours": [
        # Explicit hours label
        (r"(?:TRAINING\s*HOURS?|COURSE\s*HOURS?|HOURS?\s*OF\s*TRAINING)[:\s]*(\d+(?:\.\d+)?)", 0.9),
        # Number followed by HOURS
        (r"\b(\d+(?:\.\d+)?)\s*(?:HOURS?|HRS?)(?:\s+OF\s+TRAINING)?\b", 0.8),
        # Hours in parentheses
        (r"\((\d+(?:\.\d+)?)\s*(?:HOURS?|HRS?)\)", 0.75),
    ],
    "license_class": [
        # Explicit class label
        (r"(?:LICENSE\s*CLASS|CLASS)[:\s]*([A-C])\b", 0.95),
        # CDL Class pattern
        (r"\bCDL\s+CLASS\s+([A-C])\b", 0.95),
        (r"\bCLASS\s+([A-C])\s+(?:CDL|LICENSE)\b", 0.9),
    ],
    "endorsements": [
        # Standard endorsement codes
        (r"(?:ENDORSEMENTS?)[:\s]*([HPTNSX][,\s]*(?:[HPTNSX][,\s]*)*)", 0.9),
        # Endorsement with descriptive text
        (r"(?:ENDORSEMENTS?)[:\s]*([A-Z](?:[,\s]+[A-Z])*)\b", 0.7),
    ],
}


class GenericExtractor:
    """Extracts fields using generic regex patterns."""

    def __init__(self, patterns: Optional[dict] = None):
        """
        Initialize extractor with patterns.

        Args:
            patterns: Custom patterns dict (defaults to GENERIC_FIELD_PATTERNS)
        """
        self.patterns = patterns or GENERIC_FIELD_PATTERNS

    def extract_all_fields(
        self,
        document: NormalizedDocument,
    ) -> dict[str, ExtractedFieldValue]:
        """
        Extract all canonical fields using generic patterns.

        Args:
            document: Normalized document

        Returns:
            Dict of field_name -> ExtractedFieldValue
        """
        fields, _ = self.extract_fields_and_review_assist(document)
        return fields

    def extract_fields_and_review_assist(
        self,
        document: NormalizedDocument,
        page_num: Optional[int] = None,
    ) -> tuple[dict[str, ExtractedFieldValue], dict]:
        """Extract a coherent field set from one bounded supporting page."""
        if document.pages:
            pages = document.pages[:MAX_GENERIC_PAGES]
            if page_num is not None:
                pages = [page for page in pages if page.page_num == page_num]
            if not pages:
                return {}, {}

            page_results = [
                self._extract_text(page.page_text, page.page_num)
                for page in pages
            ]
            return max(
                page_results,
                key=lambda result: (
                    len(result[0]),
                    sum(field.confidence.overall for field in result[0].values()),
                    -next(
                        (
                            field.source_page_num
                            for field in result[0].values()
                            if field.source_page_num is not None
                        ),
                        0,
                    ),
                ),
            )

        return self._extract_text(document.searchable_text.full_text, None)

    def _extract_text(
        self,
        raw_text: str,
        source_page_num: Optional[int],
    ) -> tuple[dict[str, ExtractedFieldValue], dict]:
        """Extract fields and alternatives from one text boundary."""
        text = self._bounded_text(raw_text)
        fields: dict[str, ExtractedFieldValue] = {}
        assist: dict = {}

        for field_name in CANONICAL_FIELDS:
            result = self._extract_field(text, field_name)
            if result.best_candidate:
                fields[field_name] = self._candidate_to_field_value(
                    result.best_candidate,
                    result,
                    source_page_num,
                )
            if result.all_candidates:
                assist[field_name] = {
                    "candidates": [
                        {
                            "value": candidate.value,
                            "confidence": candidate.confidence,
                            "pattern": candidate.pattern_name,
                            "page": source_page_num,
                        }
                        for candidate in result.all_candidates[:5]
                    ],
                }

        return fields, assist

    def extract_field(
        self,
        text: str,
        field_name: str,
    ) -> GenericExtractionResult:
        """
        Extract a single field using patterns.

        Args:
            text: Document text
            field_name: Field to extract

        Returns:
            GenericExtractionResult with candidates
        """
        return self._extract_field(self._bounded_text(text), field_name)

    @staticmethod
    def _bounded_text(text: str) -> str:
        """Keep representative head/tail text while bounding regex work."""
        if len(text) <= MAX_GENERIC_TEXT_CHARS:
            return text
        head_size = (MAX_GENERIC_TEXT_CHARS * 3) // 4
        tail_size = MAX_GENERIC_TEXT_CHARS - head_size
        return f"{text[:head_size]}\n{text[-tail_size:]}"

    def _extract_field(
        self,
        text: str,
        field_name: str,
    ) -> GenericExtractionResult:
        patterns = self.patterns.get(field_name, [])
        candidates: list[GenericFieldCandidate] = []
        seen_values: set[str] = set()  # Deduplicate candidates
        candidate_limit_reached = False

        for pattern, base_confidence in patterns:
            try:
                matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    # Get the captured group (or full match)
                    value = match.group(1) if match.lastindex else match.group(0)

                    # Clean the value
                    value = _clean_extracted_value(field_name, value)

                    # Skip invalid values
                    if not value or not _is_valid_extracted_value(field_name, value):
                        continue

                    # Skip duplicates (case-insensitive)
                    value_lower = value.lower()
                    if value_lower in seen_values:
                        continue
                    seen_values.add(value_lower)

                    candidate = GenericFieldCandidate(
                        field_name=field_name,
                        value=value,
                        confidence=base_confidence,
                        match_span=(match.start(), match.end()),
                        pattern_name=pattern[:30],
                    )
                    candidates.append(candidate)
                    if len(candidates) >= MAX_GENERIC_CANDIDATES_PER_FIELD:
                        candidate_limit_reached = True
                        break
            except re.error:
                continue
            if candidate_limit_reached:
                break

        # Sort by confidence (highest first)
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        return GenericExtractionResult(
            field_name=field_name,
            best_candidate=candidates[0] if candidates else None,
            all_candidates=candidates,
        )

    def _candidate_to_field_value(
        self,
        candidate: GenericFieldCandidate,
        result: GenericExtractionResult,
        source_page_num: Optional[int] = None,
    ) -> ExtractedFieldValue:
        """Convert a candidate to ExtractedFieldValue."""
        # Calculate match quality based on number of alternatives
        match_quality = 1.0 if len(result.all_candidates) == 1 else MULTIPLE_CANDIDATE_MATCH_QUALITY

        confidence = confidence_for_generic_extraction(
            pattern_confidence=candidate.confidence,
            match_quality=match_quality,
        )

        return ExtractedFieldValue(
            field_name=candidate.field_name,
            value=candidate.value,
            confidence=confidence,
            extraction_source="generic",
            needs_review=confidence.overall < DEFAULT_NEEDS_REVIEW_BELOW,
            source_page_num=source_page_num,
        )

    def build_review_assist(
        self,
        document: NormalizedDocument,
    ) -> dict:
        """
        Build review assist data showing all extraction candidates.

        Args:
            document: Normalized document

        Returns:
            Dict with field alternatives for reviewer
        """
        _, assist = self.extract_fields_and_review_assist(document)
        return assist
