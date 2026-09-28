"""
Local LLM client for intelligent field extraction cleanup.

Calls Ollama HTTP API to clean up noisy OCR-extracted field values.
Uses Consensus-Based Hallucination Mitigation: runs N independent
inference passes (parallel when GPU VRAM >4 GB, sequential otherwise),
applies majority vote, and uses a judge call to select the best values.
Gracefully falls back to existing values if Ollama is unavailable.
"""

import asyncio
import json
import logging
import os
from collections import Counter
from datetime import datetime
from typing import Optional

import httpx

from shared.models import CANONICAL_FIELDS, ExtractionConfidence, ExtractedFieldValue
from gpu_detect import detect_gpu, should_parallelize_consensus

_CANONICAL_SET = frozenset(CANONICAL_FIELDS)

log = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))

CONSENSUS_N = int(os.getenv("LLM_CONSENSUS_N", "3"))
CONSENSUS_ENABLED = os.getenv("LLM_CONSENSUS_ENABLED", "true").lower() == "true"
CONSENSUS_TEMP = float(os.getenv("LLM_CONSENSUS_TEMP", "0.3"))
NUEXTRACT_TEMP_STEP = float(os.getenv("LLM_NUEXTRACT_TEMP_STEP", "0.05"))

# GPU auto-detection at startup (§5.1): >4 GB VRAM → parallel consensus
_GPU_INFO = detect_gpu()
PARALLEL_CONSENSUS = should_parallelize_consensus(_GPU_INFO)

# Environment override: true/false forces mode, "auto" or unset uses GPU detection
_parallel_override = os.getenv("LLM_PARALLEL_CONSENSUS", "auto").lower().strip()
if _parallel_override == "true":
    PARALLEL_CONSENSUS = True
    _parallel_reason = "forced by LLM_PARALLEL_CONSENSUS=true"
elif _parallel_override == "false":
    PARALLEL_CONSENSUS = False
    _parallel_reason = "forced by LLM_PARALLEL_CONSENSUS=false"
else:
    _parallel_reason = (
        "GPU auto-detect: %s, %s MB VRAM"
        % (_GPU_INFO.device_name or "none", _GPU_INFO.vram_total_mb or "N/A")
    )

log.info(
    "LLM consensus mode: %s (%s)",
    "parallel" if PARALLEL_CONSENSUS else "sequential",
    _parallel_reason,
)

JUDGE_MODEL = "llama3.2:3b"

NUEXTRACT_TEMPLATE = json.dumps({
    "certificate_holder_name": "",
    "course_name": "",
    "issue_date": "",
    "issuing_organization": "",
}, indent=2)

# Map NuExtract field names back to standard field names used by the system
_NUEXTRACT_FIELD_MAP = {
    "course_name": "certificate_type",
    "issuing_organization": "issuing_authority",
}

NUEXTRACT_PROMPT_TEMPLATE = """\
<|input|>
### Template:
{template}
### Text:
{input_text}

<|output|>
"""

EXTRACTION_PROMPT = """\
Extract the following fields from this certificate/training document text. \
Return ONLY a valid JSON object with the fields below. \
If a field is not found, set its value to null.

Text:
{ocr_text}

Fields to extract:
- certificate_holder_name: The person's full name only (e.g. "John Smith"). Do NOT include surrounding phrases like "presented to" or "awarded to".
- certificate_type: The course or training name only (e.g. "Sexual Harassment Prevention Training"). Do NOT include organization names or dates.
- issue_date: The date the certificate was issued, in YYYY-MM-DD format. Convert any date format to YYYY-MM-DD.
- issuing_authority: The organization that issued this certificate.

Return ONLY valid JSON, no explanation:"""

JUDGE_PROMPT = """\
You are a judge evaluating multiple extraction attempts from a certificate document.

Multiple independent attempts extracted fields from the same document. Your job is to \
pick the MOST LIKELY CORRECT value for EACH field based on the original text. \
Do NOT invent new values — pick only from the candidate values provided.

Original document text:
{ocr_text}

Candidate extractions:
{candidates_text}

Return ONLY a valid JSON object with each field name as a key and the correct \
value for that field. Pick from the candidates only. \
Return ONLY valid JSON, no explanation:"""


async def _call_ollama(
    prompt: str, temperature: float = 0.0, model: Optional[str] = None,
) -> Optional[str]:
    """
    Call Ollama generate API.

    Returns the response text, or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model or LLM_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": 512,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
    except httpx.ConnectError:
        log.debug("Ollama not available at %s, skipping LLM cleanup", OLLAMA_URL)
        return None
    except httpx.TimeoutException:
        log.warning("Ollama request timed out after %ss", LLM_TIMEOUT)
        return None
    except Exception as e:
        log.warning("Ollama request failed: %s", e)
        return None


def _parse_llm_response(response_text: str) -> Optional[dict]:
    """
    Parse JSON from LLM response, handling common formatting issues.
    """
    if not response_text:
        return None

    text = response_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the response
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    log.warning(
        "Could not parse LLM response as JSON (response_chars=%d)",
        len(text),
    )
    return None


async def _call_ollama_n_times(
    prompt: str, n: int, temperature: float | list[float],
    *, parallel: Optional[bool] = None,
) -> list[dict]:
    """
    Run the same prompt through Ollama N times.

    Execution mode is chosen by GPU auto-detection at startup:
      - >4 GB VRAM: all N calls dispatched concurrently (asyncio.gather)
      - ≤4 GB VRAM or no GPU: calls run sequentially

    Args:
        temperature: A single float (same for all runs) or a list of
            per-run temperatures (must have length >= n).
        parallel: Force parallel (True) or sequential (False).  When
            None (default), uses the module-level ``PARALLEL_CONSENSUS``
            flag set by GPU auto-detection.

    Returns:
        List of parsed JSON dicts (may be shorter than N if some runs fail).
    """
    use_parallel = PARALLEL_CONSENSUS if parallel is None else parallel
    temps = temperature if isinstance(temperature, list) else [temperature] * n

    async def _single_run(run_id: int) -> Optional[dict]:
        run_temp = temps[run_id - 1]
        log.debug("Consensus run %d/%d (temp=%.3f)", run_id, n, run_temp)
        response_text = await _call_ollama(prompt, temperature=run_temp)
        if response_text is None:
            return None
        parsed = _parse_llm_response(response_text)
        if not parsed:
            log.debug("Consensus run %d/%d: failed to parse response", run_id, n)
            return None
        return parsed

    if use_parallel:
        log.debug("Consensus: dispatching %d runs in parallel", n)
        results = await asyncio.gather(
            *(_single_run(i + 1) for i in range(n)),
            return_exceptions=True,
        )
    else:
        log.debug("Consensus: running %d runs sequentially", n)
        results = []
        for i in range(n):
            try:
                result = await _single_run(i + 1)
            except Exception as exc:
                result = exc
            results.append(result)

    candidates = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            log.warning("Consensus run %d/%d raised: %s", i + 1, n, result)
        elif result is not None:
            candidates.append(result)

    log.info(
        "Consensus: %d/%d runs produced valid JSON (%s)",
        len(candidates), n,
        "parallel" if use_parallel else "sequential",
    )
    return candidates


def _normalize_for_comparison(value: str) -> str:
    """Normalize a field value for majority vote comparison."""
    return " ".join(value.strip().lower().split())


def _is_nuextract(model: Optional[str] = None) -> bool:
    """Check if the active extraction model is NuExtract."""
    m = (model or LLM_MODEL).lower()
    return "nuextract" in m


def _normalize_date_to_iso(date_str: str) -> str:
    """Attempt to normalize a date string to YYYY-MM-DD format.

    Returns the original string if parsing fails.
    """
    if not date_str or not date_str.strip():
        return date_str

    date_str = date_str.strip()

    # Already in ISO format
    if len(date_str) == 10 and date_str[4:5] == "-" and date_str[7:8] == "-":
        return date_str

    formats = [
        "%B %d, %Y",   # January 15, 2024
        "%B %d %Y",    # January 15 2024
        "%b %d, %Y",   # Jan 15, 2024
        "%b %d %Y",    # Jan 15 2024
        "%m/%d/%Y",    # 01/15/2024
        "%m-%d-%Y",    # 01-15-2024
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_str


def _build_nuextract_prompt(ocr_text: str) -> str:
    """Build the NuExtract-format prompt for template-based extraction."""
    return NUEXTRACT_PROMPT_TEMPLATE.format(
        template=NUEXTRACT_TEMPLATE,
        input_text=ocr_text[:3000],
    )


def _postprocess_nuextract(fields: dict) -> dict:
    """Post-process NuExtract output: remap field names and normalize dates."""
    # Remap descriptive NuExtract field names to standard names
    remapped = {}
    for k, v in fields.items():
        standard_name = _NUEXTRACT_FIELD_MAP.get(k, k)
        remapped[standard_name] = v

    # Normalize dates
    for date_key in ("issue_date", "expiration_date",
                     "date_certificate_was_issued"):
        if date_key in remapped and isinstance(remapped[date_key], str):
            remapped[date_key] = _normalize_date_to_iso(remapped[date_key])
    return remapped


def _majority_vote(candidates: list[dict]) -> tuple[dict, list[str]]:
    """
    Deterministic per-field majority vote across candidate outputs.

    For each field, normalizes values and counts occurrences.
    A value appearing in >= 2 candidates wins. Original casing is preserved
    from the first candidate that produced the winning value.

    Returns:
        (consensus_fields, disputed_field_names)
        - consensus_fields: dict of field_name -> winning value (or None)
        - disputed_field_names: list of fields where no majority exists
    """
    # Collect all field names across all candidates
    all_fields: set[str] = set()
    for c in candidates:
        all_fields.update(c.keys())

    consensus = {}
    disputed = []

    for field in all_fields:
        # Gather (normalized, original) pairs for this field
        values: list[tuple[str, str]] = []
        for c in candidates:
            raw = c.get(field)
            if isinstance(raw, str) and raw.strip():
                values.append((_normalize_for_comparison(raw), raw.strip()))

        if not values:
            consensus[field] = None
            continue

        # Count by normalized value
        counts = Counter(norm for norm, _ in values)
        winner_norm, winner_count = counts.most_common(1)[0]

        majority_threshold = len(candidates) / 2
        if winner_count > majority_threshold:
            # Use original casing from the first occurrence of the winner
            for norm, original in values:
                if norm == winner_norm:
                    consensus[field] = original
                    break
        else:
            # No majority — mark as disputed
            disputed.append(field)

    if disputed:
        log.info("Consensus: disputed fields (no majority): %s", ", ".join(disputed))

    return consensus, disputed


async def _judge_candidates(
    ocr_text: str,
    candidates: list[dict],
) -> dict:
    """
    Use LLM judge to select the best value for each field across candidates.

    Sends the original OCR text and all candidate values to a judge prompt.
    The judge picks the most likely correct value from the candidates for
    every field (does not invent new ones).

    Returns:
        Dict of field_name -> adjudicated value (empty dict on failure).
    """
    all_fields: set[str] = set()
    for c in candidates:
        all_fields.update(c.keys())

    lines = []
    for field in sorted(all_fields):
        field_values = []
        for i, c in enumerate(candidates):
            val = c.get(field)
            if isinstance(val, str) and val.strip():
                field_values.append(f'  Run {i+1}: "{val.strip()}"')
        if field_values:
            lines.append(f"{field}:")
            lines.extend(field_values)

    candidates_text = "\n".join(lines)

    prompt = JUDGE_PROMPT.format(
        ocr_text=ocr_text[:2000],
        candidates_text=candidates_text,
    )

    # Judge runs at temperature=0 for deterministic adjudication
    # Always use JUDGE_MODEL (instruction-following) regardless of LLM_MODEL
    response_text = await _call_ollama(prompt, temperature=0.0, model=JUDGE_MODEL)
    if not response_text:
        return {}

    parsed = _parse_llm_response(response_text)
    if not parsed:
        return {}

    # Enforce the judge's candidate-only contract in code. Prompt instructions
    # are not a validation boundary and document text is untrusted.
    allowed_values: dict[str, dict[str, str]] = {}
    for candidate in candidates:
        for field, value in candidate.items():
            if isinstance(value, str) and value.strip():
                normalized = _normalize_for_comparison(value)
                allowed_values.setdefault(field, {}).setdefault(
                    normalized,
                    value.strip(),
                )

    result = {}
    for field in all_fields:
        val = parsed.get(field)
        if isinstance(val, str) and val.strip():
            normalized = _normalize_for_comparison(val)
            selected = allowed_values.get(field, {}).get(normalized)
            if selected is not None:
                result[field] = selected

    log.info(
        "Judge resolved fields: %s",
        ", ".join(sorted(result.keys())) if result else "none",
    )
    return result


def _apply_fields_to_extracted(
    llm_fields: dict,
    extracted_fields: dict[str, ExtractedFieldValue],
) -> list[str]:
    """
    Apply LLM-derived field values to the extracted fields dict.

    Only overrides if the LLM value is shorter/cleaner or the field is empty.

    Returns:
        List of field names that were updated.
    """
    fields_updated = []
    for field_name, llm_value in llm_fields.items():
        if not llm_value or field_name not in _CANONICAL_SET:
            continue

        if not isinstance(llm_value, str) or not llm_value.strip():
            continue

        clean_value = llm_value.strip()

        if field_name not in extracted_fields:
            # LLM discovered a field that regex didn't find — add it
            extracted_fields[field_name] = ExtractedFieldValue(
                field_name=field_name,
                value=clean_value,
                confidence=ExtractionConfidence(
                    zone=0.0, ocr=0.0, parse=0.0, validate=0.0, overall=0.5,
                ),
                extraction_source="llm",
                needs_review=True,
            )
            fields_updated.append(field_name)
        else:
            field = extracted_fields[field_name]
            # Never override template-authoritative fields
            if field.extraction_source == "template_metadata":
                continue
            # Only override if LLM produced a shorter, cleaner value
            # (avoid replacing good values with hallucinated ones)
            if len(clean_value) < len(field.value or "") or not field.value:
                field.value = clean_value
                field.confidence = ExtractionConfidence(
                    zone=0.0,
                    ocr=0.0,
                    parse=0.0,
                    validate=0.0,
                    overall=0.5,
                )
                field.extraction_source = "llm"
                field.needs_review = True
                fields_updated.append(field_name)

    return fields_updated


async def llm_clean_fields(
    ocr_text: str,
    extracted_fields: dict[str, ExtractedFieldValue],
) -> dict[str, ExtractedFieldValue]:
    """
    Use local LLM to clean up extracted field values.

    Supports two model types:
    - llama3.2:3b (default): Instruction-following with consensus pipeline
      (N runs at CONSENSUS_TEMP, majority vote + judge)
    - NuExtract: Template-based extraction with consensus pipeline
      (N runs at tiny varied temps [0.0, 0.01, 0.02, ...], majority vote + judge)

    Falls back gracefully — if LLM is unavailable or returns bad data,
    the original extracted_fields are returned unchanged.

    Args:
        ocr_text: Full OCR text from the document
        extracted_fields: Current regex-extracted fields

    Returns:
        Same dict with values cleaned up by LLM (or unchanged on failure)
    """
    if not ocr_text or not ocr_text.strip():
        return extracted_fields

    nuextract = _is_nuextract()

    # Build model-appropriate prompt
    if nuextract:
        prompt = _build_nuextract_prompt(ocr_text)
    else:
        prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text[:3000])

    # --- Single-run path (consensus disabled or N <= 1) ---
    if not CONSENSUS_ENABLED or CONSENSUS_N <= 1:
        response_text = await _call_ollama(prompt, temperature=0.0)
        if not response_text:
            return extracted_fields

        llm_fields = _parse_llm_response(response_text)
        if not llm_fields:
            return extracted_fields

        if nuextract:
            llm_fields = _postprocess_nuextract(llm_fields)

        fields_updated = _apply_fields_to_extracted(llm_fields, extracted_fields)
        if fields_updated:
            log.info("LLM cleaned fields: %s", ", ".join(fields_updated))
        return extracted_fields

    # --- Consensus path (N parallel runs + majority vote + judge) ---
    # NuExtract: tiny temperature variation per run (0.0, 0.01, 0.02, ...)
    # llama3.2:  same temperature for all runs (e.g. 0.3)
    if nuextract:
        temps = [i * NUEXTRACT_TEMP_STEP for i in range(CONSENSUS_N)]
    else:
        temps = CONSENSUS_TEMP

    log.info(
        "Starting consensus extraction: N=%d, temps=%s",
        CONSENSUS_N,
        temps if isinstance(temps, list) else f"{temps:.2f}",
    )

    candidates = await _call_ollama_n_times(prompt, CONSENSUS_N, temps)

    if not candidates:
        return extracted_fields

    # NuExtract: normalize dates in each candidate before majority vote
    # so "January 15, 2024" and "2024-01-15" compare as the same value
    if nuextract:
        candidates = [_postprocess_nuextract(c) for c in candidates]

    # Majority vote (used as fallback if judge fails)
    majority_fields, disputed = _majority_vote(candidates)

    # Judge always runs — it can resolve disputes, fill gaps, and
    # shorten verbose consensus values.  But it can NOT override a
    # unanimous non-empty consensus with a longer/equal value
    # (which would introduce flakiness from the judge model).
    judge_fields = await _judge_candidates(ocr_text, candidates)

    if judge_fields:
        final_fields = dict(majority_fields)
        for field, judge_value in judge_fields.items():
            consensus_value = majority_fields.get(field)
            if field in disputed:
                # Disputed: judge resolves
                final_fields[field] = judge_value
            elif not consensus_value:
                # Empty consensus: judge fills the gap
                final_fields[field] = judge_value
            elif len(judge_value) < len(consensus_value):
                # Unanimous but judge is shorter: prefer concise value
                final_fields[field] = judge_value
            # else: unanimous and judge is longer/equal → keep consensus
    else:
        log.warning("Judge unavailable, falling back to majority vote")
        final_fields = majority_fields

    # NuExtract: normalize dates in final fields (judge may return raw dates)
    if nuextract:
        final_fields = _postprocess_nuextract(final_fields)

    # Apply consensus values
    fields_updated = _apply_fields_to_extracted(final_fields, extracted_fields)
    if fields_updated:
        log.info("LLM consensus cleaned fields: %s", ", ".join(fields_updated))

    return extracted_fields
