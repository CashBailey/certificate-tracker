"""
OCR accuracy tests for certificate extraction.

Tests that OCR correctly extracts text from certificate images by comparing
extracted values against labeled ground truth.

These tests require:
1. Tesseract OCR to be installed (skipped if not available)
2. OCR test fixtures to be generated (run generate_test_certs.py first)

Run with: pytest tests/ocr/ -v -m ocr
"""

import json
import shutil
from pathlib import Path

import pytest

# Check if Tesseract is available
TESSERACT_AVAILABLE = shutil.which("tesseract") is not None

# Check if pytesseract is installed
try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

# Path to fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "ocr_fixtures"


def get_fixture_paths() -> list[Path]:
    """Get all JSON ground truth files."""
    if not FIXTURES_DIR.exists():
        return []

    paths = []
    for category in ["clean", "skewed", "degraded", "scanned"]:
        category_dir = FIXTURES_DIR / category
        if category_dir.exists():
            paths.extend(sorted(category_dir.glob("*.json")))
    return paths


# Get fixture paths for parametrization
FIXTURE_PATHS = get_fixture_paths()


@pytest.mark.ocr
@pytest.mark.skipif(
    not TESSERACT_AVAILABLE,
    reason="Tesseract not installed - install with: apt-get install tesseract-ocr",
)
@pytest.mark.skipif(
    not PYTESSERACT_AVAILABLE,
    reason="pytesseract not installed - install with: pip install pytesseract",
)
@pytest.mark.skipif(
    len(FIXTURE_PATHS) == 0,
    reason="No OCR fixtures found - run: python tests/ocr_fixtures/generator/generate_test_certs.py",
)
class TestOCRAccuracy:
    """Tests for OCR extraction accuracy against labeled ground truth."""

    @pytest.fixture
    def ocr_image(self):
        """
        Factory fixture that performs OCR on an image and returns extracted text.

        Returns a function that takes an image path and returns the full OCR text.
        """
        from PIL import Image

        def _ocr(image_path: Path) -> str:
            image = Image.open(image_path)
            # Use English + Spanish for Laredo (bilingual community)
            text = pytesseract.image_to_string(image, lang="eng")
            return text

        return _ocr

    @pytest.mark.parametrize(
        "fixture_path",
        FIXTURE_PATHS,
        ids=lambda p: p.stem,  # Use filename as test ID
    )
    def test_ocr_extracts_certificate_holder_name(
        self,
        fixture_path: Path,
        ocr_image,
        similarity_calculator,
    ):
        """OCR should correctly extract the certificate holder name."""
        # Load ground truth
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        # Skip for heavy blur or severe skew - text is unreadable/distorted
        distortions = ground_truth.get("distortions", [])
        if "blur_2" in distortions or "skew_10" in distortions:
            pytest.skip("Heavy blur/severe skew makes text unreadable")

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        # Run OCR
        ocr_text = ocr_image(image_path)

        # Check if name appears in OCR output
        expected_name = ground_truth["expected_fields"]["certificate_holder_name"]
        threshold = ground_truth["accuracy_threshold"]

        # Search for name in OCR text (case-insensitive)
        name_found = expected_name.lower() in ocr_text.lower()

        # Also check similarity if exact match not found
        if not name_found:
            # Try to find best matching line
            lines = ocr_text.split("\n")
            best_similarity = 0.0
            for line in lines:
                sim = similarity_calculator(expected_name, line.strip())
                best_similarity = max(best_similarity, sim)

            assert best_similarity >= threshold, (
                f"Certificate holder name not found with sufficient accuracy.\n"
                f"Expected: '{expected_name}'\n"
                f"Best match similarity: {best_similarity:.2%}\n"
                f"Required threshold: {threshold:.2%}\n"
                f"Distortions: {ground_truth.get('distortions', [])}"
            )

    @pytest.mark.parametrize(
        "fixture_path",
        FIXTURE_PATHS,
        ids=lambda p: p.stem,
    )
    def test_ocr_extracts_certificate_type(
        self,
        fixture_path: Path,
        ocr_image,
        similarity_calculator,
    ):
        """OCR should correctly extract the certificate type."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        # Skip for heavy blur or severe skew - text is unreadable
        distortions = ground_truth.get("distortions", [])
        if "blur_2" in distortions or "skew_10" in distortions:
            pytest.skip("Heavy blur/severe skew makes certificate type unreadable")

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = ocr_image(image_path)
        expected_type = ground_truth["expected_fields"]["certificate_type"]
        threshold = ground_truth["accuracy_threshold"]

        # Check if certificate type appears in OCR output
        type_found = expected_type.lower() in ocr_text.lower()

        if not type_found:
            lines = ocr_text.split("\n")
            best_similarity = 0.0
            for line in lines:
                sim = similarity_calculator(expected_type, line.strip())
                best_similarity = max(best_similarity, sim)

            assert best_similarity >= threshold, (
                f"Certificate type not found with sufficient accuracy.\n"
                f"Expected: '{expected_type}'\n"
                f"Best match similarity: {best_similarity:.2%}\n"
                f"Required threshold: {threshold:.2%}"
            )

    @pytest.mark.parametrize(
        "fixture_path",
        FIXTURE_PATHS,
        ids=lambda p: p.stem,
    )
    def test_ocr_extracts_dates(
        self,
        fixture_path: Path,
        ocr_image,
    ):
        """OCR should correctly extract issue and expiration dates."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        # Skip date tests for heavily degraded images
        # Dates like "2024-01-15" are small and often unreadable under heavy degradation or skew
        distortions = ground_truth.get("distortions", [])
        heavy_degradation = {"blur_2", "lowdpi_150", "skew_10"}
        if any(d in heavy_degradation for d in distortions):
            pytest.skip("Dates are too small for reliable OCR under heavy degradation/skew")

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = ocr_image(image_path)
        expected_issue = ground_truth["expected_fields"]["issue_date"]
        expected_expiry = ground_truth["expected_fields"]["expiration_date"]

        # Dates should appear in OCR text
        # Allow for OCR variations in date format
        issue_found = expected_issue in ocr_text or expected_issue.replace("-", "/") in ocr_text
        expiry_found = expected_expiry in ocr_text or expected_expiry.replace("-", "/") in ocr_text

        # For degraded images, lower threshold
        threshold = ground_truth["accuracy_threshold"]
        if threshold < 0.85:
            # Degraded images may not extract dates perfectly
            # At least one date should be found
            assert issue_found or expiry_found, (
                f"Neither date found in OCR output.\n"
                f"Expected issue: '{expected_issue}'\n"
                f"Expected expiry: '{expected_expiry}'\n"
                f"Distortions: {ground_truth.get('distortions', [])}"
            )
        else:
            # Clean/light distortion should get both dates
            assert issue_found, f"Issue date '{expected_issue}' not found in OCR output"
            assert expiry_found, f"Expiration date '{expected_expiry}' not found in OCR output"

    @pytest.mark.parametrize(
        "fixture_path",
        FIXTURE_PATHS,
        ids=lambda p: p.stem,
    )
    def test_ocr_extracts_certificate_number(
        self,
        fixture_path: Path,
        ocr_image,
        similarity_calculator,
    ):
        """OCR should correctly extract the certificate number."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        # Skip certificate number test for degraded images and heavy skew
        # Small alphanumeric text (e.g., "AHA-2024-123456") is inherently difficult
        # for OCR under degradation conditions or significant rotation
        distortions = ground_truth.get("distortions", [])
        skip_distortions = {"blur_1", "blur_2", "jpeg_40", "lowdpi_150", "noise", "skew_10"}
        if any(d in skip_distortions for d in distortions):
            pytest.skip("Certificate numbers are too small for reliable OCR under degradation/heavy skew")

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = ocr_image(image_path)
        expected_number = ground_truth["expected_fields"]["certificate_number"]
        threshold = ground_truth["accuracy_threshold"]

        # Certificate numbers often have OCR issues with similar characters (0/O, 1/l)
        # Check if the expected number appears directly in text (exact or near-exact match)
        if expected_number in ocr_text:
            return  # Pass - exact match found

        # Try fuzzy match on each word/segment
        best_similarity = 0.0
        best_match = ""

        # Split text into words and check each
        import re
        # Split on whitespace, colons, and other separators
        segments = re.split(r'[\s:,;]+', ocr_text)
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            sim = similarity_calculator(expected_number, segment)
            if sim > best_similarity:
                best_similarity = sim
                best_match = segment

        # Also check substrings in lines containing "cert" or similar
        for line in ocr_text.split("\n"):
            if "cert" in line.lower() or "no:" in line.lower() or "no." in line.lower():
                # Extract text after colon or "No"
                parts = re.split(r'(?:No[.:]?|:)\s*', line, flags=re.IGNORECASE)
                for part in parts:
                    part = part.strip()
                    if part:
                        sim = similarity_calculator(expected_number, part)
                        if sim > best_similarity:
                            best_similarity = sim
                            best_match = part

        # Certificate numbers are harder to OCR, use lower threshold
        adjusted_threshold = max(threshold - 0.15, 0.55)

        assert best_similarity >= adjusted_threshold, (
            f"Certificate number not found with sufficient accuracy.\n"
            f"Expected: '{expected_number}'\n"
            f"Best match: '{best_match}' ({best_similarity:.2%})\n"
            f"Required threshold: {adjusted_threshold:.2%}"
        )


@pytest.mark.ocr
class TestOCRFixtureIntegrity:
    """Tests for OCR fixture file integrity."""

    def test_all_json_have_matching_png(self):
        """Every JSON ground truth file should have a matching PNG image."""
        missing = []
        for json_path in FIXTURE_PATHS:
            png_path = json_path.with_suffix(".png")
            if not png_path.exists():
                missing.append(json_path.name)

        assert not missing, f"Missing PNG files for: {missing}"

    def test_ground_truth_has_required_fields(self):
        """All ground truth files should have required fields."""
        required_fields = [
            "certificate_holder_name",
            "certificate_type",
            "issue_date",
            "expiration_date",
        ]

        invalid = []
        for json_path in FIXTURE_PATHS:
            with open(json_path, "r") as f:
                data = json.load(f)

            expected_fields = data.get("expected_fields", {})
            missing = [f for f in required_fields if f not in expected_fields]

            if missing:
                invalid.append((json_path.name, missing))

        assert not invalid, f"Fixtures missing required fields: {invalid}"

    def test_accuracy_thresholds_are_valid(self):
        """Accuracy thresholds should be between 0 and 1."""
        invalid = []
        for json_path in FIXTURE_PATHS:
            with open(json_path, "r") as f:
                data = json.load(f)

            threshold = data.get("accuracy_threshold", 0)
            if not (0 <= threshold <= 1):
                invalid.append((json_path.name, threshold))

        assert not invalid, f"Invalid accuracy thresholds: {invalid}"
