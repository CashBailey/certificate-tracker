"""Resource and integrity bounds for generic/template extraction."""

from unittest.mock import Mock

from shared.models import (
    NormalizedDocument,
    SearchableText,
    TemplateAlignment,
    TemplateDefinition,
    TemplateDetection,
    TemplateReviewRules,
)
from src.generic_extract import (
    MAX_GENERIC_CANDIDATES_PER_FIELD,
    MAX_GENERIC_TEXT_CHARS,
    GenericExtractor,
)
from src.identify import MAX_REGEX_EVIDENCE_CHARS, TemplateIdentifier


def _document(text: str) -> NormalizedDocument:
    return NormalizedDocument(
        pages=[],
        searchable_text=SearchableText(full_text=text, token_map={}),
        total_pages=0,
    )


def test_generic_candidate_materialization_is_bounded():
    patterns = {
        "certificate_number": [
            (r"NUMBER:\s*([A-Z0-9-]+)", 0.9),
        ]
    }
    text = "\n".join(f"NUMBER: CERT-{index:05d}" for index in range(500))

    result = GenericExtractor(patterns).extract_field(text, "certificate_number")

    assert len(result.all_candidates) == MAX_GENERIC_CANDIDATES_PER_FIELD
    assert result.best_candidate is not None
    assert result.best_candidate.value == "CERT-00000"


def test_generic_text_work_keeps_bounded_head_and_tail():
    text = "H" * MAX_GENERIC_TEXT_CHARS + "MIDDLE" + "T" * MAX_GENERIC_TEXT_CHARS

    bounded = GenericExtractor._bounded_text(text)

    assert len(bounded) == MAX_GENERIC_TEXT_CHARS + 1
    assert bounded.startswith("H")
    assert bounded.endswith("T")
    assert "MIDDLE" not in bounded


def test_combined_extraction_builds_fields_and_assist_from_one_scan():
    extractor = GenericExtractor()
    original = extractor._extract_field
    extractor._extract_field = Mock(wraps=original)

    fields, assist = extractor.extract_fields_and_review_assist(
        _document("NAME: Jane Doe\nISSUED: 01/15/2026")
    )

    assert "certificate_holder_name" in fields
    assert "certificate_holder_name" in assist
    assert extractor._extract_field.call_count == 10


def test_template_regex_evidence_is_bounded_but_keeps_span():
    filler = "X" * 10_000
    text = f"CERTIFICATE OF COMPLETION {filler} CITY OF LAREDO"
    template = TemplateDefinition(
        template_id="test",
        version=1,
        name="Test",
        description="Test",
        detection=TemplateDetection(
            anchor_keywords=["CERTIFICATE OF COMPLETION", "CITY OF LAREDO"],
            anchor_regex=r"CERTIFICATE OF COMPLETION.*CITY OF LAREDO",
            min_keyword_matches=2,
            min_confidence_score=0.7,
        ),
        alignment=TemplateAlignment(reference_anchors=[]),
        zones=[],
        review_rules=TemplateReviewRules(),
    )
    identifier = TemplateIdentifier(Mock())

    score, evidence = identifier._score_template(template, text)

    assert score == 1.0
    assert len(evidence["regex_match"]) == MAX_REGEX_EVIDENCE_CHARS
    assert evidence["regex_match_span"] == [0, len(text)]
    assert evidence["regex_match_truncated"] is True
