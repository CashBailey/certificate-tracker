"""
Tests for template-authoritative issuing authority extraction.

Covers:
- Zone extraction returns hardcoded_value when set (skips OCR)
- Zone extraction falls back to OCR when hardcoded_value is None
- LLM cleanup skips fields with extraction_source="template_metadata"
- Template registry loads hardcoded_value from JSON
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Set up import paths (same pattern as test_llm_client.py). Both ApiServer/src
# and ExtractionWorker/src only exist in the host project layout (parents[4]);
# inside the api container, parents[4] is IndexError and ExtractionWorker is not
# mounted. Skip the module gracefully in that case.
try:
    _project_root = Path(__file__).resolve().parents[4]
    _api_src = str(_project_root / "CoreInstances" / "ApiServer" / "src")
    _extraction_src = str(_project_root / "BackgroundProcessingInstances" / "ExtractionWorker" / "src")
    for _p in (_api_src, _extraction_src):
        if _p not in sys.path:
            sys.path.insert(0, _p)

    # zone_extract uses `from .confidence import ...` (relative import) which
    # requires a parent package context. We set up a synthetic package so it works.
    import importlib
    import importlib.util
    import types as _types

    # Create a synthetic parent package for extraction worker modules
    _ext_pkg = _types.ModuleType("_ext_worker")
    _ext_pkg.__path__ = [_extraction_src]
    _ext_pkg.__package__ = "_ext_worker"
    sys.modules["_ext_worker"] = _ext_pkg

    # Load confidence into the package namespace
    _conf_spec = importlib.util.spec_from_file_location(
        "_ext_worker.confidence",
        str(Path(_extraction_src) / "confidence.py"),
        submodule_search_locations=[],
    )
    _conf_mod = importlib.util.module_from_spec(_conf_spec)
    _conf_mod.__package__ = "_ext_worker"
    sys.modules["_ext_worker.confidence"] = _conf_mod
    _conf_spec.loader.exec_module(_conf_mod)

    # Load zone_extract into the package namespace
    _ze_spec = importlib.util.spec_from_file_location(
        "_ext_worker.zone_extract",
        str(Path(_extraction_src) / "zone_extract.py"),
        submodule_search_locations=[],
    )
    _ze_mod = importlib.util.module_from_spec(_ze_spec)
    _ze_mod.__package__ = "_ext_worker"
    sys.modules["_ext_worker.zone_extract"] = _ze_mod
    _ze_spec.loader.exec_module(_ze_mod)

    ZoneExtractor = _ze_mod.ZoneExtractor

    from llm_client import _apply_fields_to_extracted
    from shared.models import (
        DocumentToken,
        ExtractionConfidence,
        ExtractedFieldValue,
        FieldZone,
        NormalizedDocument,
        NormalizedPage,
        SearchableText,
        ZoneParsing,
        ZoneValidators,
    )
    from shared.template_registry import JsonTemplateRegistry
except (IndexError, FileNotFoundError, ModuleNotFoundError) as _import_err:
    pytest.skip(
        f"Requires host project layout with ExtractionWorker on path ({_import_err})",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_zone(
    field_name: str = "issuing_authority",
    hardcoded_value: str | None = None,
) -> FieldZone:
    """Create a FieldZone with optional hardcoded_value."""
    return FieldZone(
        field_name=field_name,
        bbox_norm=(0.45, 0.13, 0.55, 0.32),
        parsing=ZoneParsing(strip_whitespace=True),
        validators=ZoneValidators(),
        required=True,
        hardcoded_value=hardcoded_value,
    )


def _make_document(text: str = "City of Laredo") -> NormalizedDocument:
    """Create a minimal NormalizedDocument with one token."""
    token = DocumentToken(
        token_id="tok_0",
        text=text,
        bbox_norm=(0.46, 0.14, 0.54, 0.20),
        page_num=1,
        confidence=0.95,
    )
    page = NormalizedPage(
        page_num=1,
        tokens=[token],
        page_text=text,
        is_digital=True,
    )
    return NormalizedDocument(
        pages=[page],
        searchable_text=SearchableText(full_text=text, token_map={}),
        total_pages=1,
    )


def _make_field(
    name: str,
    value: str | None,
    source: str = "generic",
) -> ExtractedFieldValue:
    """Create an ExtractedFieldValue with given source."""
    return ExtractedFieldValue(
        field_name=name,
        value=value,
        confidence=ExtractionConfidence(
            zone=0.9, ocr=0.8, parse=0.7, validate=0.6, overall=0.75,
        ),
        extraction_source=source,
        needs_review=False,
    )


# ===========================================================================
# TestZoneExtractorHardcodedValue
# ===========================================================================

class TestZoneExtractorHardcodedValue:
    """Tests for zone extraction with hardcoded_value."""

    @pytest.mark.asyncio
    async def test_returns_hardcoded_value_when_set(self):
        """Zone with hardcoded_value returns it directly, skipping OCR."""
        zone = _make_zone(hardcoded_value="City of Laredo")
        doc = _make_document("SOME OCR GARBAGE TEXT")
        extractor = ZoneExtractor()

        result = await extractor._extract_zone(doc, zone)

        assert result.value == "City of Laredo"
        assert result.extraction_source == "template_metadata"
        assert result.needs_review is False
        assert result.field_name == "issuing_authority"

    @pytest.mark.asyncio
    async def test_hardcoded_value_has_full_confidence(self):
        """Hardcoded value gets perfect confidence scores."""
        zone = _make_zone(hardcoded_value="City of Laredo")
        doc = _make_document()
        extractor = ZoneExtractor()

        result = await extractor._extract_zone(doc, zone)

        assert result.confidence.zone == 1.0
        assert result.confidence.ocr == 1.0
        assert result.confidence.parse == 1.0
        assert result.confidence.validate == 1.0
        assert result.confidence.overall == 1.0

    @pytest.mark.asyncio
    async def test_falls_back_to_ocr_when_no_hardcoded_value(self):
        """Zone without hardcoded_value extracts from OCR tokens as before."""
        zone = _make_zone(hardcoded_value=None)
        doc = _make_document("City of Laredo")
        extractor = ZoneExtractor()

        result = await extractor._extract_zone(doc, zone)

        assert result.value == "City of Laredo"
        assert result.extraction_source == "zone"
        # OCR path: confidence depends on token quality, not perfect 1.0
        assert result.confidence.overall < 1.0

    @pytest.mark.asyncio
    async def test_hardcoded_value_ignores_document_content(self):
        """Hardcoded value is used regardless of what OCR text contains."""
        zone = _make_zone(hardcoded_value="American Red Cross")
        doc = _make_document("OSHA Training Institute")
        extractor = ZoneExtractor()

        result = await extractor._extract_zone(doc, zone)

        assert result.value == "American Red Cross"
        assert result.extraction_source == "template_metadata"

    @pytest.mark.asyncio
    async def test_hardcoded_value_skips_ocr_for_scanned_pages(self):
        """Hardcoded value doesn't trigger OCR even for scanned pages."""
        zone = _make_zone(hardcoded_value="City of Laredo")
        # Create scanned page (is_digital=False) with no tokens
        page = NormalizedPage(
            page_num=1,
            tokens=[],
            page_text="",
            is_digital=False,
            raster=None,
        )
        doc = NormalizedDocument(
            pages=[page],
            searchable_text=SearchableText(full_text="", token_map={}),
            total_pages=1,
        )
        mock_ocr = AsyncMock()
        extractor = ZoneExtractor(ocr_client=mock_ocr)

        result = await extractor._extract_zone(doc, zone)

        assert result.value == "City of Laredo"
        assert result.extraction_source == "template_metadata"
        # OCR should never be called
        mock_ocr.ocr_region_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_zones_uses_hardcoded_for_configured_fields(self):
        """extract_zones() returns hardcoded for configured zones, OCR for others."""
        from shared.models import TemplateDefinition, TemplateDetection, TemplateAlignment, TemplateReviewRules

        template = TemplateDefinition(
            template_id="test_template",
            version=1,
            name="Test",
            description="",
            detection=TemplateDetection(anchor_keywords=[]),
            alignment=TemplateAlignment(reference_anchors=[]),
            zones=[
                _make_zone(hardcoded_value="City of Laredo"),
                FieldZone(
                    field_name="certificate_holder_name",
                    bbox_norm=(0.19, 0.43, 0.80, 0.54),
                    parsing=ZoneParsing(strip_whitespace=True),
                    validators=ZoneValidators(),
                    required=True,
                    hardcoded_value=None,
                ),
            ],
            review_rules=TemplateReviewRules(),
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )

        doc = _make_document("John Smith")
        extractor = ZoneExtractor()

        results = await extractor.extract_zones(doc, template)

        # issuing_authority: from hardcoded_value
        assert results["issuing_authority"].value == "City of Laredo"
        assert results["issuing_authority"].extraction_source == "template_metadata"
        # certificate_holder_name: from OCR
        assert results["certificate_holder_name"].extraction_source == "zone"


# ===========================================================================
# TestLLMSkipsTemplateMetadata
# ===========================================================================

class TestLLMSkipsTemplateMetadata:
    """Tests that LLM cleanup never overrides template-authoritative fields."""

    def test_llm_skips_template_metadata_field(self):
        """LLM value is shorter but field has template_metadata source — skip."""
        fields = {
            "issuing_authority": _make_field(
                "issuing_authority",
                "City of Laredo",
                source="template_metadata",
            ),
        }
        llm_fields = {"issuing_authority": "Laredo"}

        updated = _apply_fields_to_extracted(llm_fields, fields)

        assert "issuing_authority" not in updated
        assert fields["issuing_authority"].value == "City of Laredo"

    def test_llm_overrides_generic_source(self):
        """LLM value is shorter and field has generic source — override allowed."""
        fields = {
            "issuing_authority": _make_field(
                "issuing_authority",
                "Issued by City of Laredo Human Resources Department",
                source="generic",
            ),
        }
        llm_fields = {"issuing_authority": "City of Laredo"}

        updated = _apply_fields_to_extracted(llm_fields, fields)

        assert "issuing_authority" in updated
        assert fields["issuing_authority"].value == "City of Laredo"

    def test_llm_overrides_zone_source(self):
        """LLM value is shorter and field has zone source — override allowed."""
        fields = {
            "issuing_authority": _make_field(
                "issuing_authority",
                "City of Laredo Health Department",
                source="zone",
            ),
        }
        llm_fields = {"issuing_authority": "City of Laredo"}

        updated = _apply_fields_to_extracted(llm_fields, fields)

        assert "issuing_authority" in updated
        assert fields["issuing_authority"].value == "City of Laredo"

    def test_llm_skips_template_metadata_even_when_empty(self):
        """Template metadata field with empty value is still protected."""
        fields = {
            "issuing_authority": _make_field(
                "issuing_authority",
                "City of Laredo",
                source="template_metadata",
            ),
        }
        # LLM tries to override with a different value
        llm_fields = {"issuing_authority": "OSHA"}

        updated = _apply_fields_to_extracted(llm_fields, fields)

        assert "issuing_authority" not in updated
        assert fields["issuing_authority"].value == "City of Laredo"

    def test_llm_can_add_non_template_fields_alongside_protected(self):
        """LLM adds new fields while leaving template_metadata fields untouched."""
        fields = {
            "issuing_authority": _make_field(
                "issuing_authority",
                "City of Laredo",
                source="template_metadata",
            ),
        }
        llm_fields = {
            "issuing_authority": "Laredo",  # Should be skipped
            "certificate_type": "Safety Training",  # New field, should be added
        }

        updated = _apply_fields_to_extracted(llm_fields, fields)

        assert "issuing_authority" not in updated
        assert "certificate_type" in updated
        assert fields["certificate_type"].value == "Safety Training"
        assert fields["certificate_type"].extraction_source == "llm"
        assert fields["issuing_authority"].value == "City of Laredo"


# ===========================================================================
# TestTemplateRegistryLoadsHardcodedValue
# ===========================================================================

class TestTemplateRegistryLoadsHardcodedValue:
    """Tests that template registry correctly loads hardcoded_value from JSON."""

    def test_loads_hardcoded_value_from_city_of_laredo_template(self):
        """city_of_laredo.json has hardcoded_value on issuing_authority zone."""
        templates_dir = _project_root / "CoreInstances" / "ApiServer" / "templates"
        registry = JsonTemplateRegistry(str(templates_dir))

        template = registry.get_template("city_of_laredo")
        ia_zone = None
        for zone in template.zones:
            if zone.field_name == "issuing_authority":
                ia_zone = zone
                break

        assert ia_zone is not None
        assert ia_zone.hardcoded_value == "City of Laredo"

    def test_no_hardcoded_value_on_other_zones(self):
        """Other zones in city_of_laredo template have no hardcoded_value."""
        templates_dir = _project_root / "CoreInstances" / "ApiServer" / "templates"
        registry = JsonTemplateRegistry(str(templates_dir))

        template = registry.get_template("city_of_laredo")
        for zone in template.zones:
            if zone.field_name != "issuing_authority":
                assert zone.hardcoded_value is None, (
                    f"Zone {zone.field_name} should not have hardcoded_value"
                )

    def test_lms_template_has_no_hardcoded_values(self):
        """lms_certificate template has no hardcoded_value on any zone."""
        templates_dir = _project_root / "CoreInstances" / "ApiServer" / "templates"
        registry = JsonTemplateRegistry(str(templates_dir))

        template = registry.get_template("lms_certificate")
        for zone in template.zones:
            assert zone.hardcoded_value is None, (
                f"Zone {zone.field_name} should not have hardcoded_value"
            )


# ===========================================================================
# TestFieldZoneModel
# ===========================================================================

class TestFieldZoneModel:
    """Tests for FieldZone dataclass hardcoded_value attribute."""

    def test_hardcoded_value_defaults_to_none(self):
        """FieldZone without hardcoded_value has None by default."""
        zone = FieldZone(
            field_name="issuing_authority",
            bbox_norm=(0.0, 0.0, 1.0, 1.0),
            parsing=ZoneParsing(),
            validators=ZoneValidators(),
        )
        assert zone.hardcoded_value is None

    def test_hardcoded_value_can_be_set(self):
        """FieldZone accepts hardcoded_value parameter."""
        zone = FieldZone(
            field_name="issuing_authority",
            bbox_norm=(0.0, 0.0, 1.0, 1.0),
            parsing=ZoneParsing(),
            validators=ZoneValidators(),
            hardcoded_value="City of Laredo",
        )
        assert zone.hardcoded_value == "City of Laredo"

    def test_hardcoded_value_works_for_any_field(self):
        """hardcoded_value is a generic mechanism — works for any field name."""
        zone = FieldZone(
            field_name="certificate_type",
            bbox_norm=(0.0, 0.0, 1.0, 1.0),
            parsing=ZoneParsing(),
            validators=ZoneValidators(),
            hardcoded_value="CPR Certification",
        )
        assert zone.hardcoded_value == "CPR Certification"
        assert zone.field_name == "certificate_type"
