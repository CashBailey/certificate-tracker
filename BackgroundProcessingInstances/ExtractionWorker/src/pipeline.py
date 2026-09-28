"""
Extraction pipeline orchestrator.

Ties together all extraction stages: normalization, template identification,
zone extraction, generic extraction, and confidence calculation.
"""

import asyncio
import logging
import os
from typing import Optional

from shared.models import (
    DocumentToken,
    ExtractionRun,
    ExtractedFieldValue,
    ReviewState,
)
from shared.template_registry import JsonTemplateRegistry

from .confidence import determine_needs_review
from .generic_extract import GenericExtractor
from .identify import TemplateIdentifier
from .normalize import DocumentNormalizer
from .pdf_text import DocumentLimitError
from .zone_extract import ZoneExtractor

log = logging.getLogger(__name__)
EXTRACTION_DEADLINE_SECONDS = 300


class ExtractionPipeline:
    """
    Main extraction pipeline orchestrator.

    Coordinates the full extraction process from raw document to extraction run.
    """

    def __init__(
        self,
        templates_dir: Optional[str] = None,
        ocr_client=None,
    ):
        """
        Initialize extraction pipeline.

        Args:
            templates_dir: Path to templates directory
            ocr_client: Optional OCR client for scanned documents
        """
        # Resolve templates directory
        if templates_dir is None:
            templates_dir = os.getenv(
                "TEMPLATES_DIR",
                "/app/templates"
            )

        self.registry = JsonTemplateRegistry(templates_dir)
        self.normalizer = DocumentNormalizer()
        self.identifier = TemplateIdentifier(self.registry)
        self.ocr_client = ocr_client
        self.zone_extractor = ZoneExtractor(ocr_client=ocr_client)
        self.generic_extractor = GenericExtractor()

    async def run_extraction(
        self,
        document_id: int,
        file_bytes: bytes,
        file_type: str,
    ) -> ExtractionRun:
        """Run extraction within a hard end-to-end async deadline."""
        try:
            async with asyncio.timeout(EXTRACTION_DEADLINE_SECONDS):
                return await self._run_extraction(document_id, file_bytes, file_type)
        except TimeoutError as exc:
            raise DocumentLimitError(
                f"Extraction exceeded {EXTRACTION_DEADLINE_SECONDS} seconds",
            ) from exc

    async def _run_extraction(
        self,
        document_id: int,
        file_bytes: bytes,
        file_type: str,
    ) -> ExtractionRun:
        """
        Run the full extraction pipeline on a document.

        Args:
            document_id: ID of the document record
            file_bytes: Raw file bytes
            file_type: MIME type of the file

        Returns:
            ExtractionRun with results
        """
        # 1. Normalize document
        if file_type == "application/pdf":
            document = self.normalizer.normalize_pdf(file_bytes)
        else:
            document = self.normalizer.normalize_image(file_bytes)

        # 1.5. Run full-page OCR for scanned/image pages
        for page in document.pages:
            if not page.is_digital and page.raster and self.ocr_client:
                try:
                    text_spans = await self.ocr_client.ocr_region_async(
                        page.raster,
                        (0.0, 0.0, 1.0, 1.0),  # Full page
                    )
                    ocr_tokens = [
                        DocumentToken(
                            token_id=f"ocr_fullpage_{page.page_num}_{i}",
                            text=span.text,
                            bbox_norm=span.bbox_norm,
                            page_num=page.page_num,
                            confidence=span.confidence,
                        )
                        for i, span in enumerate(text_spans)
                    ]
                    document = self.normalizer.update_with_ocr_tokens(
                        document, page.page_num, ocr_tokens
                    )
                except Exception as e:
                    log.warning("Full-page OCR failed for page %d: %s", page.page_num, e)

        # 2. Identify template
        template, use_generic, match_evidence = self.identifier.identify_with_fallback(
            document
        )

        # 3. Extract fields
        supporting_page = None
        if template and not use_generic:
            supporting_page = self.zone_extractor.select_supporting_page(
                document,
                template,
                preferred_page_num=match_evidence.get("page_num"),
            )
            # Zone-based extraction
            extracted_fields = await self.zone_extractor.extract_zones(
                document,
                template,
                supporting_page=supporting_page,
            )

            # Generic supplementation stays on the same evidence page.
            generic_fields, review_assist = (
                self.generic_extractor.extract_fields_and_review_assist(
                    document,
                    page_num=supporting_page.page_num if supporting_page else None,
                )
            )

            # Supplement with generic extraction for missing fields
            for field_name, field_value in generic_fields.items():
                if field_name not in extracted_fields:
                    extracted_fields[field_name] = field_value
        else:
            # Pure generic extraction
            extracted_fields, review_assist = (
                self.generic_extractor.extract_fields_and_review_assist(document)
            )
            selected_page_num = next(
                (
                    field.source_page_num
                    for field in extracted_fields.values()
                    if field.source_page_num is not None
                ),
                None,
            )
            supporting_page = next(
                (
                    page
                    for page in document.pages
                    if page.page_num == selected_page_num
                ),
                document.pages[0] if document.pages else None,
            )

        # 3.5. Correct certificate_type against known course names
        from .course_name_corrector import correct_certificate_type_field
        extracted_fields = correct_certificate_type_field(extracted_fields)

        # 3.6. LLM field cleanup (if Ollama available)
        from .llm_client import llm_clean_fields
        llm_text = (
            supporting_page.page_text
            if supporting_page
            else document.searchable_text.full_text
        )
        extracted_fields = await llm_clean_fields(
            llm_text,
            extracted_fields,
        )

        # 5. Determine if needs review
        always_review_fields = (
            set(template.review_rules.always_review_fields)
            if template and not use_generic
            else set()
        )
        needs_review, review_reasons = determine_needs_review(
            extracted_fields,
            always_review_fields=always_review_fields,
        )

        # 6. Serialize extracted fields for storage
        serialized_fields = self._serialize_fields(extracted_fields)
        field_evidence = self._serialize_field_evidence(extracted_fields)

        # 7. Build extraction run
        extraction = ExtractionRun(
            id=0,  # Will be set by DB
            document_id=document_id,
            review_state=ReviewState.PENDING_REVIEW,
            extracted_fields=serialized_fields,
            needs_review=needs_review,
            needs_review_reasons=review_reasons,
            template_id=template.template_id if template else None,
            template_version=template.version if template else None,
            template_match_evidence=match_evidence,
            review_assist=review_assist,
            field_evidence=field_evidence or None,
        )

        return extraction

    def _serialize_fields(
        self,
        fields: dict[str, ExtractedFieldValue],
    ) -> dict:
        """Serialize extracted fields to JSON-compatible dict."""
        result = {}
        for field_name, field_value in fields.items():
            result[field_name] = {
                "value": field_value.value,
                "confidence": {
                    "zone": field_value.confidence.zone,
                    "ocr": field_value.confidence.ocr,
                    "parse": field_value.confidence.parse,
                    "validate": field_value.confidence.validate,
                    "overall": field_value.confidence.overall,
                },
                "extraction_source": field_value.extraction_source,
                "needs_review": field_value.needs_review,
            }
        return result

    def _serialize_field_evidence(
        self,
        fields: dict[str, ExtractedFieldValue],
    ) -> dict[str, dict]:
        """Preserve the source page and validation evidence behind fields."""
        evidence: dict[str, dict] = {}
        for field_name, field_value in fields.items():
            if field_value.source_page_num is None:
                continue
            item = {
                "page": field_value.source_page_num,
                "source": field_value.extraction_source,
                "parse_success": field_value.parse_success,
                "validation_passed": field_value.validation_passed,
            }
            if field_value.source_bbox_norm is not None:
                item["bbox"] = list(field_value.source_bbox_norm)
                item["zone_id"] = field_name
            evidence[field_name] = item
        return evidence
