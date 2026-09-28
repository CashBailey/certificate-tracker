"""Security and provenance controls at the extraction review boundary."""

import asyncio
from io import BytesIO
from unittest.mock import Mock

import pytest
from pypdf import PdfWriter

from shared.models import (
    DocumentToken,
    ExtractionConfidence,
    ExtractedFieldValue,
    FieldZone,
    NormalizedDocument,
    NormalizedPage,
    SearchableText,
    TemplateAlignment,
    TemplateDefinition,
    TemplateDetection,
    TemplateReviewRules,
    ZoneParsing,
    ZoneValidators,
)
from shared.text_processing import PAGE_BREAK_MARKER, build_searchable_text
from src.confidence import determine_needs_review
from src.course_name_corrector import correct_certificate_type_field
from src.generic_extract import GenericExtractor
from src.identify import TemplateIdentifier
from src.name_matcher import match_names
from src.pdf_text import MAX_PDF_PAGES, DocumentLimitError, PyPdfTextExtractor
from src.pipeline import ExtractionPipeline
from src.zone_extract import ZoneExtractor


def _token(text: str, page: int, bbox=(0.1, 0.1, 0.4, 0.2)) -> DocumentToken:
    return DocumentToken(
        token_id=f"page-{page}-{text}",
        text=text,
        bbox_norm=bbox,
        page_num=page,
        confidence=1.0,
    )


def _document(*pages: list[DocumentToken]) -> NormalizedDocument:
    normalized_pages = [
        NormalizedPage(
            page_num=index,
            tokens=tokens,
            page_text=" ".join(token.text for token in tokens),
            is_digital=True,
        )
        for index, tokens in enumerate(pages, start=1)
    ]
    full_text = "\n".join(page.page_text for page in normalized_pages)
    return NormalizedDocument(
        pages=normalized_pages,
        searchable_text=SearchableText(full_text=full_text, token_map={}),
        total_pages=len(normalized_pages),
    )


def _zone(
    name: str,
    bbox=(0.1, 0.1, 0.4, 0.2),
    regex_pattern: str | None = None,
) -> FieldZone:
    return FieldZone(
        field_name=name,
        bbox_norm=bbox,
        parsing=ZoneParsing(regex_pattern=regex_pattern),
        validators=ZoneValidators(),
        required=True,
    )


def _template(zones: list[FieldZone], always_review: list[str] | None = None):
    return TemplateDefinition(
        template_id="test",
        version=1,
        name="Test",
        description="",
        detection=TemplateDetection(anchor_keywords=[]),
        alignment=TemplateAlignment(reference_anchors=[]),
        zones=zones,
        review_rules=TemplateReviewRules(always_review_fields=always_review or []),
    )


def _field(value: str) -> ExtractedFieldValue:
    return ExtractedFieldValue(
        field_name="certificate_type",
        value=value,
        confidence=ExtractionConfidence(0.35, 0.25, 0.2, 0.2, 1.0),
        extraction_source="zone",
        needs_review=False,
    )


@pytest.mark.asyncio
async def test_zone_values_are_bound_to_one_supporting_page():
    holder_zone = _zone("certificate_holder_name")
    type_zone = _zone("certificate_type", bbox=(0.1, 0.4, 0.4, 0.5))
    document = _document(
        [_token("Marie Garcia", 1), _token("HIPAA", 1, type_zone.bbox_norm)],
        [_token("Maria Garcia", 2)],
    )

    fields = await ZoneExtractor().extract_zones(
        document,
        _template([holder_zone, type_zone]),
    )

    assert fields["certificate_holder_name"].value == "Marie Garcia"
    assert fields["certificate_type"].value == "HIPAA"
    assert {field.source_page_num for field in fields.values()} == {1}


@pytest.mark.asyncio
async def test_parse_failure_forces_review_even_at_threshold():
    zone = _zone("issuing_authority", regex_pattern=r"Issued by: (.+)")
    fields = await ZoneExtractor().extract_zones(
        _document([_token("City of Laredo", 1)]),
        _template([zone]),
    )

    field = fields["issuing_authority"]
    needs_review, reasons = determine_needs_review(fields)

    assert field.confidence.overall == pytest.approx(0.8)
    assert field.parse_success is False
    assert field.needs_review is True
    assert needs_review is True
    assert reasons == ["Field 'issuing_authority' could not be parsed using the template rule"]


def test_template_always_review_rule_is_enforced():
    field = _field("HIPAA Privacy & Security Training")

    needs_review, reasons = determine_needs_review(
        {"certificate_type": field},
        always_review_fields={"certificate_type"},
    )

    assert needs_review is True
    assert "template policy" in reasons[0]


def test_near_neighbor_name_does_not_suppress_identity_mismatch():
    result = match_names("Maria Garcia", "Marie", "Garcia")

    assert result.is_match is False
    assert result.confidence == 0.3
    assert "exactly match" in (result.mismatch_reason or "")


def test_exact_name_parts_allow_middle_names_and_ordering():
    result = match_names("Garcia Maria Elena", "Maria", "Garcia")

    assert result.is_match is True
    assert result.confidence == 1.0


def test_oversized_name_is_rejected_without_copying_it_to_reason():
    malicious_name = "A" * 10_000

    result = match_names(malicious_name, "Maria", "Garcia")

    assert result.is_match is False
    assert malicious_name not in (result.mismatch_reason or "")
    assert len(result.mismatch_reason or "") < 100


@pytest.mark.parametrize(
    "value",
    [
        "NOT HIPAA Privacy & Security Training",
        "This certificate excludes Sexual Harassment & Other Harassment Prevention Training",
    ],
)
def test_negated_course_text_is_not_promoted(value: str):
    field = _field(value)

    correct_certificate_type_field({"certificate_type": field})

    assert field.value == value
    assert field.needs_review is True


def test_non_exact_course_wrapper_remains_visible_for_review():
    value = "Certificate of Completion: HIPAA Privacy & Security Training"
    field = _field(value)

    correct_certificate_type_field({"certificate_type": field})

    assert field.value == value
    assert field.needs_review is True


def test_equivalent_course_punctuation_can_be_canonicalized():
    field = _field("CPR Basic Life Support BLS")

    correct_certificate_type_field({"certificate_type": field})

    assert field.value == "CPR / Basic Life Support (BLS)"
    assert field.needs_review is False


def test_searchable_text_never_joins_label_and_value_across_pages():
    tokens = [
        _token("ISSUE DATE:", 1),
        _token("01/02/2024", 2, bbox=(0.5, 0.1, 0.7, 0.2)),
    ]

    searchable = build_searchable_text(tokens)

    assert searchable.full_text == f"ISSUE DATE:\n{PAGE_BREAK_MARKER}\n01/02/2024"
    assert "issue_date" not in GenericExtractor().extract_all_fields(
        NormalizedDocument(
            pages=[],
            searchable_text=searchable,
            total_pages=2,
        )
    )


def test_generic_extraction_uses_one_supporting_page():
    document = _document(
        [_token("NAME: Maria Garcia", 1)],
        [_token("ISSUE DATE: 01/02/2024", 2)],
    )

    fields = GenericExtractor().extract_all_fields(document)

    assert not {
        "certificate_holder_name",
        "issue_date",
    }.issubset(fields)
    assert len({field.source_page_num for field in fields.values()}) <= 1


def test_template_anchors_must_match_on_the_same_page():
    template = _template([])
    template.detection = TemplateDetection(
        anchor_keywords=["CERTIFICATE OF COMPLETION", "CITY OF LAREDO"],
        min_keyword_matches=2,
        min_confidence_score=0.6,
    )
    registry = Mock()
    registry.list_templates.return_value = [template]
    document = _document(
        [_token("CERTIFICATE OF COMPLETION", 1)],
        [_token("CITY OF LAREDO", 2)],
    )

    result = TemplateIdentifier(registry).identify_template(document)

    assert result.template is None
    assert result.confidence == 0.0


def test_pdf_page_count_is_rejected_before_token_expansion():
    writer = PdfWriter()
    for _ in range(MAX_PDF_PAGES + 1):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)

    with pytest.raises(DocumentLimitError, match="pages"):
        PyPdfTextExtractor().extract_text_with_positions(output.getvalue())


@pytest.mark.asyncio
async def test_pipeline_deadline_becomes_terminal_document_limit(monkeypatch):
    pipeline = ExtractionPipeline.__new__(ExtractionPipeline)

    async def slow_extraction(*_args):
        await asyncio.sleep(1)

    pipeline._run_extraction = slow_extraction
    monkeypatch.setattr("src.pipeline.EXTRACTION_DEADLINE_SECONDS", 0.01)

    with pytest.raises(DocumentLimitError, match="exceeded"):
        await pipeline.run_extraction(1, b"data", "application/pdf")
