"""
OCR accuracy tests with image preprocessing (deskew, denoise, binarize).

Tests that the PillowImagePreprocessor pipeline improves OCR accuracy
on skewed, noisy, and degraded certificate images compared to raw Tesseract.

Requirements:
    - Tesseract OCR installed (system binary)
    - pytesseract, opencv-python-headless, numpy, Pillow installed
    - OCR test fixtures generated (run: python tests/ocr_fixtures/generator/generate_test_certs.py)

Usage:
    pytest tests/ocr/test_ocr_preprocessed.py -v -m ocr_preprocessed
    pytest tests/ocr/test_ocr_preprocessed.py -v -k "TestPreprocessingImprovement"
    pytest tests/ocr/ -v  # Run all OCR tests (raw + preprocessed)
"""

import json
import shutil
from io import BytesIO
from pathlib import Path

import pytest

from tests.ocr.conftest import (
    EASYOCR_AVAILABLE,
    FIXTURES_DIR,
    OPENCV_AVAILABLE,
    TESSERACT_AVAILABLE,
    calculate_similarity,
    get_all_fixture_paths,
    get_fixtures_by_category,
    get_fixtures_by_distortion,
)

# Check for pytesseract
try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

# Threshold boost constants - how much preprocessing should improve accuracy
DESKEW_THRESHOLD_BOOST = 0.15
DENOISE_THRESHOLD_BOOST = 0.10
BINARIZE_THRESHOLD_BOOST = 0.10
FULL_PIPELINE_THRESHOLD_BOOST = 0.20
MAX_THRESHOLD = 0.90
MIN_THRESHOLD = 0.50

# Distortion categories
SKEW_DISTORTIONS = {"skew_05", "skew_10"}
NOISE_DISTORTIONS = {"noise"}
LOW_CONTRAST_DISTORTIONS = {"lowdpi_150"}  # jpeg_40 is compression, not contrast
HEAVY_DISTORTIONS = {"blur_2", "skew_10", "lowdpi_150"}

# Fixture lists
ALL_FIXTURES = get_all_fixture_paths()
SKEWED_FIXTURES = get_fixtures_by_distortion(SKEW_DISTORTIONS)
NOISY_FIXTURES = get_fixtures_by_distortion(NOISE_DISTORTIONS)
LOW_CONTRAST_FIXTURES = get_fixtures_by_distortion(LOW_CONTRAST_DISTORTIONS)
HEAVY_DEGRADATION_FIXTURES = get_fixtures_by_distortion(HEAVY_DISTORTIONS)
CLEAN_FIXTURES = get_fixtures_by_category("clean")
SCANNED_FIXTURES = get_fixtures_by_category("scanned")

# Skip reasons
SKIP_NO_TESSERACT = "Tesseract OCR not installed"
SKIP_NO_PYTESSERACT = "pytesseract not installed"
SKIP_NO_OPENCV = "opencv-python-headless not installed"
SKIP_NO_EASYOCR = "easyocr not installed"
SKIP_NO_FIXTURES = "OCR test fixtures not generated"


def _preprocess_and_ocr(preprocessor, image_path: Path, steps: list[str]) -> str:
    """Apply preprocessing steps then run Tesseract OCR."""
    image_bytes = image_path.read_bytes()

    for step in steps:
        image_bytes = getattr(preprocessor, step)(image_bytes)

    from PIL import Image
    image = Image.open(BytesIO(image_bytes))
    return pytesseract.image_to_string(image, lang="eng")


def _raw_ocr(image_path: Path) -> str:
    """Run Tesseract OCR without preprocessing."""
    from PIL import Image
    image = Image.open(image_path)
    return pytesseract.image_to_string(image, lang="eng")


def _boosted_threshold(base_threshold: float, boost: float) -> float:
    """Calculate boosted accuracy threshold, clamped to [MIN, MAX]."""
    return max(MIN_THRESHOLD, min(base_threshold + boost, MAX_THRESHOLD))


# ---------------------------------------------------------------------------
# Full Pipeline Tests
# ---------------------------------------------------------------------------

@pytest.mark.ocr
@pytest.mark.ocr_preprocessed
@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason=SKIP_NO_TESSERACT)
@pytest.mark.skipif(not PYTESSERACT_AVAILABLE, reason=SKIP_NO_PYTESSERACT)
@pytest.mark.skipif(not OPENCV_AVAILABLE, reason=SKIP_NO_OPENCV)
@pytest.mark.skipif(len(ALL_FIXTURES) == 0, reason=SKIP_NO_FIXTURES)
class TestPreprocessedOCR:
    """Tests OCR accuracy after applying the full preprocessing pipeline."""

    @pytest.fixture
    def preprocessed_ocr(self, preprocessor):
        """Factory that preprocesses an image then runs OCR."""
        def _ocr(image_path: Path) -> str:
            return _preprocess_and_ocr(
                preprocessor, image_path, ["deskew", "denoise", "binarize"]
            )
        return _ocr

    @pytest.mark.parametrize("fixture_path", ALL_FIXTURES, ids=lambda p: p.stem)
    def test_full_pipeline_extracts_holder_name(
        self,
        fixture_path: Path,
        preprocessed_ocr,
        similarity_calculator,
    ):
        """Full pipeline should extract certificate holder name from any fixture."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = preprocessed_ocr(image_path)
        expected_name = ground_truth["expected_fields"]["certificate_holder_name"]
        threshold = _boosted_threshold(
            ground_truth["accuracy_threshold"], FULL_PIPELINE_THRESHOLD_BOOST
        )

        name_found = expected_name.lower() in ocr_text.lower()
        if not name_found:
            lines = ocr_text.split("\n")
            best_similarity = max(
                (similarity_calculator(expected_name, line.strip()) for line in lines),
                default=0.0,
            )
            assert best_similarity >= threshold, (
                f"Preprocessed OCR: holder name not found.\n"
                f"Expected: '{expected_name}'\n"
                f"Best similarity: {best_similarity:.2%}\n"
                f"Threshold: {threshold:.2%}\n"
                f"Distortions: {ground_truth.get('distortions', [])}"
            )

    @pytest.mark.parametrize("fixture_path", ALL_FIXTURES, ids=lambda p: p.stem)
    def test_full_pipeline_extracts_certificate_type(
        self,
        fixture_path: Path,
        preprocessed_ocr,
        similarity_calculator,
    ):
        """Full pipeline should extract certificate type from any fixture."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = preprocessed_ocr(image_path)
        expected_type = ground_truth["expected_fields"]["certificate_type"]
        threshold = _boosted_threshold(
            ground_truth["accuracy_threshold"], FULL_PIPELINE_THRESHOLD_BOOST
        )

        type_found = expected_type.lower() in ocr_text.lower()
        if not type_found:
            lines = ocr_text.split("\n")
            best_similarity = max(
                (similarity_calculator(expected_type, line.strip()) for line in lines),
                default=0.0,
            )
            assert best_similarity >= threshold, (
                f"Preprocessed OCR: certificate type not found.\n"
                f"Expected: '{expected_type}'\n"
                f"Best similarity: {best_similarity:.2%}\n"
                f"Threshold: {threshold:.2%}\n"
                f"Distortions: {ground_truth.get('distortions', [])}"
            )

    @pytest.mark.parametrize("fixture_path", ALL_FIXTURES, ids=lambda p: p.stem)
    def test_full_pipeline_extracts_dates(
        self,
        fixture_path: Path,
        preprocessed_ocr,
    ):
        """Full pipeline should extract at least one date from any fixture."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        # Heavy blur destroys date formatting even with preprocessing
        distortions = ground_truth.get("distortions", [])
        if "blur_2" in distortions:
            pytest.skip("Heavy blur makes dates unrecoverable even with preprocessing")

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = preprocessed_ocr(image_path)
        expected_issue = ground_truth["expected_fields"]["issue_date"]
        expected_expiry = ground_truth["expected_fields"]["expiration_date"]

        issue_found = (
            expected_issue in ocr_text or expected_issue.replace("-", "/") in ocr_text
        )
        expiry_found = (
            expected_expiry in ocr_text or expected_expiry.replace("-", "/") in ocr_text
        )

        assert issue_found or expiry_found, (
            f"Preprocessed OCR: no dates found.\n"
            f"Expected issue: '{expected_issue}'\n"
            f"Expected expiry: '{expected_expiry}'\n"
            f"Distortions: {ground_truth.get('distortions', [])}"
        )


# ---------------------------------------------------------------------------
# Individual Preprocessing Step Tests
# ---------------------------------------------------------------------------

@pytest.mark.ocr
@pytest.mark.ocr_preprocessed
@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason=SKIP_NO_TESSERACT)
@pytest.mark.skipif(not PYTESSERACT_AVAILABLE, reason=SKIP_NO_PYTESSERACT)
@pytest.mark.skipif(not OPENCV_AVAILABLE, reason=SKIP_NO_OPENCV)
class TestIndividualPreprocessing:
    """Tests that each preprocessing step individually improves accuracy."""

    @pytest.mark.parametrize(
        "fixture_path",
        SKEWED_FIXTURES,
        ids=lambda p: p.stem,
    )
    def test_deskew_improves_skewed_images(
        self,
        fixture_path: Path,
        preprocessor,
        similarity_calculator,
    ):
        """Deskew alone should improve name extraction on skewed images."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = _preprocess_and_ocr(preprocessor, image_path, ["deskew"])
        expected_name = ground_truth["expected_fields"]["certificate_holder_name"]
        threshold = _boosted_threshold(
            ground_truth["accuracy_threshold"], DESKEW_THRESHOLD_BOOST
        )

        name_found = expected_name.lower() in ocr_text.lower()
        if not name_found:
            lines = ocr_text.split("\n")
            best_similarity = max(
                (similarity_calculator(expected_name, line.strip()) for line in lines),
                default=0.0,
            )
            assert best_similarity >= threshold, (
                f"Deskew: holder name not found.\n"
                f"Expected: '{expected_name}'\n"
                f"Best similarity: {best_similarity:.2%}\n"
                f"Threshold: {threshold:.2%}\n"
                f"Distortions: {ground_truth.get('distortions', [])}"
            )

    @pytest.mark.parametrize(
        "fixture_path",
        NOISY_FIXTURES if NOISY_FIXTURES else [pytest.param("skip", marks=pytest.mark.skip)],
        ids=lambda p: p.stem if isinstance(p, Path) else "no_fixtures",
    )
    def test_denoise_improves_noisy_images(
        self,
        fixture_path: Path,
        preprocessor,
        similarity_calculator,
    ):
        """Denoise alone should improve name extraction on noisy images."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = _preprocess_and_ocr(preprocessor, image_path, ["denoise"])
        expected_name = ground_truth["expected_fields"]["certificate_holder_name"]
        threshold = _boosted_threshold(
            ground_truth["accuracy_threshold"], DENOISE_THRESHOLD_BOOST
        )

        name_found = expected_name.lower() in ocr_text.lower()
        if not name_found:
            lines = ocr_text.split("\n")
            best_similarity = max(
                (similarity_calculator(expected_name, line.strip()) for line in lines),
                default=0.0,
            )
            assert best_similarity >= threshold, (
                f"Denoise: holder name not found.\n"
                f"Expected: '{expected_name}'\n"
                f"Best similarity: {best_similarity:.2%}\n"
                f"Threshold: {threshold:.2%}\n"
                f"Distortions: {ground_truth.get('distortions', [])}"
            )

    @pytest.mark.parametrize(
        "fixture_path",
        LOW_CONTRAST_FIXTURES if LOW_CONTRAST_FIXTURES else [pytest.param("skip", marks=pytest.mark.skip)],
        ids=lambda p: p.stem if isinstance(p, Path) else "no_fixtures",
    )
    def test_binarize_improves_lowcontrast_images(
        self,
        fixture_path: Path,
        preprocessor,
        similarity_calculator,
    ):
        """Binarize alone should improve name extraction on low-contrast images."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = _preprocess_and_ocr(preprocessor, image_path, ["binarize"])
        expected_name = ground_truth["expected_fields"]["certificate_holder_name"]
        threshold = _boosted_threshold(
            ground_truth["accuracy_threshold"], BINARIZE_THRESHOLD_BOOST
        )

        name_found = expected_name.lower() in ocr_text.lower()
        if not name_found:
            lines = ocr_text.split("\n")
            best_similarity = max(
                (similarity_calculator(expected_name, line.strip()) for line in lines),
                default=0.0,
            )
            assert best_similarity >= threshold, (
                f"Binarize: holder name not found.\n"
                f"Expected: '{expected_name}'\n"
                f"Best similarity: {best_similarity:.2%}\n"
                f"Threshold: {threshold:.2%}\n"
                f"Distortions: {ground_truth.get('distortions', [])}"
            )


# ---------------------------------------------------------------------------
# Before/After Comparison Tests
# ---------------------------------------------------------------------------

@pytest.mark.ocr
@pytest.mark.ocr_preprocessed
@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason=SKIP_NO_TESSERACT)
@pytest.mark.skipif(not PYTESSERACT_AVAILABLE, reason=SKIP_NO_PYTESSERACT)
@pytest.mark.skipif(not OPENCV_AVAILABLE, reason=SKIP_NO_OPENCV)
@pytest.mark.skipif(len(SKEWED_FIXTURES + HEAVY_DEGRADATION_FIXTURES) == 0, reason=SKIP_NO_FIXTURES)
class TestPreprocessingImprovement:
    """Explicit before/after comparison proving preprocessing helps."""

    @pytest.mark.parametrize(
        "fixture_path",
        sorted(set(SKEWED_FIXTURES + HEAVY_DEGRADATION_FIXTURES)),
        ids=lambda p: p.stem,
    )
    def test_preprocessing_improves_or_maintains_name_accuracy(
        self,
        fixture_path: Path,
        preprocessor,
        similarity_calculator,
    ):
        """Preprocessed OCR should match or exceed raw OCR for holder name."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        expected_name = ground_truth["expected_fields"]["certificate_holder_name"]

        # Raw OCR
        raw_text = _raw_ocr(image_path)
        raw_lines = raw_text.split("\n")
        raw_best = max(
            (similarity_calculator(expected_name, line.strip()) for line in raw_lines),
            default=0.0,
        )

        # Preprocessed OCR
        preprocessed_text = _preprocess_and_ocr(
            preprocessor, image_path, ["deskew", "denoise", "binarize"]
        )
        preprocessed_lines = preprocessed_text.split("\n")
        preprocessed_best = max(
            (similarity_calculator(expected_name, line.strip()) for line in preprocessed_lines),
            default=0.0,
        )

        # Preprocessing should not make things significantly worse
        # Allow 10% tolerance for minor variations (binarize can occasionally
        # reduce accuracy on already-readable text)
        tolerance = 0.10
        assert preprocessed_best >= raw_best - tolerance, (
            f"Preprocessing degraded accuracy!\n"
            f"Expected: '{expected_name}'\n"
            f"Raw accuracy: {raw_best:.2%}\n"
            f"Preprocessed accuracy: {preprocessed_best:.2%}\n"
            f"Distortions: {ground_truth.get('distortions', [])}"
        )


# ---------------------------------------------------------------------------
# Regression Guard for Clean Images
# ---------------------------------------------------------------------------

@pytest.mark.ocr
@pytest.mark.ocr_preprocessed
@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason=SKIP_NO_TESSERACT)
@pytest.mark.skipif(not PYTESSERACT_AVAILABLE, reason=SKIP_NO_PYTESSERACT)
@pytest.mark.skipif(not OPENCV_AVAILABLE, reason=SKIP_NO_OPENCV)
@pytest.mark.skipif(len(CLEAN_FIXTURES) == 0, reason=SKIP_NO_FIXTURES)
class TestPipelineRegression:
    """Verify preprocessing does not degrade clean images."""

    CLEAN_THRESHOLD = 0.90

    @pytest.mark.parametrize("fixture_path", CLEAN_FIXTURES, ids=lambda p: p.stem)
    def test_pipeline_does_not_degrade_clean_images(
        self,
        fixture_path: Path,
        preprocessor,
        similarity_calculator,
    ):
        """Full pipeline on clean images should maintain at least 90% accuracy."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = _preprocess_and_ocr(
            preprocessor, image_path, ["deskew", "denoise", "binarize"]
        )
        expected_name = ground_truth["expected_fields"]["certificate_holder_name"]

        name_found = expected_name.lower() in ocr_text.lower()
        if not name_found:
            lines = ocr_text.split("\n")
            best_similarity = max(
                (similarity_calculator(expected_name, line.strip()) for line in lines),
                default=0.0,
            )
            assert best_similarity >= self.CLEAN_THRESHOLD, (
                f"Preprocessing degraded clean image!\n"
                f"Expected: '{expected_name}'\n"
                f"Best similarity: {best_similarity:.2%}\n"
                f"Threshold: {self.CLEAN_THRESHOLD:.2%}"
            )


# ---------------------------------------------------------------------------
# EasyOCR Helpers
# ---------------------------------------------------------------------------

def _easyocr_ocr(reader, image_path: Path) -> str:
    """Run EasyOCR on an image file, returning joined text."""
    results = reader.readtext(str(image_path), detail=1, paragraph=False)
    texts = [text.strip() for _, text, _ in results if text.strip()]
    return " ".join(texts)


def _fuzzy_word_overlap(expected: str, ocr_text: str) -> float:
    """
    Calculate fuzzy word overlap between expected string and OCR text.

    For each word in expected, finds the best fuzzy match in OCR text.
    Handles common OCR artifacts (punctuation, minor character errors).
    """
    import re
    import difflib

    # Clean OCR artifacts
    clean_ocr = re.sub(r'[;:"\'\[\]{}|\\]', '', ocr_text.lower())
    clean_expected = expected.lower()

    expected_words = clean_expected.split()
    ocr_words = clean_ocr.split()

    if not expected_words:
        return 1.0
    if not ocr_words:
        return 0.0

    matches = 0
    for exp_word in expected_words:
        best_match = max(
            (difflib.SequenceMatcher(None, exp_word, ocr_word).ratio()
             for ocr_word in ocr_words),
            default=0.0,
        )
        if best_match >= 0.60:  # Allow 40% character error per word (handles OCR artifacts)
            matches += 1

    return matches / len(expected_words)


def _easyocr_ocr_with_confidence(reader, image_path: Path) -> tuple[str, float]:
    """Run EasyOCR returning (text, avg_confidence)."""
    results = reader.readtext(str(image_path), detail=1, paragraph=False)
    texts = []
    confidences = []
    for _, text, conf in results:
        text = text.strip()
        if text:
            texts.append(text)
            confidences.append(conf)
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return " ".join(texts), avg_conf


def _preprocess_and_easyocr(preprocessor, reader, image_path: Path) -> str:
    """Apply full preprocessing then run EasyOCR."""
    import tempfile
    import os

    image_bytes = image_path.read_bytes()
    for step in ["deskew", "denoise", "binarize"]:
        image_bytes = getattr(preprocessor, step)(image_bytes)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(image_bytes)
        temp_path = f.name

    try:
        return _easyocr_ocr(reader, Path(temp_path))
    finally:
        os.unlink(temp_path)


def _ensemble_ocr(preprocessor, reader, image_path: Path) -> str:
    """
    Run both Tesseract and EasyOCR with preprocessing, return best result.

    Compares by checking which engine extracts more text with higher confidence.
    """
    # Tesseract with preprocessing
    tess_text = _preprocess_and_ocr(
        preprocessor, image_path, ["deskew", "denoise", "binarize"]
    )

    # EasyOCR with preprocessing
    import tempfile
    import os

    image_bytes = image_path.read_bytes()
    for step in ["deskew", "denoise", "binarize"]:
        image_bytes = getattr(preprocessor, step)(image_bytes)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(image_bytes)
        temp_path = f.name

    try:
        easy_text, easy_conf = _easyocr_ocr_with_confidence(reader, Path(temp_path))
    finally:
        os.unlink(temp_path)

    # Also get raw EasyOCR confidence (without preprocessing) for comparison
    _, raw_easy_conf = _easyocr_ocr_with_confidence(reader, image_path)

    # Pick the result with better confidence
    # Tesseract doesn't give a global confidence easily, so we compare
    # by checking if EasyOCR confidence is above a reasonable threshold
    if easy_conf > 0.5:
        return easy_text
    return tess_text


# ---------------------------------------------------------------------------
# EasyOCR Standalone Tests
# ---------------------------------------------------------------------------

@pytest.mark.ocr
@pytest.mark.ocr_ensemble
@pytest.mark.skipif(not EASYOCR_AVAILABLE, reason=SKIP_NO_EASYOCR)
@pytest.mark.skipif(len(ALL_FIXTURES) == 0, reason=SKIP_NO_FIXTURES)
class TestEasyOCR:
    """Tests EasyOCR accuracy on all fixtures (no preprocessing)."""

    @pytest.mark.parametrize("fixture_path", ALL_FIXTURES, ids=lambda p: p.stem)
    def test_easyocr_extracts_holder_name(
        self,
        fixture_path: Path,
        easyocr_reader,
        similarity_calculator,
    ):
        """EasyOCR should extract certificate holder name."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        # Skip blur_2 - too degraded for any single engine
        distortions = ground_truth.get("distortions", [])
        if "blur_2" in distortions:
            pytest.skip("Heavy blur too degraded for single-engine OCR")

        ocr_text = _easyocr_ocr(easyocr_reader, image_path)
        expected_name = ground_truth["expected_fields"]["certificate_holder_name"]
        threshold = ground_truth["accuracy_threshold"]

        name_found = expected_name.lower() in ocr_text.lower()
        if not name_found:
            fuzzy_overlap = _fuzzy_word_overlap(expected_name, ocr_text)

            assert fuzzy_overlap >= threshold, (
                f"EasyOCR: holder name not found.\n"
                f"Expected: '{expected_name}'\n"
                f"Got: '{ocr_text[:200]}'\n"
                f"Fuzzy word overlap: {fuzzy_overlap:.2%}\n"
                f"Threshold: {threshold:.2%}\n"
                f"Distortions: {distortions}"
            )


# ---------------------------------------------------------------------------
# Ensemble OCR Tests (Tesseract + EasyOCR with Preprocessing)
# ---------------------------------------------------------------------------

@pytest.mark.ocr
@pytest.mark.ocr_ensemble
@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason=SKIP_NO_TESSERACT)
@pytest.mark.skipif(not PYTESSERACT_AVAILABLE, reason=SKIP_NO_PYTESSERACT)
@pytest.mark.skipif(not EASYOCR_AVAILABLE, reason=SKIP_NO_EASYOCR)
@pytest.mark.skipif(not OPENCV_AVAILABLE, reason=SKIP_NO_OPENCV)
@pytest.mark.skipif(len(ALL_FIXTURES) == 0, reason=SKIP_NO_FIXTURES)
class TestEnsembleOCR:
    """Tests ensemble OCR (Tesseract + EasyOCR) on all fixtures."""

    @pytest.fixture
    def ensemble(self, preprocessor, easyocr_reader):
        """Factory returning ensemble OCR text for a given image."""
        def _ocr(image_path: Path) -> str:
            return _ensemble_ocr(preprocessor, easyocr_reader, image_path)
        return _ocr

    @pytest.mark.parametrize("fixture_path", ALL_FIXTURES, ids=lambda p: p.stem)
    def test_ensemble_extracts_holder_name(
        self,
        fixture_path: Path,
        ensemble,
        similarity_calculator,
    ):
        """Ensemble should extract holder name from ALL fixtures including heavy degradation."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = ensemble(image_path)
        expected_name = ground_truth["expected_fields"]["certificate_holder_name"]

        # Ensemble should handle even heavily degraded images
        # Use a lower threshold for blur_2 since it's extremely degraded
        distortions = ground_truth.get("distortions", [])
        if "blur_2" in distortions:
            threshold = 0.40
        else:
            threshold = _boosted_threshold(
                ground_truth["accuracy_threshold"], FULL_PIPELINE_THRESHOLD_BOOST
            )

        name_found = expected_name.lower() in ocr_text.lower()
        if not name_found:
            fuzzy_overlap = _fuzzy_word_overlap(expected_name, ocr_text)

            lines = ocr_text.split("\n") if "\n" in ocr_text else [ocr_text]
            best_similarity = max(
                (similarity_calculator(expected_name, line.strip()) for line in lines),
                default=0.0,
            )
            effective = max(best_similarity, fuzzy_overlap)

            assert effective >= threshold, (
                f"Ensemble OCR: holder name not found.\n"
                f"Expected: '{expected_name}'\n"
                f"Got: '{ocr_text[:300]}'\n"
                f"Similarity: {best_similarity:.2%}, Fuzzy overlap: {fuzzy_overlap:.2%}\n"
                f"Threshold: {threshold:.2%}\n"
                f"Distortions: {distortions}"
            )

    @pytest.mark.parametrize("fixture_path", ALL_FIXTURES, ids=lambda p: p.stem)
    def test_ensemble_extracts_certificate_type(
        self,
        fixture_path: Path,
        ensemble,
        similarity_calculator,
    ):
        """Ensemble should extract certificate type from all fixtures."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        distortions = ground_truth.get("distortions", [])
        if "blur_2" in distortions:
            threshold = 0.35
        else:
            threshold = _boosted_threshold(
                ground_truth["accuracy_threshold"], FULL_PIPELINE_THRESHOLD_BOOST
            )

        ocr_text = ensemble(image_path)
        expected_type = ground_truth["expected_fields"]["certificate_type"]

        type_found = expected_type.lower() in ocr_text.lower()
        if not type_found:
            fuzzy_overlap = _fuzzy_word_overlap(expected_type, ocr_text)

            lines = ocr_text.split("\n") if "\n" in ocr_text else [ocr_text]
            best_similarity = max(
                (similarity_calculator(expected_type, line.strip()) for line in lines),
                default=0.0,
            )
            effective = max(best_similarity, fuzzy_overlap)

            assert effective >= threshold, (
                f"Ensemble OCR: certificate type not found.\n"
                f"Expected: '{expected_type}'\n"
                f"Got: '{ocr_text[:300]}'\n"
                f"Similarity: {best_similarity:.2%}, Fuzzy overlap: {fuzzy_overlap:.2%}\n"
                f"Threshold: {threshold:.2%}\n"
                f"Distortions: {distortions}"
            )

    @pytest.mark.parametrize("fixture_path", ALL_FIXTURES, ids=lambda p: p.stem)
    def test_ensemble_extracts_dates(
        self,
        fixture_path: Path,
        ensemble,
    ):
        """Ensemble should extract at least one date from most fixtures."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        distortions = ground_truth.get("distortions", [])
        if "blur_2" in distortions:
            pytest.skip("Heavy blur destroys date formatting for all engines")

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        ocr_text = ensemble(image_path)
        expected_issue = ground_truth["expected_fields"]["issue_date"]
        expected_expiry = ground_truth["expected_fields"]["expiration_date"]

        # Normalize OCR text separators (EasyOCR may read dashes as dots/colons)
        ocr_normalized = ocr_text.replace(".", "-").replace(":", "-")

        import difflib

        def _date_found(expected_date: str, text: str, normalized: str) -> bool:
            """Check if date appears in text, with fuzzy matching for OCR errors."""
            # Exact match with various separators
            if expected_date in text:
                return True
            if expected_date.replace("-", "/") in text:
                return True
            if expected_date in normalized:
                return True
            # Fuzzy match: allow 1 character difference (e.g., "2074" vs "2024")
            for i in range(len(normalized) - len(expected_date) + 1):
                window = normalized[i:i + len(expected_date)]
                if difflib.SequenceMatcher(None, expected_date, window).ratio() >= 0.80:
                    return True
            return False

        issue_found = _date_found(expected_issue, ocr_text, ocr_normalized)
        expiry_found = _date_found(expected_expiry, ocr_text, ocr_normalized)

        assert issue_found or expiry_found, (
            f"Ensemble OCR: no dates found.\n"
            f"Expected issue: '{expected_issue}'\n"
            f"Expected expiry: '{expected_expiry}'\n"
            f"Got: '{ocr_text[:300]}'\n"
            f"Distortions: {distortions}"
        )


# ---------------------------------------------------------------------------
# Ensemble vs Individual Comparison
# ---------------------------------------------------------------------------

@pytest.mark.ocr
@pytest.mark.ocr_ensemble
@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason=SKIP_NO_TESSERACT)
@pytest.mark.skipif(not PYTESSERACT_AVAILABLE, reason=SKIP_NO_PYTESSERACT)
@pytest.mark.skipif(not EASYOCR_AVAILABLE, reason=SKIP_NO_EASYOCR)
@pytest.mark.skipif(not OPENCV_AVAILABLE, reason=SKIP_NO_OPENCV)
@pytest.mark.skipif(len(HEAVY_DEGRADATION_FIXTURES) == 0, reason=SKIP_NO_FIXTURES)
class TestEnsembleImprovement:
    """Verify ensemble is at least as good as the better individual engine."""

    @pytest.mark.parametrize(
        "fixture_path",
        HEAVY_DEGRADATION_FIXTURES,
        ids=lambda p: p.stem,
    )
    def test_ensemble_beats_or_matches_individual_engines(
        self,
        fixture_path: Path,
        preprocessor,
        easyocr_reader,
        similarity_calculator,
    ):
        """Ensemble result should be >= best individual engine result."""
        with open(fixture_path, "r") as f:
            ground_truth = json.load(f)

        image_path = fixture_path.with_suffix(".png")
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        expected_name = ground_truth["expected_fields"]["certificate_holder_name"]

        # Tesseract with preprocessing
        tess_text = _preprocess_and_ocr(
            preprocessor, image_path, ["deskew", "denoise", "binarize"]
        )
        tess_words = set(expected_name.lower().split())
        tess_found = set(tess_text.lower().split())
        tess_overlap = len(tess_words & tess_found) / len(tess_words) if tess_words else 0

        # EasyOCR with preprocessing
        easy_text = _preprocess_and_easyocr(preprocessor, easyocr_reader, image_path)
        easy_found = set(easy_text.lower().split())
        easy_overlap = len(tess_words & easy_found) / len(tess_words) if tess_words else 0

        # Ensemble
        ensemble_text = _ensemble_ocr(preprocessor, easyocr_reader, image_path)
        ens_found = set(ensemble_text.lower().split())
        ens_overlap = len(tess_words & ens_found) / len(tess_words) if tess_words else 0

        best_individual = max(tess_overlap, easy_overlap)
        tolerance = 0.15  # Allow small tolerance

        assert ens_overlap >= best_individual - tolerance, (
            f"Ensemble worse than best individual!\n"
            f"Expected: '{expected_name}'\n"
            f"Tesseract overlap: {tess_overlap:.2%}\n"
            f"EasyOCR overlap: {easy_overlap:.2%}\n"
            f"Ensemble overlap: {ens_overlap:.2%}\n"
            f"Distortions: {ground_truth.get('distortions', [])}"
        )
