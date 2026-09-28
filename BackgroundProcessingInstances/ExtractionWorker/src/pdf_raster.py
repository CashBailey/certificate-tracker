"""
PDF rasterization using pdf2image (poppler).

Renders PDF pages to images for OCR processing.
"""

from io import BytesIO
from typing import Optional

from shared.models import PageImage

from .pdf_text import MAX_PDF_PAGES

PDF_RENDER_TIMEOUT_SECONDS = 20
MAX_RENDER_DIMENSION_PX = 4096


class PopplerPdfRasterizer:
    """PDF rasterizer using pdf2image/poppler."""

    def __init__(self, default_dpi: int = 300):
        """
        Initialize rasterizer.

        Args:
            default_dpi: Default DPI for rendering (300 is good for OCR)
        """
        self.default_dpi = default_dpi

    def rasterize_pages(
        self,
        pdf_bytes: bytes,
        dpi: Optional[int] = None,
    ) -> list[PageImage]:
        """
        Rasterize all pages of a PDF to images.

        Args:
            pdf_bytes: PDF file bytes
            dpi: Resolution for rendering (defaults to self.default_dpi)

        Returns:
            List of PageImage objects
        """
        from pdf2image import convert_from_bytes

        render_dpi = dpi or self.default_dpi

        # Convert PDF to PIL Images
        pil_images = convert_from_bytes(
            pdf_bytes,
            dpi=render_dpi,
            fmt='PNG',
            first_page=1,
            last_page=MAX_PDF_PAGES,
            size=MAX_RENDER_DIMENSION_PX,
            timeout=PDF_RENDER_TIMEOUT_SECONDS,
            thread_count=1,
        )

        result: list[PageImage] = []

        for page_num, pil_image in enumerate(pil_images):
            # Convert PIL Image to bytes
            img_buffer = BytesIO()
            pil_image.save(img_buffer, format='PNG')
            img_bytes = img_buffer.getvalue()

            page_image = PageImage(
                page_num=page_num,
                image_bytes=img_bytes,
                width_px=pil_image.width,
                height_px=pil_image.height,
                dpi=render_dpi,
            )
            result.append(page_image)

        return result

    def rasterize_page(
        self,
        pdf_bytes: bytes,
        page_num: int,
        dpi: Optional[int] = None,
    ) -> Optional[PageImage]:
        """
        Rasterize a single page of a PDF.

        Args:
            pdf_bytes: PDF file bytes
            page_num: Page number (0-indexed)
            dpi: Resolution for rendering

        Returns:
            PageImage or None if page doesn't exist
        """
        from pdf2image import convert_from_bytes

        render_dpi = dpi or self.default_dpi

        # Convert specific page (pdf2image uses 1-indexed pages)
        pil_images = convert_from_bytes(
            pdf_bytes,
            dpi=render_dpi,
            fmt='PNG',
            first_page=page_num + 1,
            last_page=page_num + 1,
            size=MAX_RENDER_DIMENSION_PX,
            timeout=PDF_RENDER_TIMEOUT_SECONDS,
            thread_count=1,
        )

        if not pil_images:
            return None

        pil_image = pil_images[0]

        # Convert PIL Image to bytes
        img_buffer = BytesIO()
        pil_image.save(img_buffer, format='PNG')
        img_bytes = img_buffer.getvalue()

        return PageImage(
            page_num=page_num,
            image_bytes=img_bytes,
            width_px=pil_image.width,
            height_px=pil_image.height,
            dpi=render_dpi,
        )
