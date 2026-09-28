"""
OCR service using Tesseract.

Provides OCR functionality for scanned document regions.
"""

import json
import math
import re
from io import BytesIO

import pytesseract
from PIL import Image

from shared.models import PageImage, TextSpan

MAX_OCR_TASK_BYTES = 30 * 1024 * 1024
MAX_OCR_IMAGE_BYTES = 20 * 1024 * 1024
MAX_OCR_PIXELS = 40_000_000
MAX_OCR_DIMENSION = 8192
MAX_OCR_SPANS = 5_000
MAX_OCR_TEXT_CHARS = 100_000
TESSERACT_TIMEOUT_SECONDS = 60


class TesseractOcrService:
    """OCR service using Tesseract."""

    def __init__(
        self,
        lang: str = "eng",
        config: str = "",
    ):
        """
        Initialize OCR service.

        Args:
            lang: Tesseract language(s) to use (e.g., "eng", "eng+spa")
            config: Additional Tesseract config options
        """
        self.lang = lang
        self.config = config

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
        # Load image
        pil_image = Image.open(BytesIO(page_image.image_bytes))
        if pil_image.size != (page_image.width_px, page_image.height_px):
            raise ValueError("Declared OCR image dimensions do not match payload")
        if pil_image.width * pil_image.height > MAX_OCR_PIXELS:
            raise ValueError("OCR image exceeds pixel limit")
        pil_image.load()

        # Convert bbox_norm to pixel coordinates
        x0, y0, x1, y1 = bbox_norm
        px_x0 = int(x0 * page_image.width_px)
        px_y0 = int(y0 * page_image.height_px)
        px_x1 = int(x1 * page_image.width_px)
        px_y1 = int(y1 * page_image.height_px)

        # Crop image to region
        cropped = pil_image.crop((px_x0, px_y0, px_x1, px_y1))

        # Run Tesseract with TSVA output for per-word bbox + confidence
        tsv_data = pytesseract.image_to_data(
            cropped,
            lang=self.lang,
            config=self.config,
            output_type=pytesseract.Output.DICT,
            timeout=TESSERACT_TIMEOUT_SECONDS,
        )

        # Parse results and convert to TextSpans
        text_spans: list[TextSpan] = []
        n_boxes = len(tsv_data['text'])

        crop_width = px_x1 - px_x0
        crop_height = px_y1 - px_y0
        total_text_chars = 0

        for i in range(n_boxes):
            text = tsv_data['text'][i].strip()
            conf = tsv_data['conf'][i]

            # Skip empty text or low confidence
            if not text or conf < 0:
                continue
            total_text_chars += len(text)
            if (
                len(text_spans) >= MAX_OCR_SPANS
                or total_text_chars > MAX_OCR_TEXT_CHARS
            ):
                break

            # Get bounding box in cropped image coordinates
            box_x = tsv_data['left'][i]
            box_y = tsv_data['top'][i]
            box_w = tsv_data['width'][i]
            box_h = tsv_data['height'][i]

            # Convert to full page normalized coordinates
            if crop_width > 0 and crop_height > 0:
                # Position within crop
                rel_x0 = box_x / crop_width
                rel_y0 = box_y / crop_height
                rel_x1 = (box_x + box_w) / crop_width
                rel_y1 = (box_y + box_h) / crop_height

                # Convert to full page coordinates
                page_x0 = x0 + rel_x0 * (x1 - x0)
                page_y0 = y0 + rel_y0 * (y1 - y0)
                page_x1 = x0 + rel_x1 * (x1 - x0)
                page_y1 = y0 + rel_y1 * (y1 - y0)
            else:
                page_x0, page_y0, page_x1, page_y1 = x0, y0, x1, y1

            text_span = TextSpan(
                text=text,
                bbox_norm=(page_x0, page_y0, page_x1, page_y1),
                confidence=conf / 100.0,  # Tesseract returns 0-100
            )
            text_spans.append(text_span)

        return text_spans


def serialize_ocr_request(
    request_id: str,
    page_image: PageImage,
    bbox_norm: tuple[float, float, float, float],
) -> bytes:
    """
    Serialize OCR request for Redis queue.

    Args:
        request_id: Unique request identifier
        page_image: Page image
        bbox_norm: Region bounding box

    Returns:
        JSON bytes
    """
    import base64

    data = {
        "request_id": request_id,
        "page_num": page_image.page_num,
        "image_b64": base64.b64encode(page_image.image_bytes).decode('ascii'),
        "width_px": page_image.width_px,
        "height_px": page_image.height_px,
        "dpi": page_image.dpi,
        "bbox_norm": list(bbox_norm),
    }
    return json.dumps(data).encode('utf-8')


def deserialize_ocr_request(data: bytes) -> tuple[str, PageImage, tuple[float, float, float, float]]:
    """
    Deserialize OCR request from Redis queue.

    Args:
        data: JSON bytes

    Returns:
        Tuple of (request_id, page_image, bbox_norm)
    """
    import base64

    if len(data) > MAX_OCR_TASK_BYTES:
        raise ValueError("OCR task exceeds serialized size limit")
    parsed = json.loads(data.decode('utf-8'))

    request_id = parsed["request_id"]
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", request_id):
        raise ValueError("Invalid OCR request ID")

    page_num = parsed["page_num"]
    if not isinstance(page_num, int) or not 0 <= page_num < 20:
        raise ValueError("Invalid OCR page number")

    width_px = parsed["width_px"]
    height_px = parsed["height_px"]
    dpi = parsed["dpi"]
    if not isinstance(width_px, int) or not isinstance(height_px, int):
        raise ValueError("OCR dimensions must be integers")
    if (
        width_px <= 0
        or height_px <= 0
        or width_px > MAX_OCR_DIMENSION
        or height_px > MAX_OCR_DIMENSION
        or width_px * height_px > MAX_OCR_PIXELS
    ):
        raise ValueError("OCR image dimensions exceed limit")
    if not isinstance(dpi, int) or not 50 <= dpi <= 600:
        raise ValueError("OCR DPI is outside the supported range")

    image_b64 = parsed["image_b64"]
    if not isinstance(image_b64, str):
        raise ValueError("OCR image payload must be base64 text")
    image_bytes = base64.b64decode(image_b64, validate=True)
    if not image_bytes or len(image_bytes) > MAX_OCR_IMAGE_BYTES:
        raise ValueError("OCR image payload exceeds limit")

    bbox_values = parsed["bbox_norm"]
    if not isinstance(bbox_values, list) or len(bbox_values) != 4:
        raise ValueError("OCR bounding box must contain four values")
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in bbox_values):
        raise ValueError("OCR bounding box values must be finite numbers")
    x0, y0, x1, y1 = (float(value) for value in bbox_values)
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("OCR bounding box is outside the image")

    page_image = PageImage(
        page_num=page_num,
        image_bytes=image_bytes,
        width_px=width_px,
        height_px=height_px,
        dpi=dpi,
    )

    bbox_norm = (x0, y0, x1, y1)

    return request_id, page_image, bbox_norm


def serialize_ocr_result(request_id: str, text_spans: list[TextSpan]) -> bytes:
    """
    Serialize OCR result for Redis.

    Args:
        request_id: Original request ID
        text_spans: OCR results

    Returns:
        JSON bytes
    """
    bounded_spans: list[TextSpan] = []
    total_chars = 0
    for span in text_spans[:MAX_OCR_SPANS]:
        total_chars += len(span.text)
        if total_chars > MAX_OCR_TEXT_CHARS:
            break
        bounded_spans.append(span)

    data = {
        "request_id": request_id,
        "spans": [
            {
                "text": span.text,
                "bbox_norm": list(span.bbox_norm),
                "confidence": span.confidence,
            }
            for span in bounded_spans
        ],
    }
    return json.dumps(data).encode('utf-8')


def deserialize_ocr_result(data: bytes) -> tuple[str, list[TextSpan]]:
    """
    Deserialize OCR result from Redis.

    Args:
        data: JSON bytes

    Returns:
        Tuple of (request_id, text_spans)
    """
    parsed = json.loads(data.decode('utf-8'))

    text_spans = [
        TextSpan(
            text=s["text"],
            bbox_norm=tuple(s["bbox_norm"]),
            confidence=s["confidence"],
        )
        for s in parsed["spans"]
    ]

    return parsed["request_id"], text_spans
