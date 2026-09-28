"""
Zone-based extraction for template-matched documents.

Extracts field values from defined zones in templates.
"""

import re
from datetime import datetime
from typing import Optional

from shared.models import (
    DEFAULT_NEEDS_REVIEW_BELOW,
    DocumentToken,
    ExtractionConfidence,
    ExtractedFieldValue,
    FieldZone,
    NormalizedDocument,
    NormalizedPage,
    TemplateDefinition,
)
from shared.utils import span_belongs_to_zone

from .confidence import confidence_for_zone_extraction


class ZoneExtractor:
    """Extracts field values from template zones."""

    def __init__(self, ocr_client=None):
        """
        Initialize zone extractor.

        Args:
            ocr_client: Optional OCR client for scanned regions
        """
        self.ocr_client = ocr_client

    async def extract_zones(
        self,
        document: NormalizedDocument,
        template: TemplateDefinition,
        supporting_page: Optional[NormalizedPage] = None,
    ) -> dict[str, ExtractedFieldValue]:
        """
        Extract all zones defined in template.

        Args:
            document: Normalized document
            template: Template with zone definitions

        Returns:
            Dict of field_name -> ExtractedFieldValue
        """
        results: dict[str, ExtractedFieldValue] = {}
        supporting_page = supporting_page or self.select_supporting_page(
            document,
            template,
        )

        for zone in template.zones:
            value = await self._extract_zone(document, zone, supporting_page)
            results[zone.field_name] = value

        return results

    async def _extract_zone(
        self,
        document: NormalizedDocument,
        zone: FieldZone,
        supporting_page: Optional[NormalizedPage] = None,
    ) -> ExtractedFieldValue:
        """
        Extract a single zone.

        Args:
            document: Normalized document
            zone: Zone definition

        Returns:
            ExtractedFieldValue for this zone
        """
        # If zone has a hardcoded value, use it directly (template-authoritative)
        if zone.hardcoded_value:
            return ExtractedFieldValue(
                field_name=zone.field_name,
                value=zone.hardcoded_value,
                confidence=ExtractionConfidence(
                    zone=1.0, ocr=1.0, parse=1.0, validate=1.0, overall=1.0,
                ),
                extraction_source="template_metadata",
                needs_review=False,
            )

        # A template extraction must remain bound to one page. Combining the
        # same coordinates across pages can create a field set that exists on
        # no actual certificate page.
        page = supporting_page or self._select_supporting_page_for_zone(document, zone)
        zone_tokens: list[DocumentToken] = []
        if page:
            zone_tokens = self._get_tokens_in_zone(page.tokens, zone)
            if not zone_tokens and not page.is_digital and page.raster and self.ocr_client:
                zone_tokens = await self._ocr_zone(page, zone)

        # Parse zone text
        raw_text = " ".join(t.text for t in zone_tokens).strip()
        parsed_value, parse_success = self._parse_zone_value(raw_text, zone)

        # Validate
        validation_passed = self._validate_zone_value(parsed_value, zone)

        # Calculate confidence
        zone_match_quality = 1.0 if zone_tokens else 0.0
        avg_ocr_conf = (
            sum(t.confidence for t in zone_tokens) / len(zone_tokens)
            if zone_tokens else 0.0
        )

        confidence = confidence_for_zone_extraction(
            zone_match_quality=zone_match_quality,
            ocr_confidence=avg_ocr_conf,
            parse_success=parse_success,
            validation_passed=validation_passed,
        )

        return ExtractedFieldValue(
            field_name=zone.field_name,
            value=parsed_value,
            confidence=confidence,
            extraction_source="zone",
            needs_review=(
                not parse_success
                or not validation_passed
                or confidence.overall < DEFAULT_NEEDS_REVIEW_BELOW
            ),
            source_page_num=page.page_num if page else None,
            source_bbox_norm=zone.bbox_norm,
            parse_success=parse_success,
            validation_passed=validation_passed,
        )

    def select_supporting_page(
        self,
        document: NormalizedDocument,
        template: TemplateDefinition,
        preferred_page_num: Optional[int] = None,
    ) -> Optional[NormalizedPage]:
        """Choose one deterministic page with the strongest zone coverage."""
        if not document.pages:
            return None
        if preferred_page_num is not None:
            preferred = next(
                (
                    page
                    for page in document.pages
                    if page.page_num == preferred_page_num
                ),
                None,
            )
            if preferred:
                return preferred

        def page_score(page: NormalizedPage) -> tuple[int, int, float, int]:
            matching = [
                self._get_tokens_in_zone(page.tokens, zone)
                for zone in template.zones
                if not zone.hardcoded_value
            ]
            populated_zones = sum(bool(tokens) for tokens in matching)
            token_count = sum(len(tokens) for tokens in matching)
            confidence = sum(token.confidence for tokens in matching for token in tokens)
            # Prefer the earliest page for an otherwise exact tie.
            return populated_zones, token_count, confidence, -page.page_num

        return max(document.pages, key=page_score)

    def _select_supporting_page_for_zone(
        self,
        document: NormalizedDocument,
        zone: FieldZone,
    ) -> Optional[NormalizedPage]:
        """Select one page for direct single-zone calls without merging pages."""
        if not document.pages:
            return None
        return max(
            document.pages,
            key=lambda page: (
                len(self._get_tokens_in_zone(page.tokens, zone)),
                sum(
                    token.confidence
                    for token in self._get_tokens_in_zone(page.tokens, zone)
                ),
                -page.page_num,
            ),
        )

    def _get_tokens_in_zone(
        self,
        tokens: list[DocumentToken],
        zone: FieldZone,
    ) -> list[DocumentToken]:
        """Get tokens that fall within a zone's bounding box."""
        return [
            t for t in tokens
            if span_belongs_to_zone(t.bbox_norm, zone.bbox_norm, tolerance=0.02)
        ]

    async def _ocr_zone(
        self,
        page: NormalizedPage,
        zone: FieldZone,
    ) -> list[DocumentToken]:
        """
        Perform OCR on a specific zone of a page.

        Args:
            page: Page with raster image
            zone: Zone to OCR

        Returns:
            List of tokens from OCR
        """
        if not page.raster or not self.ocr_client:
            return []

        try:
            # Call OCR service for this zone
            text_spans = await self.ocr_client.ocr_region_async(
                page.raster,
                zone.bbox_norm,
            )

            # Convert TextSpans to DocumentTokens
            tokens = []
            for i, span in enumerate(text_spans):
                token = DocumentToken(
                    token_id=f"ocr_{page.page_num}_{zone.field_name}_{i}",
                    text=span.text,
                    bbox_norm=span.bbox_norm,
                    page_num=page.page_num,
                    confidence=span.confidence,
                )
                tokens.append(token)

            return tokens
        except Exception:
            return []

    def _parse_zone_value(
        self,
        raw_text: str,
        zone: FieldZone,
    ) -> tuple[Optional[str], bool]:
        """
        Parse raw zone text according to zone parsing rules.

        Returns:
            Tuple of (parsed_value, success)
        """
        if not raw_text:
            return None, False

        text = raw_text

        # Strip whitespace if configured
        if zone.parsing.strip_whitespace:
            text = text.strip()

        # Apply regex pattern if specified
        if zone.parsing.regex_pattern:
            match = re.search(zone.parsing.regex_pattern, text, re.IGNORECASE)
            if match:
                text = match.group(1) if match.lastindex else match.group(0)
            else:
                return text, False  # Pattern didn't match

        # Parse date if date_format specified
        if zone.parsing.date_format:
            try:
                parsed_date = datetime.strptime(text, zone.parsing.date_format)
                text = parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                # Try common formats as fallback
                for fmt in ["%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%B %d, %Y"]:
                    try:
                        parsed_date = datetime.strptime(text, fmt)
                        text = parsed_date.strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
                else:
                    return text, False

        return text, True

    def _validate_zone_value(
        self,
        value: Optional[str],
        zone: FieldZone,
    ) -> bool:
        """
        Validate parsed value against zone validators.

        Returns:
            True if validation passes
        """
        if value is None:
            return not zone.required

        validators = zone.validators

        # Check min length
        if validators.min_length and len(value) < validators.min_length:
            return False

        # Check max length
        if validators.max_length and len(value) > validators.max_length:
            return False

        # Check regex match
        if validators.regex_match:
            if not re.match(validators.regex_match, value):
                return False

        # Check date range
        if validators.date_range:
            try:
                date_val = datetime.strptime(value, "%Y-%m-%d")
                min_date = datetime.strptime(validators.date_range[0], "%Y-%m-%d")
                max_date = datetime.strptime(validators.date_range[1], "%Y-%m-%d")
                if not (min_date <= date_val <= max_date):
                    return False
            except ValueError:
                return False

        return True
