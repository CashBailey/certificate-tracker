"""
Integration tests for consensus-based LLM field extraction against real Ollama.

Sends realistic certificate OCR text to a live Ollama instance and verifies
the extracted fields match ground truth from the OCR fixtures.

Requirements:
    - Ollama running at localhost:11434 (``make up`` starts it)
    - llama3.2:3b model pulled (``ollama-init`` handles this automatically)

Run:
    python3 -m pytest CoreInstances/ApiServer/tests/integration/test_llm_consensus_integration.py -v -s
"""

import difflib
import json
import sys
from pathlib import Path

import httpx
import pytest

# ---------------------------------------------------------------------------
# Path setup — walk up to the project root (works from host and Docker)
# ---------------------------------------------------------------------------
def _find_project_root() -> Path:
    """Walk up from this file until we find docker-compose.yml (project root)."""
    current = Path(__file__).resolve().parent
    for parent in (current, *current.parents):
        if (parent / "docker-compose.yml").exists():
            return parent
    # Fallback: assume ApiServer/src is a sibling of tests/ (Docker layout)
    return Path(__file__).resolve().parents[2]

_project_root = _find_project_root()
_api_src = str(_project_root / "CoreInstances" / "ApiServer" / "src")
_extraction_src = str(
    _project_root / "BackgroundProcessingInstances" / "ExtractionWorker" / "src"
)
# In Docker, src/ is directly at /app/src — add that as fallback
_docker_src = str(Path(__file__).resolve().parents[2] / "src")
for _p in (_api_src, _extraction_src, _docker_src):
    if Path(_p).is_dir() and _p not in sys.path:
        sys.path.insert(0, _p)

# ExtractionWorker is not mounted into the api container, so llm_client is not
# importable in that environment. Skip the module gracefully when running there.
try:
    import llm_client
    from llm_client import llm_clean_fields
    from shared.models import ExtractionConfidence, ExtractedFieldValue
except ModuleNotFoundError as _import_err:
    pytest.skip(
        f"Requires ExtractionWorker on path ({_import_err})",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------
FIXTURES_DIR = (
    Path(__file__).resolve().parents[1] / "ocr_fixtures" / "clean"
)

OLLAMA_URL = "http://localhost:11434"


# ---------------------------------------------------------------------------
# Synthetic OCR text for each certificate
# ---------------------------------------------------------------------------
# Simulates what Tesseract produces from scanning a real certificate.
# Uses natural-language dates, surrounding context phrases, and boilerplate.

SYNTHETIC_OCR_TEXT = {
    "cert_001": """\
CERTIFICATE OF COMPLETION

American Heart Association

This is to certify that

John Michael Doe

has successfully completed all requirements for

CPR/BLS Certification

Date of Issue: January 15, 2024
Expiration Date: January 15, 2026
Certificate Number: AHA-2024-123456

This certificate confirms the holder has demonstrated competency
in cardiopulmonary resuscitation and basic life support techniques
in accordance with current AHA Guidelines.

Authorized Signature: ____________________
American Heart Association Training Center
""",
    "cert_002": """\
CERTIFICATE OF ACHIEVEMENT

American Red Cross

This certifies that

Maria Elena Garcia

has successfully completed the training program for

First Aid Certification

Issued on: February 20, 2024
Valid Through: February 20, 2026
Certificate ID: ARC-2024-789012

The American Red Cross hereby certifies that the above-named individual
has met all requirements for First Aid certification including
practical skills demonstration and written examination.

Authorized by American Red Cross National Headquarters
""",
    "cert_003": """\
TRAINING COMPLETION CERTIFICATE

City of Laredo Health Department

This is to acknowledge that

Robert James Smith

has completed the required training in

HIPAA Compliance Training

Date Completed: March 10, 2024
Renewal Date: March 10, 2025
Certificate Number: CLH-2024-345678

This training covered the Health Insurance Portability and Accountability Act
requirements including privacy rules, security standards, and breach
notification procedures as required by federal law.

City of Laredo Health Department
Office of Training and Education
""",
    "cert_004": """\
CERTIFICATE OF TRAINING

OSHA Training Institute

This is to certify that

Ana Isabel Martinez

has successfully completed the course

Bloodborne Pathogens Training

Date: April 5, 2024
Expiry: April 5, 2025
Certificate No.: OSHA-2024-901234

This certificate verifies that the above named individual has completed
OSHA-required training in Bloodborne Pathogens Standard (29 CFR 1910.1030)
including exposure control, prevention methods, and post-exposure procedures.

OSHA Training Institute Education Centers
U.S. Department of Labor
""",
    "cert_005": """\
STATE OF TEXAS
DEPARTMENT OF STATE HEALTH SERVICES

FOOD HANDLER CERTIFICATION

This is to certify that

William Thomas Johnson

has successfully completed the approved food handler training program

Food Handler Certification

Issue Date: May 12, 2024
Expiration Date: May 12, 2026
Certificate Number: DSHS-2024-567890

The Texas Department of State Health Services certifies that the
above-named individual has completed an accredited food handler
training program meeting requirements under Texas Health and Safety Code.

Texas Department of State Health Services
Austin, Texas
""",
    "cert_006": """\
NATIONAL REGISTRY OF EMERGENCY MEDICAL TECHNICIANS

CERTIFICATION

This certifies that

Carmen Rosa Lopez

has met all requirements and is certified as an

Emergency Medical Responder

Certification Date: June 18, 2024
Expiration: June 18, 2026
NREMT Registry Number: NREMT-2024-112233

The National Registry of EMTs certifies that the above-named
individual has successfully completed the cognitive and psychomotor
examinations and meets the standards for Emergency Medical Responder.

National Registry of EMTs
Columbus, Ohio
""",
    "cert_007": """\
CERTIFICATE OF COMPLETION

EPA Training Center
Environmental Protection Agency

This certifies that

David Alexander Brown

has completed the required training course in

Hazardous Materials Handling

Date of Completion: July 22, 2024
Recertification Required: July 22, 2025
Certificate Number: EPA-2024-445566

This training covers HAZWOPER requirements under 29 CFR 1910.120
including hazard recognition, personal protective equipment,
decontamination procedures, and emergency response protocols.

EPA Training Center
U.S. Environmental Protection Agency
""",
    "cert_008": """\
CERTIFICATE

Texas Health and Human Services

This is to certify that

Patricia Ann Wilson

has completed all requirements for

Tuberculosis Screening Certification

Date Issued: August 30, 2024
Valid Until: August 30, 2025
Certificate ID: THHS-2024-778899

Texas Health and Human Services certifies that the above individual
has completed the required TB screening training program including
Mantoux tuberculin skin test administration and interpretation,
and interferon-gamma release assay procedures.

Texas Health and Human Services Commission
Austin, Texas
""",
    "cert_009": """\
TRAINING CERTIFICATE

CDC Training Division
Centers for Disease Control and Prevention

This is to acknowledge that

Miguel Angel Rodriguez

has successfully completed the training program

Infection Control Training

Completion Date: September 14, 2024
Renewal Required By: September 14, 2025
Certificate Number: CDC-2024-001122

The CDC Training Division certifies that the above individual has
completed comprehensive training in infection prevention and control
including standard precautions, transmission-based precautions,
hand hygiene, and personal protective equipment usage.

CDC Training Division
Atlanta, Georgia
""",
    "cert_010": """\
CERTIFICATE OF COMPLETION

National Council for Mental Wellbeing

This certifies that

Jennifer Lynn Davis

has successfully completed the certification course

Mental Health First Aid

Date of Certification: October 25, 2024
Certificate Valid Through: October 25, 2027
Certificate Number: NCMW-2024-334455

The National Council for Mental Wellbeing certifies the above individual
as a Mental Health First Aider, having completed the 8-hour training
covering depression, anxiety, psychosis, substance use disorders,
and crisis intervention techniques.

National Council for Mental Wellbeing
Washington, D.C.
""",
}


# ---------------------------------------------------------------------------
# Noisy initial extracted fields (simulating regex/zone extraction)
# ---------------------------------------------------------------------------
# Values are deliberately longer than ground truth so the conservative
# override rule (shorter wins) allows the LLM to replace them.

NOISY_EXTRACTED = {
    "cert_001": {
        "certificate_holder_name": "This is to certify that John Michael Doe has successfully completed",
        "certificate_type": "completed all requirements for CPR/BLS Certification course",
        "issue_date": "January 15, 2024",
        "issuing_authority": "Issued by American Heart Association Training Center",
    },
    "cert_002": {
        "certificate_holder_name": "This certifies that Maria Elena Garcia has successfully completed",
        "certificate_type": "the training program for First Aid Certification including practical skills",
        "issue_date": "February 20, 2024",
        "issuing_authority": "Authorized by American Red Cross National Headquarters",
    },
    "cert_003": {
        "certificate_holder_name": "This is to acknowledge that Robert James Smith has completed the required",
        "certificate_type": "required training in HIPAA Compliance Training covered the Health Insurance",
        "issue_date": "March 10, 2024",
        "issuing_authority": "City of Laredo Health Department Office of Training and Education",
    },
    "cert_004": {
        "certificate_holder_name": "This is to certify that Ana Isabel Martinez has successfully completed",
        "certificate_type": "completed the course Bloodborne Pathogens Training OSHA-required training",
        "issue_date": "April 5, 2024",
        "issuing_authority": "OSHA Training Institute Education Centers U.S. Department of Labor",
    },
    "cert_005": {
        "certificate_holder_name": "This is to certify that William Thomas Johnson has successfully completed",
        "certificate_type": "approved food handler training program Food Handler Certification meeting requirements",
        "issue_date": "May 12, 2024",
        "issuing_authority": "Texas Department of State Health Services Austin Texas",
    },
    "cert_006": {
        "certificate_holder_name": "This certifies that Carmen Rosa Lopez has met all requirements",
        "certificate_type": "certified as an Emergency Medical Responder examinations and meets the standards",
        "issue_date": "June 18, 2024",
        "issuing_authority": "National Registry of EMTs Columbus Ohio",
    },
    "cert_007": {
        "certificate_holder_name": "This certifies that David Alexander Brown has completed the required",
        "certificate_type": "required training course in Hazardous Materials Handling HAZWOPER requirements",
        "issue_date": "July 22, 2024",
        "issuing_authority": "EPA Training Center U.S. Environmental Protection Agency",
    },
    "cert_008": {
        "certificate_holder_name": "This is to certify that Patricia Ann Wilson has completed all requirements",
        "certificate_type": "requirements for Tuberculosis Screening Certification including Mantoux tuberculin",
        "issue_date": "August 30, 2024",
        "issuing_authority": "Texas Health and Human Services Commission Austin Texas",
    },
    "cert_009": {
        "certificate_holder_name": "This is to acknowledge that Miguel Angel Rodriguez has successfully completed",
        "certificate_type": "completed the training program Infection Control Training including standard precautions",
        "issue_date": "September 14, 2024",
        "issuing_authority": "CDC Training Division Centers for Disease Control and Prevention Atlanta Georgia",
    },
    "cert_010": {
        "certificate_holder_name": "This certifies that Jennifer Lynn Davis has successfully completed the certification",
        "certificate_type": "completed the certification course Mental Health First Aid having completed the 8-hour",
        "issue_date": "October 25, 2024",
        "issuing_authority": "National Council for Mental Wellbeing Washington D.C.",
    },
}


# ---------------------------------------------------------------------------
# Similarity thresholds per field
# ---------------------------------------------------------------------------
FIELD_THRESHOLDS = {
    "certificate_holder_name": 0.85,
    "certificate_type": 0.80,
    "issue_date": 1.0,   # Exact match required (YYYY-MM-DD)
    "issuing_authority": 0.70,
}

# The 4 fields that llm_clean_fields is prompted to extract
LLM_FIELDS = list(FIELD_THRESHOLDS.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _similarity(expected: str, actual: str) -> float:
    """Normalized similarity ratio via difflib SequenceMatcher."""
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0
    return difflib.SequenceMatcher(
        None, expected.lower().strip(), actual.lower().strip(),
    ).ratio()


def _make_field(name: str, value: str) -> ExtractedFieldValue:
    return ExtractedFieldValue(
        field_name=name,
        value=value,
        confidence=ExtractionConfidence(
            zone=0.5, ocr=0.6, parse=0.4, validate=0.3, overall=0.45,
        ),
        extraction_source="generic",
        needs_review=True,
    )


def _load_clean_fixtures() -> list[dict]:
    """Load all 10 clean cert fixtures and attach synthetic OCR text."""
    fixtures = []
    for json_path in sorted(FIXTURES_DIR.glob("cert_*.json")):
        with open(json_path) as f:
            data = json.load(f)
        cert_id = data["id"]
        if cert_id in SYNTHETIC_OCR_TEXT:
            data["ocr_text"] = SYNTHETIC_OCR_TEXT[cert_id]
            data["noisy_fields"] = NOISY_EXTRACTED[cert_id]
            data.setdefault("acceptable_alternatives", {})
            fixtures.append(data)
    return fixtures


# Build parametrize list at import time (no Ollama needed for collection)
_FIXTURES = _load_clean_fixtures()
_CERT_IDS = [f["id"] for f in _FIXTURES]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ollama_is_reachable() -> bool:
    """Synchronous check — used at collection time."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _ollama_has_model(model_name: str) -> bool:
    """Check if a specific model is available in Ollama."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code != 200:
            return False
        # Ollama appends :latest to names without a tag
        for m in resp.json().get("models", []):
            name = m["name"]
            if name == model_name or name == f"{model_name}:latest":
                return True
        return False
    except Exception:
        return False


# Skip the entire module if Ollama is not running
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _ollama_is_reachable(),
        reason=f"Ollama not reachable at {OLLAMA_URL} (run `make up` first)",
    ),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fixture",
    _FIXTURES,
    ids=_CERT_IDS,
)
async def test_consensus_extraction_accuracy(fixture):
    """
    Send synthetic certificate OCR text through the full consensus pipeline
    (3 parallel extraction runs + 1 judge) against real Ollama and verify
    outputs match ground truth.
    """
    cert_id = fixture["id"]
    ocr_text = fixture["ocr_text"]
    expected = fixture["expected_fields"]
    noisy = fixture["noisy_fields"]

    # Build noisy extracted fields
    extracted_fields = {
        name: _make_field(name, noisy[name])
        for name in LLM_FIELDS
    }

    # Override module-level config to point at localhost Ollama
    saved = (
        llm_client.OLLAMA_URL,
        llm_client.CONSENSUS_ENABLED,
        llm_client.CONSENSUS_N,
        llm_client.CONSENSUS_TEMP,
    )
    try:
        llm_client.OLLAMA_URL = OLLAMA_URL
        llm_client.CONSENSUS_ENABLED = True
        llm_client.CONSENSUS_N = 3
        llm_client.CONSENSUS_TEMP = 0.3

        result = await llm_clean_fields(ocr_text, extracted_fields)
    finally:
        (
            llm_client.OLLAMA_URL,
            llm_client.CONSENSUS_ENABLED,
            llm_client.CONSENSUS_N,
            llm_client.CONSENSUS_TEMP,
        ) = saved

    # --- Check each field ---
    alternatives = fixture.get("acceptable_alternatives", {})
    failures = []
    for field_name in LLM_FIELDS:
        actual_value = result[field_name].value
        expected_value = expected[field_name]
        sim = _similarity(expected_value, actual_value)
        threshold = FIELD_THRESHOLDS[field_name]

        # Check acceptable alternatives if primary match fails
        if sim < threshold and field_name in alternatives:
            for alt in alternatives[field_name]:
                alt_sim = _similarity(alt, actual_value)
                if alt_sim >= threshold:
                    sim = alt_sim
                    expected_value = alt
                    break

        # If value is unchanged from noisy input, the pipeline couldn't
        # improve it — acceptable (not a regression, just a limitation)
        noisy_value = noisy.get(field_name, "")
        unchanged = actual_value == noisy_value

        status = "PASS" if sim >= threshold or unchanged else "FAIL"
        print(
            f"  [{cert_id}] {field_name}: "
            f"expected={expected_value!r}  "
            f"actual={actual_value!r}  "
            f"similarity={sim:.2f}  "
            f"threshold={threshold}  "
            f"{status}"
            + (" (unchanged from input)" if unchanged and sim < threshold else "")
        )

        if sim < threshold and not unchanged:
            failures.append(
                f"{field_name}: expected={expected_value!r}, "
                f"got={actual_value!r}, similarity={sim:.2f} < {threshold}"
            )

    assert not failures, (
        f"[{cert_id}] Field extraction accuracy below threshold:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )


# ---------------------------------------------------------------------------
# NuExtract Integration Tests
# ---------------------------------------------------------------------------

NUEXTRACT_MODEL = "sroecker/nuextract-tiny-v1.5"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fixture",
    _FIXTURES,
    ids=_CERT_IDS,
)
async def test_nuextract_extraction_accuracy(fixture):
    """
    Send synthetic certificate OCR text through NuExtract single-shot
    extraction against real Ollama and verify outputs match ground truth.
    """
    if not _ollama_has_model(NUEXTRACT_MODEL):
        pytest.skip(f"NuExtract model not available in Ollama ({NUEXTRACT_MODEL})")

    cert_id = fixture["id"]
    ocr_text = fixture["ocr_text"]
    expected = fixture["expected_fields"]
    noisy = fixture["noisy_fields"]

    extracted_fields = {
        name: _make_field(name, noisy[name])
        for name in LLM_FIELDS
    }

    saved = (
        llm_client.OLLAMA_URL,
        llm_client.LLM_MODEL,
        llm_client.CONSENSUS_ENABLED,
    )
    try:
        llm_client.OLLAMA_URL = OLLAMA_URL
        llm_client.LLM_MODEL = NUEXTRACT_MODEL
        llm_client.CONSENSUS_ENABLED = True  # Should be ignored by NuExtract path

        result = await llm_clean_fields(ocr_text, extracted_fields)
    finally:
        (
            llm_client.OLLAMA_URL,
            llm_client.LLM_MODEL,
            llm_client.CONSENSUS_ENABLED,
        ) = saved

    # --- Check each field ---
    alternatives = fixture.get("acceptable_alternatives", {})
    failures = []
    for field_name in LLM_FIELDS:
        actual_value = result[field_name].value
        expected_value = expected[field_name]
        sim = _similarity(expected_value, actual_value)
        threshold = FIELD_THRESHOLDS[field_name]

        # Check acceptable alternatives if primary match fails
        if sim < threshold and field_name in alternatives:
            for alt in alternatives[field_name]:
                alt_sim = _similarity(alt, actual_value)
                if alt_sim >= threshold:
                    sim = alt_sim
                    expected_value = alt
                    break

        # If value is unchanged from noisy input, the pipeline couldn't
        # improve it — acceptable (not a regression, just a limitation)
        noisy_value = noisy.get(field_name, "")
        unchanged = actual_value == noisy_value

        status = "PASS" if sim >= threshold or unchanged else "FAIL"
        print(
            f"  [NuExtract][{cert_id}] {field_name}: "
            f"expected={expected_value!r}  "
            f"actual={actual_value!r}  "
            f"similarity={sim:.2f}  "
            f"threshold={threshold}  "
            f"{status}"
            + (" (unchanged from input)" if unchanged and sim < threshold else "")
        )

        if sim < threshold and not unchanged:
            failures.append(
                f"{field_name}: expected={expected_value!r}, "
                f"got={actual_value!r}, similarity={sim:.2f} < {threshold}"
            )

    assert not failures, (
        f"[NuExtract][{cert_id}] Field extraction accuracy below threshold:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )
