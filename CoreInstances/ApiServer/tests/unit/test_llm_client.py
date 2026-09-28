"""
Tests for consensus-based LLM field extraction (llm_client.py).

Covers: JSON parsing, normalization, majority vote, field application,
parallel Ollama calls, judge candidate resolution, and end-to-end consensus flow.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# llm_client imports "from shared.models import ..." which needs ApiServer/src on path.
# It also lives in ExtractionWorker/src. Both directories only exist in the host
# project layout (parents[4]); inside the api container, parents[4] is IndexError
# and ExtractionWorker is not mounted. Skip the module gracefully in that case.
try:
    _project_root = Path(__file__).resolve().parents[4]
    _api_src = str(_project_root / "CoreInstances" / "ApiServer" / "src")
    _extraction_src = str(_project_root / "BackgroundProcessingInstances" / "ExtractionWorker" / "src")
    for _p in (_api_src, _extraction_src):
        if _p not in sys.path:
            sys.path.insert(0, _p)

    from gpu_detect import GpuInfo, detect_gpu, should_parallelize_consensus
    from llm_client import (
        PARALLEL_CONSENSUS,
        _apply_fields_to_extracted,
        _build_nuextract_prompt,
        _call_ollama_n_times,
        _is_nuextract,
        _judge_candidates,
        _majority_vote,
        _normalize_date_to_iso,
        _normalize_for_comparison,
        _parse_llm_response,
        _postprocess_nuextract,
        llm_clean_fields,
    )
    from shared.models import ExtractionConfidence, ExtractedFieldValue
except (IndexError, ModuleNotFoundError) as _import_err:
    pytest.skip(
        f"Requires host project layout with ExtractionWorker on path ({_import_err})",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_field(name: str, value: str | None) -> ExtractedFieldValue:
    """Create an ExtractedFieldValue with dummy confidence."""
    return ExtractedFieldValue(
        field_name=name,
        value=value,
        confidence=ExtractionConfidence(
            zone=0.9, ocr=0.8, parse=0.7, validate=0.6, overall=0.75,
        ),
        extraction_source="generic",
        needs_review=False,
    )


def _sample_fields() -> dict[str, ExtractedFieldValue]:
    """Noisy regex-extracted fields — values are longer than clean LLM output."""
    return {
        "certificate_holder_name": _make_field(
            "certificate_holder_name",
            "This certificate is presented to Maria Garcia",
        ),
        "certificate_type": _make_field(
            "certificate_type",
            "Successfully completed Sexual Harassment Prevention Training course",
        ),
        "issue_date": _make_field("issue_date", "September 14, 2024"),
        "issuing_authority": _make_field(
            "issuing_authority",
            "Issued by City of Laredo Human Resources Department",
        ),
    }


def _unanimous_response() -> str:
    """Standard clean extraction result used across multiple tests."""
    return json.dumps({
        "certificate_holder_name": "Maria Garcia",
        "certificate_type": "Harassment Prevention",
        "issue_date": "2024-09-14",
        "issuing_authority": "City of Laredo",
    })


# ===========================================================================
# TestParseResponse
# ===========================================================================

class TestParseResponse:
    def test_valid_json(self):
        raw = '{"name": "John Smith", "date": "2024-01-15"}'
        result = _parse_llm_response(raw)
        assert result == {"name": "John Smith", "date": "2024-01-15"}

    def test_json_in_code_fences(self):
        raw = '```json\n{"name": "John Smith"}\n```'
        result = _parse_llm_response(raw)
        assert result == {"name": "John Smith"}

    def test_json_embedded_in_text(self):
        raw = 'Here is the result: {"name": "John Smith"} as requested.'
        result = _parse_llm_response(raw)
        assert result == {"name": "John Smith"}

    def test_empty_input(self):
        assert _parse_llm_response("") is None
        assert _parse_llm_response(None) is None

    def test_unparseable_garbage(self):
        assert _parse_llm_response("not json at all!!!") is None

    def test_unparseable_response_content_is_not_logged(self, caplog):
        sensitive = "Jane Doe certificate TX-SECRET-123 is not JSON"
        with caplog.at_level("WARNING", logger="llm_client"):
            assert _parse_llm_response(sensitive) is None

        assert sensitive not in caplog.text
        assert "TX-SECRET-123" not in caplog.text
        assert f"response_chars={len(sensitive)}" in caplog.text


# ===========================================================================
# TestNormalization
# ===========================================================================

class TestNormalization:
    def test_strip_and_lower(self):
        assert _normalize_for_comparison("  John Smith  ") == "john smith"

    def test_collapse_spaces(self):
        assert _normalize_for_comparison("John   Smith") == "john smith"

    def test_mixed_case_and_whitespace(self):
        assert _normalize_for_comparison("  JOHN   smith  ") == "john smith"


# ===========================================================================
# TestNuExtractHelpers
# ===========================================================================

class TestNuExtractHelpers:
    """Tests for NuExtract-specific helpers."""

    def test_is_nuextract_true(self):
        assert _is_nuextract("sroecker/nuextract-tiny-v1.5") is True

    def test_is_nuextract_false(self):
        assert _is_nuextract("llama3.2:3b") is False

    def test_is_nuextract_case_insensitive(self):
        assert _is_nuextract("SROECKER/NUEXTRACT-TINY-V1.5") is True

    def test_normalize_date_iso_passthrough(self):
        assert _normalize_date_to_iso("2024-01-15") == "2024-01-15"

    def test_normalize_date_month_name(self):
        assert _normalize_date_to_iso("January 15, 2024") == "2024-01-15"

    def test_normalize_date_month_name_no_comma(self):
        assert _normalize_date_to_iso("January 15 2024") == "2024-01-15"

    def test_normalize_date_slash_format(self):
        assert _normalize_date_to_iso("01/15/2024") == "2024-01-15"

    def test_normalize_date_unparseable_returns_original(self):
        assert _normalize_date_to_iso("sometime in 2024") == "sometime in 2024"

    def test_normalize_date_empty(self):
        assert _normalize_date_to_iso("") == ""

    def test_normalize_date_none(self):
        assert _normalize_date_to_iso(None) is None

    def test_build_nuextract_prompt_format(self):
        prompt = _build_nuextract_prompt("some ocr text")
        assert "<|input|>" in prompt
        assert "<|output|>" in prompt
        assert "### Template:" in prompt
        assert "certificate_holder_name" in prompt
        assert "course_name" in prompt
        assert "issue_date" in prompt
        assert "issuing_organization" in prompt
        assert "some ocr text" in prompt

    def test_postprocess_nuextract_remaps_field_names(self):
        """NuExtract field names are remapped to standard system names."""
        fields = {
            "certificate_holder_name": "John Smith",
            "course_name": "CPR/BLS Certification",
            "issue_date": "January 15, 2024",
            "issuing_organization": "American Heart Association",
        }
        result = _postprocess_nuextract(fields)
        assert result["certificate_holder_name"] == "John Smith"
        assert result["certificate_type"] == "CPR/BLS Certification"
        assert result["issue_date"] == "2024-01-15"
        assert result["issuing_authority"] == "American Heart Association"
        assert "course_name" not in result
        assert "issuing_organization" not in result

    def test_postprocess_nuextract_normalizes_date(self):
        fields = {
            "certificate_holder_name": "John Smith",
            "issue_date": "January 15, 2024",
        }
        result = _postprocess_nuextract(fields)
        assert result["issue_date"] == "2024-01-15"
        assert result["certificate_holder_name"] == "John Smith"

    def test_postprocess_nuextract_iso_date_unchanged(self):
        fields = {"issue_date": "2024-01-15"}
        result = _postprocess_nuextract(fields)
        assert result["issue_date"] == "2024-01-15"

    def test_postprocess_nuextract_unknown_fields_preserved(self):
        """Fields not in the remap dict keep their original names."""
        fields = {"some_other_field": "value"}
        result = _postprocess_nuextract(fields)
        assert result["some_other_field"] == "value"


# ===========================================================================
# TestMajorityVote
# ===========================================================================

class TestMajorityVote:
    def test_unanimous(self):
        candidates = [
            {"name": "Maria Garcia", "date": "2024-09-14"},
            {"name": "Maria Garcia", "date": "2024-09-14"},
            {"name": "Maria Garcia", "date": "2024-09-14"},
        ]
        consensus, disputed = _majority_vote(candidates)
        assert consensus["name"] == "Maria Garcia"
        assert consensus["date"] == "2024-09-14"
        assert disputed == []

    def test_two_of_three_agree(self):
        candidates = [
            {"name": "Maria Garcia"},
            {"name": "Maria Garcia"},
            {"name": "Maria Garzia"},  # hallucinated typo
        ]
        consensus, disputed = _majority_vote(candidates)
        assert consensus["name"] == "Maria Garcia"
        assert disputed == []

    def test_all_differ(self):
        candidates = [
            {"name": "Maria Garcia"},
            {"name": "Maria Garzia"},
            {"name": "M. Garcia"},
        ]
        consensus, disputed = _majority_vote(candidates)
        assert "name" in disputed
        assert "name" not in consensus

    def test_case_insensitive_match(self):
        candidates = [
            {"name": "John Smith"},
            {"name": "john smith"},
            {"name": "John Smith"},
        ]
        consensus, disputed = _majority_vote(candidates)
        assert consensus["name"].lower() == "john smith"
        assert disputed == []

    def test_mixed_consensus_and_disputed(self):
        candidates = [
            {"name": "Maria Garcia", "date": "2024-09-14"},
            {"name": "Maria Garcia", "date": "2024-09-15"},
            {"name": "Maria Garcia", "date": "2024-09-16"},
        ]
        consensus, disputed = _majority_vote(candidates)
        assert consensus["name"] == "Maria Garcia"
        assert "date" in disputed

    def test_null_and_empty_values(self):
        candidates = [
            {"name": None, "date": "2024-09-14"},
            {"name": "", "date": "2024-09-14"},
            {"name": "Maria", "date": "2024-09-14"},
        ]
        consensus, disputed = _majority_vote(candidates)
        # "Maria" is the only non-empty value but only appears once out of 3
        # None and "" are filtered out, so only 1 valid value for "name"
        # 1 > 1.5 is False, so it's disputed
        assert consensus["date"] == "2024-09-14"


# ===========================================================================
# TestApplyFields
# ===========================================================================

class TestApplyFields:
    def test_shorter_value_overrides(self):
        fields = _sample_fields()
        llm_fields = {"certificate_holder_name": "Maria Garcia"}
        updated = _apply_fields_to_extracted(llm_fields, fields)
        assert "certificate_holder_name" in updated
        assert fields["certificate_holder_name"].value == "Maria Garcia"
        assert fields["certificate_holder_name"].extraction_source == "llm"
        assert fields["certificate_holder_name"].confidence.overall == 0.5
        assert fields["certificate_holder_name"].needs_review is True

    def test_longer_value_does_not_override(self):
        fields = _sample_fields()
        llm_fields = {
            "certificate_holder_name": (
                "This certificate is awarded and presented to Maria Garcia of Laredo TX"
            ),
        }
        updated = _apply_fields_to_extracted(llm_fields, fields)
        assert "certificate_holder_name" not in updated

    def test_fills_empty_value(self):
        fields = {"issue_date": _make_field("issue_date", None)}
        llm_fields = {"issue_date": "2024-09-14"}
        updated = _apply_fields_to_extracted(llm_fields, fields)
        assert "issue_date" in updated
        assert fields["issue_date"].value == "2024-09-14"

    def test_adds_new_canonical_field(self):
        """LLM discovers a canonical field not found by regex — it should be added."""
        fields = {"certificate_holder_name": _make_field("certificate_holder_name", "Jane Doe")}
        llm_fields = {"certificate_type": "Forklift Safety"}
        updated = _apply_fields_to_extracted(llm_fields, fields)
        assert "certificate_type" in updated
        assert "certificate_type" in fields
        new_field = fields["certificate_type"]
        assert new_field.value == "Forklift Safety"
        assert new_field.extraction_source == "llm"
        assert new_field.needs_review is True
        assert new_field.confidence.zone == 0.0
        assert new_field.confidence.ocr == 0.0
        assert new_field.confidence.parse == 0.0
        assert new_field.confidence.validate == 0.0
        assert new_field.confidence.overall == 0.5

    def test_drops_non_canonical_field(self):
        """LLM returns a field not in CANONICAL_FIELDS — it should be silently dropped."""
        fields = {}
        llm_fields = {"hallucinated_field": "some value"}
        updated = _apply_fields_to_extracted(llm_fields, fields)
        assert "hallucinated_field" not in updated
        assert "hallucinated_field" not in fields

    def test_adds_multiple_new_fields(self):
        """LLM discovers multiple canonical fields not found by regex."""
        fields = {}
        llm_fields = {
            "certificate_type": "Hazmat Training",
            "issue_date": "2024-01-15",
            "issuing_authority": "OSHA",
        }
        updated = _apply_fields_to_extracted(llm_fields, fields)
        assert len(updated) == 3
        for name in ("certificate_type", "issue_date", "issuing_authority"):
            assert name in fields
            assert fields[name].extraction_source == "llm"
            assert fields[name].needs_review is True


# ===========================================================================
# TestCallOllamaNTimes
# ===========================================================================

class TestCallOllamaNTimes:
    @pytest.mark.asyncio
    async def test_all_succeed(self):
        responses = [
            json.dumps({"name": "Maria Garcia"}),
            json.dumps({"name": "Maria Garcia"}),
            json.dumps({"name": "Maria Garzia"}),
        ]
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = responses
            result = await _call_ollama_n_times("prompt", 3, 0.3)

        assert len(result) == 3
        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_all_calls_fail_returns_empty(self):
        """Ollama unreachable — all parallel calls return None."""
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = None
            result = await _call_ollama_n_times("prompt", 3, 0.3)

        assert result == []
        assert mock.call_count == 3  # All 3 fired in parallel

    @pytest.mark.asyncio
    async def test_partial_failure(self):
        """Some calls succeed, some fail — collect what succeeded."""
        responses = [
            json.dumps({"name": "Maria Garcia"}),
            None,  # second call fails
            json.dumps({"name": "Maria Garcia"}),
        ]
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = responses
            result = await _call_ollama_n_times("prompt", 3, 0.3)

        assert len(result) == 2
        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_all_unparseable(self):
        responses = ["not json", "also not json", "still not json"]
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = responses
            result = await _call_ollama_n_times("prompt", 3, 0.3)

        assert result == []

    @pytest.mark.asyncio
    async def test_runs_in_parallel(self):
        """Verify N calls are dispatched concurrently via asyncio.gather."""
        in_flight = 0
        max_in_flight = 0

        async def mock_call(prompt, temperature=0.0):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)  # Simulate brief I/O
            in_flight -= 1
            return json.dumps({"name": "test"})

        with patch("llm_client._call_ollama", side_effect=mock_call):
            result = await _call_ollama_n_times("prompt", 3, 0.3, parallel=True)

        assert len(result) == 3
        # All 3 were in-flight simultaneously (sequential would give 1)
        assert max_in_flight == 3


# ===========================================================================
# TestJudgeCandidates
# ===========================================================================

class TestJudgeCandidates:
    @pytest.mark.asyncio
    async def test_judge_resolves_all_fields(self):
        candidates = [
            {"name": "Maria Garcia", "issue_date": "2024-09-14"},
            {"name": "Maria Garzia", "issue_date": "2024-09-15"},
            {"name": "Maria Garcia", "issue_date": "2024-09-16"},
        ]
        judge_response = json.dumps({
            "name": "Maria Garcia",
            "issue_date": "2024-09-14",
        })
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = judge_response
            result = await _judge_candidates("some ocr text", candidates)

        assert result == {"name": "Maria Garcia", "issue_date": "2024-09-14"}

    @pytest.mark.asyncio
    async def test_judge_unavailable(self):
        candidates = [
            {"issue_date": "2024-09-14"},
            {"issue_date": "2024-09-15"},
            {"issue_date": "2024-09-16"},
        ]
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = None
            result = await _judge_candidates("some ocr text", candidates)

        assert result == {}

    @pytest.mark.asyncio
    async def test_judge_partial_resolution(self):
        candidates = [
            {"issue_date": "2024-09-14", "name": "A"},
            {"issue_date": "2024-09-15", "name": "B"},
            {"issue_date": "2024-09-16", "name": "C"},
        ]
        # Judge only resolves issue_date, not name
        judge_response = json.dumps({"issue_date": "2024-09-14"})
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = judge_response
            result = await _judge_candidates("some ocr text", candidates)

        assert result == {"issue_date": "2024-09-14"}
        assert "name" not in result

    @pytest.mark.asyncio
    async def test_judge_with_single_candidate(self):
        """Judge still runs meaningfully with only 1 candidate."""
        candidates = [
            {"name": "Maria Garcia", "issue_date": "2024-09-14"},
        ]
        judge_response = json.dumps({
            "name": "Maria Garcia",
            "issue_date": "2024-09-14",
        })
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = judge_response
            result = await _judge_candidates("some ocr text", candidates)

        assert result == {"name": "Maria Garcia", "issue_date": "2024-09-14"}

    @pytest.mark.asyncio
    async def test_judge_rejects_values_not_present_in_candidates(self):
        candidates = [
            {"issue_date": "2024-09-14"},
            {"issue_date": "2024-09-15"},
            {"issue_date": "2024-09-16"},
        ]
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = json.dumps({"issue_date": "1"})
            result = await _judge_candidates("adversarial OCR text", candidates)

        assert result == {}

    @pytest.mark.asyncio
    async def test_judge_normalized_match_returns_original_candidate(self):
        candidates = [{"certificate_holder_name": "Maria   Garcia"}]
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = json.dumps(
                {"certificate_holder_name": " maria garcia "}
            )
            result = await _judge_candidates("ocr text", candidates)

        assert result == {"certificate_holder_name": "Maria   Garcia"}

    @pytest.mark.asyncio
    async def test_judge_uses_llama_model_regardless_of_llm_model(self):
        """Judge must always use llama3.2:3b even when LLM_MODEL is NuExtract."""
        import llm_client

        candidates = [
            {"name": "Maria Garcia", "issue_date": "2024-09-14"},
        ]
        judge_response = json.dumps({
            "name": "Maria Garcia",
            "issue_date": "2024-09-14",
        })
        saved_model = llm_client.LLM_MODEL
        try:
            llm_client.LLM_MODEL = "sroecker/nuextract-tiny-v1.5"
            with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
                mock.return_value = judge_response
                await _judge_candidates("ocr text", candidates)

            # Verify model= was explicitly set to JUDGE_MODEL
            assert mock.call_args.kwargs.get("model") == "llama3.2:3b"
        finally:
            llm_client.LLM_MODEL = saved_model


# ===========================================================================
# TestLlmCleanFieldsConsensus
# ===========================================================================

class TestLlmCleanFieldsConsensus:
    @pytest.mark.asyncio
    async def test_empty_ocr_text_returns_unchanged(self):
        fields = _sample_fields()
        original_name = fields["certificate_holder_name"].value
        result = await llm_clean_fields("", fields)
        assert result["certificate_holder_name"].value == original_name

    @pytest.mark.asyncio
    async def test_ollama_unavailable_returns_unchanged(self):
        import llm_client

        fields = _sample_fields()
        original_name = fields["certificate_holder_name"].value
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = None
            # Force consensus path
            old_enabled = llm_client.CONSENSUS_ENABLED
            old_n = llm_client.CONSENSUS_N
            try:
                llm_client.CONSENSUS_ENABLED = True
                llm_client.CONSENSUS_N = 3
                result = await llm_clean_fields("Certificate text here", fields)
            finally:
                llm_client.CONSENSUS_ENABLED = old_enabled
                llm_client.CONSENSUS_N = old_n

        assert result["certificate_holder_name"].value == original_name

    @pytest.mark.asyncio
    async def test_consensus_disabled_single_run(self):
        import llm_client

        fields = _sample_fields()
        single_response = _unanimous_response()
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = single_response
            old_enabled = llm_client.CONSENSUS_ENABLED
            try:
                llm_client.CONSENSUS_ENABLED = False
                result = await llm_clean_fields("Certificate text here", fields)
            finally:
                llm_client.CONSENSUS_ENABLED = old_enabled

        # Single call only
        assert mock.call_count == 1
        assert result["certificate_holder_name"].value == "Maria Garcia"

    @pytest.mark.asyncio
    async def test_consensus_unanimous_judge_cannot_lengthen(self):
        """When all N runs agree, judge can't override with a longer value."""
        import llm_client

        fields = _sample_fields()
        resp = _unanimous_response()  # "Maria Garcia"
        # Judge returns a LONGER name — should be ignored
        judge_resp = json.dumps({
            "certificate_holder_name": "Maria Elena Garcia",
            "certificate_type": "Sexual Harassment Prevention Training",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })

        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = [resp, resp, resp, judge_resp]
            old_enabled = llm_client.CONSENSUS_ENABLED
            old_n = llm_client.CONSENSUS_N
            try:
                llm_client.CONSENSUS_ENABLED = True
                llm_client.CONSENSUS_N = 3
                result = await llm_clean_fields("Certificate text here", fields)
            finally:
                llm_client.CONSENSUS_ENABLED = old_enabled
                llm_client.CONSENSUS_N = old_n

        # 3 generation + 1 judge = 4 calls
        assert mock.call_count == 4
        # Judge's longer values are ignored; consensus preserved
        assert result["certificate_holder_name"].value == "Maria Garcia"

    @pytest.mark.asyncio
    async def test_consensus_with_dispute_judge_resolves(self):
        """Judge resolves fields where extractors disagree."""
        import llm_client

        fields = _sample_fields()
        # 3 runs agree on name but disagree on date
        run1 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })
        run2 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-15",
            "issuing_authority": "City of Laredo",
        })
        run3 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-16",
            "issuing_authority": "City of Laredo",
        })
        judge_response = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })

        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            # 3 generation calls + 1 judge call
            mock.side_effect = [run1, run2, run3, judge_response]
            old_enabled = llm_client.CONSENSUS_ENABLED
            old_n = llm_client.CONSENSUS_N
            try:
                llm_client.CONSENSUS_ENABLED = True
                llm_client.CONSENSUS_N = 3
                result = await llm_clean_fields("Certificate text here", fields)
            finally:
                llm_client.CONSENSUS_ENABLED = old_enabled
                llm_client.CONSENSUS_N = old_n

        # 3 generation + 1 judge = 4 calls
        assert mock.call_count == 4
        assert result["certificate_holder_name"].value == "Maria Garcia"
        assert result["issue_date"].value == "2024-09-14"

    @pytest.mark.asyncio
    async def test_one_of_three_succeeds_judge_runs(self):
        """1/3 extraction succeeds — judge still runs with 1 candidate."""
        import llm_client

        fields = _sample_fields()
        single_result = _unanimous_response()
        judge_response = _unanimous_response()

        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = [
                single_result,  # Run 1 succeeds
                None,           # Run 2 fails
                None,           # Run 3 fails
                judge_response, # Judge runs
            ]
            old_enabled = llm_client.CONSENSUS_ENABLED
            old_n = llm_client.CONSENSUS_N
            try:
                llm_client.CONSENSUS_ENABLED = True
                llm_client.CONSENSUS_N = 3
                result = await llm_clean_fields("Certificate text here", fields)
            finally:
                llm_client.CONSENSUS_ENABLED = old_enabled
                llm_client.CONSENSUS_N = old_n

        assert mock.call_count == 4  # 3 extraction + 1 judge
        assert result["certificate_holder_name"].value == "Maria Garcia"

    @pytest.mark.asyncio
    async def test_two_of_three_succeed_judge_runs(self):
        """2/3 extraction succeeds — judge runs with 2 candidates."""
        import llm_client

        fields = _sample_fields()
        run1 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })
        run2 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-15",
            "issuing_authority": "City of Laredo",
        })
        judge_response = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })

        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = [
                run1,
                None,           # Run 2 fails
                run2,
                judge_response,
            ]
            old_enabled = llm_client.CONSENSUS_ENABLED
            old_n = llm_client.CONSENSUS_N
            try:
                llm_client.CONSENSUS_ENABLED = True
                llm_client.CONSENSUS_N = 3
                result = await llm_clean_fields("Certificate text here", fields)
            finally:
                llm_client.CONSENSUS_ENABLED = old_enabled
                llm_client.CONSENSUS_N = old_n

        assert mock.call_count == 4  # 3 extraction + 1 judge
        assert result["certificate_holder_name"].value == "Maria Garcia"
        assert result["issue_date"].value == "2024-09-14"

    @pytest.mark.asyncio
    async def test_majority_wins_judge_cannot_override_longer(self):
        """2/3 agree on all fields; judge's longer values are ignored."""
        import llm_client

        fields = _sample_fields()
        # 2/3 agree on everything, 1 has a typo
        run1 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })
        run2 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })
        run3 = json.dumps({
            "certificate_holder_name": "Maria Garzia",  # typo
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })
        judge_response = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })

        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = [run1, run2, run3, judge_response]
            old_enabled = llm_client.CONSENSUS_ENABLED
            old_n = llm_client.CONSENSUS_N
            try:
                llm_client.CONSENSUS_ENABLED = True
                llm_client.CONSENSUS_N = 3
                result = await llm_clean_fields("Certificate text here", fields)
            finally:
                llm_client.CONSENSUS_ENABLED = old_enabled
                llm_client.CONSENSUS_N = old_n

        assert mock.call_count == 4  # 3 extraction + 1 judge
        # Majority vote: Maria Garcia won 2/3
        assert result["certificate_holder_name"].value == "Maria Garcia"

    @pytest.mark.asyncio
    async def test_judge_fails_no_majority_returns_originals(self):
        """Judge fails + all 3 disagree = no majority, originals preserved."""
        import llm_client

        fields = _sample_fields()
        original_name = fields["certificate_holder_name"].value

        # All 3 runs produce different names (no majority possible)
        run1 = json.dumps({"certificate_holder_name": "A"})
        run2 = json.dumps({"certificate_holder_name": "B"})
        run3 = json.dumps({"certificate_holder_name": "C"})

        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = [run1, run2, run3, None]  # Judge also fails
            old_enabled = llm_client.CONSENSUS_ENABLED
            old_n = llm_client.CONSENSUS_N
            try:
                llm_client.CONSENSUS_ENABLED = True
                llm_client.CONSENSUS_N = 3
                result = await llm_clean_fields("Certificate text here", fields)
            finally:
                llm_client.CONSENSUS_ENABLED = old_enabled
                llm_client.CONSENSUS_N = old_n

        assert mock.call_count == 4
        # No majority, judge failed — original value unchanged
        assert result["certificate_holder_name"].value == original_name

    @pytest.mark.asyncio
    async def test_zero_of_three_succeed_returns_originals(self):
        """0/3 extraction succeeds — return originals, no judge call."""
        import llm_client

        fields = _sample_fields()
        original_name = fields["certificate_holder_name"].value

        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = None  # All fail
            old_enabled = llm_client.CONSENSUS_ENABLED
            old_n = llm_client.CONSENSUS_N
            try:
                llm_client.CONSENSUS_ENABLED = True
                llm_client.CONSENSUS_N = 3
                result = await llm_clean_fields("Certificate text here", fields)
            finally:
                llm_client.CONSENSUS_ENABLED = old_enabled
                llm_client.CONSENSUS_N = old_n

        # 3 extraction calls only, no judge (0 candidates)
        assert mock.call_count == 3
        assert result["certificate_holder_name"].value == original_name

    @pytest.mark.asyncio
    async def test_consensus_disputed_judge_only_overrides_disputed_fields(self):
        """Judge result for unanimous fields is ignored; only disputed fields use judge."""
        import llm_client

        fields = _sample_fields()
        # 3 runs agree on name/type/authority but disagree on date
        run1 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })
        run2 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-15",
            "issuing_authority": "City of Laredo",
        })
        run3 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-16",
            "issuing_authority": "City of Laredo",
        })
        # Judge returns DIFFERENT values for unanimous fields (simulating the bug)
        judge_response = json.dumps({
            "certificate_holder_name": "Maria Elena Garcia",  # Judge disagrees
            "certificate_type": "Sexual Harassment Prevention",  # Judge disagrees
            "issue_date": "2024-09-14",  # Judge resolves dispute
            "issuing_authority": "City of Laredo HR",  # Judge disagrees
        })

        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = [run1, run2, run3, judge_response]
            old_enabled = llm_client.CONSENSUS_ENABLED
            old_n = llm_client.CONSENSUS_N
            try:
                llm_client.CONSENSUS_ENABLED = True
                llm_client.CONSENSUS_N = 3
                result = await llm_clean_fields("Certificate text here", fields)
            finally:
                llm_client.CONSENSUS_ENABLED = old_enabled
                llm_client.CONSENSUS_N = old_n

        assert mock.call_count == 4  # 3 extraction + 1 judge (dispute exists)
        # Unanimous fields preserve majority vote, NOT judge override
        assert result["certificate_holder_name"].value == "Maria Garcia"
        assert result["certificate_type"].value == "Harassment Prevention"
        assert result["issuing_authority"].value == "City of Laredo"
        # Disputed field uses judge resolution
        assert result["issue_date"].value == "2024-09-14"


# ===========================================================================
# TestLlmCleanFieldsNuExtract
# ===========================================================================

class TestLlmCleanFieldsNuExtract:
    """Tests for NuExtract code path in llm_clean_fields."""

    @pytest.mark.asyncio
    async def test_nuextract_consensus_judge_cannot_lengthen(self):
        """NuExtract unanimous consensus: judge's longer values are ignored."""
        import llm_client

        fields = _sample_fields()
        # NuExtract returns fields with course_name/issuing_organization (remapped)
        resp = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "course_name": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_organization": "City of Laredo",
        })
        # Judge returns longer values — should be ignored for unanimous fields
        judge_resp = json.dumps({
            "certificate_holder_name": "Maria Elena Garcia",
            "certificate_type": "Harassment Prevention Training",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo Health Dept",
        })

        saved = (llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N)
        try:
            llm_client.LLM_MODEL = "sroecker/nuextract-tiny-v1.5"
            llm_client.CONSENSUS_ENABLED = True
            llm_client.CONSENSUS_N = 3

            with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
                mock.side_effect = [resp, resp, resp, judge_resp]
                result = await llm_clean_fields("Certificate text", fields)

            # 3 extraction + 1 judge = 4 calls
            assert mock.call_count == 4
        finally:
            llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N = saved

        # Consensus values preserved (judge was longer)
        assert result["certificate_holder_name"].value == "Maria Garcia"
        assert result["certificate_type"].value == "Harassment Prevention"
        assert result["issuing_authority"].value == "City of Laredo"

    @pytest.mark.asyncio
    async def test_nuextract_varied_temperatures(self):
        """NuExtract consensus runs use tiny varied temperatures."""
        import llm_client

        fields = _sample_fields()
        resp = json.dumps({"certificate_holder_name": "Maria Garcia"})

        saved = (llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N)
        try:
            llm_client.LLM_MODEL = "sroecker/nuextract-tiny-v1.5"
            llm_client.CONSENSUS_ENABLED = True
            llm_client.CONSENSUS_N = 3

            with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
                mock.return_value = resp
                await llm_clean_fields("Certificate text", fields)

            # First 3 calls are extraction runs with varied temps
            extraction_calls = mock.call_args_list[:3]
            temps = [c.kwargs.get("temperature", c.args[1] if len(c.args) > 1 else None)
                     for c in extraction_calls]
            # Temps should be [0.0, 0.05, 0.1] (not all the same)
            assert temps[0] == 0.0
            assert temps[1] > temps[0]
            assert temps[2] > temps[1]
            # All reasonably small
            assert all(t <= 0.15 for t in temps)
        finally:
            llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N = saved

    @pytest.mark.asyncio
    async def test_nuextract_prompt_format_used(self):
        """Verify the NuExtract prompt format (not EXTRACTION_PROMPT) is sent."""
        import llm_client

        fields = _sample_fields()
        resp = json.dumps({"certificate_holder_name": "Test"})

        saved = (llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N)
        try:
            llm_client.LLM_MODEL = "sroecker/nuextract-tiny-v1.5"
            llm_client.CONSENSUS_ENABLED = True
            llm_client.CONSENSUS_N = 3

            with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
                mock.return_value = resp
                await llm_clean_fields("Certificate text", fields)

            # Check the first extraction call's prompt
            prompt_arg = mock.call_args_list[0][0][0]
            assert "<|input|>" in prompt_arg
            assert "<|output|>" in prompt_arg
            assert "### Template:" in prompt_arg
        finally:
            llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N = saved

    @pytest.mark.asyncio
    async def test_nuextract_date_normalized(self):
        """NuExtract dates in natural language are normalized to ISO format."""
        import llm_client

        fields = _sample_fields()
        # NuExtract returns fields with raw dates and NuExtract-style names
        resp = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "course_name": "Harassment Prevention",
            "issue_date": "September 14, 2024",
            "issuing_organization": "City of Laredo",
        })
        # Judge sees standard names after postprocessing (date already normalized)
        judge_resp = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })

        saved = (llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N)
        try:
            llm_client.LLM_MODEL = "sroecker/nuextract-tiny-v1.5"
            llm_client.CONSENSUS_ENABLED = True
            llm_client.CONSENSUS_N = 3

            with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
                mock.side_effect = [resp, resp, resp, judge_resp]
                result = await llm_clean_fields("Certificate text", fields)
        finally:
            llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N = saved

        assert result["issue_date"].value == "2024-09-14"

    @pytest.mark.asyncio
    async def test_nuextract_ollama_unavailable_returns_unchanged(self):
        """NuExtract unavailable returns original fields."""
        import llm_client

        fields = _sample_fields()
        original_name = fields["certificate_holder_name"].value

        saved = (llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N)
        try:
            llm_client.LLM_MODEL = "sroecker/nuextract-tiny-v1.5"
            llm_client.CONSENSUS_ENABLED = True
            llm_client.CONSENSUS_N = 3

            with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
                mock.return_value = None
                result = await llm_clean_fields("Certificate text", fields)
        finally:
            llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N = saved

        assert result["certificate_holder_name"].value == original_name

    @pytest.mark.asyncio
    async def test_nuextract_disputed_field_uses_judge(self):
        """NuExtract with disputed field calls judge; unanimous fields preserved."""
        import llm_client

        fields = _sample_fields()
        # NuExtract runs agree on name but disagree on issue_date
        resp1 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "course_name": "Harassment Prevention",
            "issue_date": "September 14, 2024",
            "issuing_organization": "City of Laredo",
        })
        resp2 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "course_name": "Harassment Prevention",
            "issue_date": "September 15, 2024",
            "issuing_organization": "City of Laredo",
        })
        resp3 = json.dumps({
            "certificate_holder_name": "Maria Garcia",
            "course_name": "Harassment Prevention",
            "issue_date": "September 16, 2024",
            "issuing_organization": "City of Laredo",
        })
        # Judge resolves the date dispute (using standard field names)
        judge_resp = json.dumps({
            "certificate_holder_name": "Maria Elena Garcia",  # Should be ignored
            "certificate_type": "Harassment Prevention",
            "issue_date": "2024-09-14",
            "issuing_authority": "City of Laredo",
        })

        saved = (llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N)
        try:
            llm_client.LLM_MODEL = "sroecker/nuextract-tiny-v1.5"
            llm_client.CONSENSUS_ENABLED = True
            llm_client.CONSENSUS_N = 3

            with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
                mock.side_effect = [resp1, resp2, resp3, judge_resp]
                result = await llm_clean_fields("Certificate text", fields)

            # 3 extraction + 1 judge = 4 calls (dispute exists)
            assert mock.call_count == 4
        finally:
            llm_client.LLM_MODEL, llm_client.CONSENSUS_ENABLED, llm_client.CONSENSUS_N = saved

        # Unanimous fields preserved from majority vote (judge ignored)
        assert result["certificate_holder_name"].value == "Maria Garcia"
        assert result["certificate_type"].value == "Harassment Prevention"
        assert result["issuing_authority"].value == "City of Laredo"
        # Disputed field resolved by judge
        assert result["issue_date"].value == "2024-09-14"


# ===========================================================================
# TestGpuDetect
# ===========================================================================

class TestGpuDetect:
    """Tests for gpu_detect module."""

    def test_gpu_info_dataclass(self):
        info = GpuInfo(detected=True, device_name="RTX 3060", vram_total_mb=12288)
        assert info.detected is True
        assert info.device_name == "RTX 3060"
        assert info.vram_total_mb == 12288

    def test_gpu_info_no_gpu(self):
        info = GpuInfo(detected=False)
        assert info.detected is False
        assert info.device_name is None
        assert info.vram_total_mb is None

    def test_should_parallelize_above_threshold(self):
        info = GpuInfo(detected=True, device_name="RTX 3060", vram_total_mb=12288)
        assert should_parallelize_consensus(info) is True

    def test_should_parallelize_exactly_threshold(self):
        """4096 MB is exactly the threshold boundary — should NOT parallelize."""
        info = GpuInfo(detected=True, device_name="GPU", vram_total_mb=4096)
        assert should_parallelize_consensus(info) is False

    def test_should_parallelize_above_threshold_by_one(self):
        info = GpuInfo(detected=True, device_name="GPU", vram_total_mb=4097)
        assert should_parallelize_consensus(info) is True

    def test_should_not_parallelize_below_threshold(self):
        info = GpuInfo(detected=True, device_name="small GPU", vram_total_mb=2048)
        assert should_parallelize_consensus(info) is False

    def test_should_not_parallelize_no_gpu(self):
        info = GpuInfo(detected=False)
        assert should_parallelize_consensus(info) is False

    def test_detect_gpu_env_override(self):
        with patch.dict("os.environ", {"GPU_VRAM_MB": "8192"}):
            info = detect_gpu()
        assert info.detected is True
        assert info.vram_total_mb == 8192
        assert info.device_name == "env-override"

    def test_detect_gpu_env_override_zero(self):
        with patch.dict("os.environ", {"GPU_VRAM_MB": "0"}):
            info = detect_gpu()
        assert info.detected is False
        assert info.vram_total_mb == 0

    def test_detect_gpu_env_override_invalid(self):
        """Invalid env value falls through to nvidia-smi detection."""
        with patch.dict("os.environ", {"GPU_VRAM_MB": "not_a_number"}):
            with patch("gpu_detect._detect_via_nvidia_smi", return_value=None):
                info = detect_gpu()
        assert info.detected is False

    def test_detect_gpu_nvidia_smi(self):
        """nvidia-smi returns valid GPU info."""
        fake_info = GpuInfo(detected=True, device_name="RTX 4090", vram_total_mb=24576)
        with patch.dict("os.environ", {}, clear=False):
            env = os.environ.copy()
            env.pop("GPU_VRAM_MB", None)
            with patch.dict("os.environ", env, clear=True):
                with patch("gpu_detect._detect_via_nvidia_smi", return_value=fake_info):
                    info = detect_gpu()
        assert info.detected is True
        assert info.vram_total_mb == 24576

    def test_detect_gpu_no_nvidia_smi(self):
        """No nvidia-smi and no env override → no GPU."""
        with patch.dict("os.environ", {}, clear=False):
            env = os.environ.copy()
            env.pop("GPU_VRAM_MB", None)
            with patch.dict("os.environ", env, clear=True):
                with patch("gpu_detect._detect_via_nvidia_smi", return_value=None):
                    info = detect_gpu()
        assert info.detected is False


# ===========================================================================
# TestConsensusParallelism
# ===========================================================================

class TestConsensusParallelism:
    """Tests for parallel vs sequential consensus runs based on GPU detection."""

    @pytest.mark.asyncio
    async def test_parallel_flag_true_runs_concurrently(self):
        """parallel=True dispatches all calls concurrently."""
        in_flight = 0
        max_in_flight = 0

        async def mock_call(prompt, temperature=0.0):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return json.dumps({"name": "test"})

        with patch("llm_client._call_ollama", side_effect=mock_call):
            result = await _call_ollama_n_times("prompt", 3, 0.3, parallel=True)

        assert len(result) == 3
        assert max_in_flight == 3  # All in-flight simultaneously

    @pytest.mark.asyncio
    async def test_parallel_flag_false_runs_sequentially(self):
        """parallel=False runs calls one at a time."""
        in_flight = 0
        max_in_flight = 0

        async def mock_call(prompt, temperature=0.0):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return json.dumps({"name": "test"})

        with patch("llm_client._call_ollama", side_effect=mock_call):
            result = await _call_ollama_n_times("prompt", 3, 0.3, parallel=False)

        assert len(result) == 3
        assert max_in_flight == 1  # Only 1 in-flight at a time

    @pytest.mark.asyncio
    async def test_sequential_still_collects_all_results(self):
        """Sequential mode collects results identically to parallel."""
        responses = [
            json.dumps({"name": "Maria Garcia"}),
            json.dumps({"name": "Maria Garcia"}),
            json.dumps({"name": "Maria Garzia"}),
        ]
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = responses
            result = await _call_ollama_n_times("prompt", 3, 0.3, parallel=False)

        assert len(result) == 3
        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_sequential_partial_failure(self):
        """Sequential mode handles partial failures."""
        responses = [
            json.dumps({"name": "Maria Garcia"}),
            None,
            json.dumps({"name": "Maria Garcia"}),
        ]
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.side_effect = responses
            result = await _call_ollama_n_times("prompt", 3, 0.3, parallel=False)

        assert len(result) == 2
        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_sequential_all_fail(self):
        """Sequential mode with all failures returns empty list."""
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = None
            result = await _call_ollama_n_times("prompt", 3, 0.3, parallel=False)

        assert result == []
        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_sequential_exception_handling(self):
        """Sequential mode catches exceptions from individual runs."""
        async def exploding_call(prompt, temperature=0.0):
            if temperature > 0.2:
                raise RuntimeError("boom")
            return json.dumps({"name": "test"})

        with patch("llm_client._call_ollama", side_effect=exploding_call):
            result = await _call_ollama_n_times(
                "prompt", 3, [0.0, 0.1, 0.3], parallel=False,
            )

        # First two succeed, third raises → 2 valid results
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_default_uses_module_level_flag(self):
        """When parallel is not specified, uses PARALLEL_CONSENSUS."""
        with patch("llm_client._call_ollama", new_callable=AsyncMock) as mock:
            mock.return_value = json.dumps({"name": "test"})
            await _call_ollama_n_times("prompt", 3, 0.3)

        # Just verify it ran (mode depends on detected GPU)
        assert mock.call_count == 3


# ===========================================================================
# TestParallelConsensusEnvOverride
# ===========================================================================

class TestParallelConsensusEnvOverride:
    """Tests for LLM_PARALLEL_CONSENSUS env var override in llm_client."""

    def _reload_parallel_flag(self):
        """Re-execute the env-override logic and return the resulting flag."""
        import importlib
        import llm_client
        importlib.reload(llm_client)
        return llm_client.PARALLEL_CONSENSUS

    def test_env_true_forces_parallel(self):
        """LLM_PARALLEL_CONSENSUS=true → parallel regardless of GPU."""
        with patch("gpu_detect._detect_via_nvidia_smi", return_value=None):
            with patch.dict("os.environ", {"LLM_PARALLEL_CONSENSUS": "true"}):
                flag = self._reload_parallel_flag()
        assert flag is True

    def test_env_false_forces_sequential(self):
        """LLM_PARALLEL_CONSENSUS=false → sequential regardless of GPU."""
        with patch.dict("os.environ", {
            "LLM_PARALLEL_CONSENSUS": "false",
            "GPU_VRAM_MB": "24576",
        }):
            flag = self._reload_parallel_flag()
        assert flag is False

    def test_env_auto_uses_gpu_detection(self):
        """LLM_PARALLEL_CONSENSUS=auto → defers to GPU auto-detect."""
        with patch.dict("os.environ", {
            "LLM_PARALLEL_CONSENSUS": "auto",
            "GPU_VRAM_MB": "12288",
        }):
            flag = self._reload_parallel_flag()
        assert flag is True

    def test_env_unset_uses_gpu_detection(self):
        """LLM_PARALLEL_CONSENSUS unset → defers to GPU auto-detect."""
        env = os.environ.copy()
        env.pop("LLM_PARALLEL_CONSENSUS", None)
        env["GPU_VRAM_MB"] = "2048"
        with patch.dict("os.environ", env, clear=True):
            flag = self._reload_parallel_flag()
        assert flag is False

    def test_env_true_case_insensitive(self):
        """Override is case-insensitive."""
        with patch("gpu_detect._detect_via_nvidia_smi", return_value=None):
            with patch.dict("os.environ", {"LLM_PARALLEL_CONSENSUS": "True"}):
                flag = self._reload_parallel_flag()
        assert flag is True
