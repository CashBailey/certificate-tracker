"""
Ensemble OCR engine that runs multiple OCR engines and picks the best result.

Runs both Tesseract and EasyOCR in parallel, compares confidence scores,
and returns the result from whichever engine performed better.
"""

from shared.models import PageImage, TextSpan


def avg_confidence(spans: list[TextSpan]) -> float:
    """Calculate average confidence across text spans."""
    if not spans:
        return 0.0
    return sum(s.confidence for s in spans) / len(spans)


class EnsembleOcrEngine:
    """OCR engine that combines Tesseract and EasyOCR results."""

    def __init__(self, tesseract_service, easyocr_service):
        """
        Initialize ensemble engine.

        Args:
            tesseract_service: TesseractOcrService instance
            easyocr_service: EasyOcrService instance
        """
        self.tesseract = tesseract_service
        self.easyocr = easyocr_service

    def ocr_region(
        self,
        page_image: PageImage,
        bbox_norm: tuple[float, float, float, float],
    ) -> list[TextSpan]:
        """
        Perform OCR on a region using both engines, return best result.

        Args:
            page_image: Page image to process
            bbox_norm: Normalized bounding box (x0, y0, x1, y1)

        Returns:
            TextSpan list from the engine with higher average confidence
        """
        tess_spans = self.tesseract.ocr_region(page_image, bbox_norm)
        easy_spans = self.easyocr.ocr_region(page_image, bbox_norm)

        tess_conf = avg_confidence(tess_spans)
        easy_conf = avg_confidence(easy_spans)

        return easy_spans if easy_conf > tess_conf else tess_spans
