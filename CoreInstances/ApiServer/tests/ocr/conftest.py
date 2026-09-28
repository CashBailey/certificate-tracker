"""
Pytest configuration and fixtures for OCR accuracy tests.
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Generator

import pytest


# Check if Tesseract is available
TESSERACT_AVAILABLE = shutil.which("tesseract") is not None

# Check if OpenCV is available (needed for preprocessing tests)
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

# Check if EasyOCR is available (needed for ensemble tests)
try:
    import easyocr as _easyocr_check
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

# Path to OCR fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "ocr_fixtures"

# Path to ExtractionWorker preprocessor. Only resolvable in the host project
# layout (parents[4]); inside the api container parents[4] is IndexError and
# ExtractionWorker is not mounted. Set to None and let downstream tests skip.
try:
    _EXTRACTION_WORKER_SRC = (
        Path(__file__).resolve().parents[4]
        / "BackgroundProcessingInstances"
        / "ExtractionWorker"
        / "src"
    )
except IndexError:
    _EXTRACTION_WORKER_SRC = None


def pytest_configure(config):
    """Register custom markers for OCR tests."""
    config.addinivalue_line(
        "markers",
        "ocr: marks tests as OCR accuracy tests (require Tesseract)",
    )
    config.addinivalue_line(
        "markers",
        "ocr_preprocessed: marks tests as OCR tests with preprocessing (require OpenCV)",
    )
    config.addinivalue_line(
        "markers",
        "ocr_ensemble: marks tests as ensemble OCR tests (require EasyOCR + Tesseract)",
    )


def get_all_fixture_paths() -> list[Path]:
    """
    Get all ground truth JSON files from the fixtures directory.

    Returns:
        List of paths to JSON ground truth files
    """
    if not FIXTURES_DIR.exists():
        return []

    # Find all JSON files (excluding generator directory)
    json_files = []
    for subdir in ["clean", "skewed", "degraded", "scanned"]:
        subdir_path = FIXTURES_DIR / subdir
        if subdir_path.exists():
            json_files.extend(subdir_path.glob("*.json"))

    return sorted(json_files)


@pytest.fixture(scope="session")
def fixtures_available() -> bool:
    """Check if OCR fixtures have been generated."""
    return len(get_all_fixture_paths()) > 0


@pytest.fixture
def ocr_fixture_paths() -> list[Path]:
    """Get list of all fixture paths for parametrization."""
    return get_all_fixture_paths()


@pytest.fixture
def load_fixture():
    """
    Factory fixture to load a specific OCR test fixture.

    Returns:
        Function that loads (image_path, ground_truth) for a given JSON path
    """

    def _load(json_path: Path) -> tuple[Path, dict]:
        """Load image path and ground truth from JSON file."""
        with open(json_path, "r", encoding="utf-8") as f:
            ground_truth = json.load(f)

        image_path = json_path.with_suffix(".png")
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        return image_path, ground_truth

    return _load


def calculate_similarity(expected: str, actual: str) -> float:
    """
    Calculate string similarity ratio between expected and actual values.

    Uses difflib SequenceMatcher for fuzzy matching.

    Args:
        expected: Expected string value
        actual: Actual extracted string value

    Returns:
        Similarity ratio between 0.0 and 1.0
    """
    import difflib

    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0

    # Normalize strings for comparison
    expected_norm = expected.lower().strip()
    actual_norm = actual.lower().strip()

    return difflib.SequenceMatcher(None, expected_norm, actual_norm).ratio()


@pytest.fixture
def similarity_calculator():
    """Fixture providing string similarity calculation."""
    return calculate_similarity


@pytest.fixture(scope="session")
def preprocessor():
    """
    Provide the PillowImagePreprocessor from ExtractionWorker.

    Imports the preprocessor class using sys.path manipulation to avoid
    permanent import pollution. Skips if OpenCV is not available.
    """
    if not OPENCV_AVAILABLE:
        pytest.skip("opencv-python-headless not installed")
    if _EXTRACTION_WORKER_SRC is None:
        pytest.skip("ExtractionWorker not on host project layout")

    sys.path.insert(0, str(_EXTRACTION_WORKER_SRC))
    try:
        from preprocess import PillowImagePreprocessor
        return PillowImagePreprocessor()
    except ImportError:
        pytest.skip("PillowImagePreprocessor not found in ExtractionWorker")
    finally:
        if str(_EXTRACTION_WORKER_SRC) in sys.path:
            sys.path.remove(str(_EXTRACTION_WORKER_SRC))


@pytest.fixture(scope="session")
def easyocr_reader():
    """
    Provide an EasyOCR Reader instance.

    Session-scoped because model loading is expensive (~2-3 seconds).
    Skips if EasyOCR is not installed.
    """
    if not EASYOCR_AVAILABLE:
        pytest.skip("easyocr not installed")

    import easyocr
    return easyocr.Reader(["en"], gpu=True)


def get_fixtures_by_distortion(distortion_types: set[str]) -> list[Path]:
    """Get fixture paths that have any of the specified distortions."""
    results = []
    for path in get_all_fixture_paths():
        with open(path, "r") as f:
            data = json.load(f)
        if any(d in distortion_types for d in data.get("distortions", [])):
            results.append(path)
    return sorted(results)


def get_fixtures_by_category(category: str) -> list[Path]:
    """Get fixture paths from a specific category directory."""
    subdir = FIXTURES_DIR / category
    if not subdir.exists():
        return []
    return sorted(subdir.glob("*.json"))
