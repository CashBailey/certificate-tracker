"""
OCR service using EasyOCR (deep learning-based).

Provides GPU-accelerated OCR as an alternative to Tesseract,
particularly effective on skewed and degraded images.
"""

import numpy as np
from io import BytesIO

from PIL import Image

from shared.models import PageImage, TextSpan


class EasyOcrService:
    """OCR service using EasyOCR with GPU support."""

    def __init__(
        self,
        lang: str = "en",
        gpu: bool = True,
    ):
        """
        Initialize EasyOCR service.

        Args:
            lang: EasyOCR language code (e.g., "en", "es")
            gpu: Whether to use GPU acceleration
        """
        import easyocr

        self.reader = easyocr.Reader([lang], gpu=gpu)
        self.last_confidence: float = 0.0

    def ocr_region(
        self,
        page_image: PageImage,
        bbox_norm: tuple[float, float, float, float],
    ) -> list[TextSpan]:
        """
        Perform OCR on a specific region of a page image.

        Args:
            page_image: Page image to process
            bbox_norm: Normalized bounding box (x0, y0, x1, y1) in 0-1 range

        Returns:
            List of TextSpan objects with positions relative to full page
        """
        pil_image = Image.open(BytesIO(page_image.image_bytes))
        img_array = np.array(pil_image)

        # Convert bbox_norm to pixel coordinates
        x0, y0, x1, y1 = bbox_norm
        px_x0 = int(x0 * page_image.width_px)
        px_y0 = int(y0 * page_image.height_px)
        px_x1 = int(x1 * page_image.width_px)
        px_y1 = int(y1 * page_image.height_px)

        # Crop to region
        cropped = img_array[px_y0:px_y1, px_x0:px_x1]

        crop_height, crop_width = cropped.shape[:2]
        if crop_width == 0 or crop_height == 0:
            self.last_confidence = 0.0
            return []

        # Run EasyOCR - returns [(bbox, text, confidence), ...]
        results = self.reader.readtext(cropped, detail=1, paragraph=False)

        text_spans: list[TextSpan] = []
        confidences: list[float] = []

        for bbox, text, confidence in results:
            text = text.strip()
            if not text:
                continue

            confidences.append(confidence)

            # bbox is [[x0,y0],[x1,y1],[x2,y2],[x3,y3]] - get bounding rect
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            box_x0, box_x1 = min(xs), max(xs)
            box_y0, box_y1 = min(ys), max(ys)

            # Convert to full page normalized coordinates
            rel_x0 = box_x0 / crop_width
            rel_y0 = box_y0 / crop_height
            rel_x1 = box_x1 / crop_width
            rel_y1 = box_y1 / crop_height

            page_x0 = x0 + rel_x0 * (x1 - x0)
            page_y0 = y0 + rel_y0 * (y1 - y0)
            page_x1 = x0 + rel_x1 * (x1 - x0)
            page_y1 = y0 + rel_y1 * (y1 - y0)

            text_spans.append(TextSpan(
                text=text,
                bbox_norm=(page_x0, page_y0, page_x1, page_y1),
                confidence=confidence,
            ))

        self.last_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )
        return text_spans
