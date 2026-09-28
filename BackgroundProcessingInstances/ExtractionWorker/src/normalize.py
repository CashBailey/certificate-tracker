"""
Document normalization for extraction pipeline.

Handles hybrid page classification (digital/scanned), token ID assignment,
and SearchableText building.
"""

from typing import Optional

from shared.models import (
    DocumentToken,
    NormalizationConfig,
    NormalizedDocument,
    NormalizedPage,
    PageImage,
    SearchableText,
)
from shared.utils import build_searchable_text

from .pdf_text import DocumentLimitError, PyPdfTextExtractor
from .pdf_raster import PopplerPdfRasterizer
from .preprocess import PillowImagePreprocessor

MAX_SCANNED_PAGES = 10
MAX_RASTER_BYTES = 100 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000


class DocumentNormalizer:
    """Normalizes documents for extraction processing."""

    def __init__(
        self,
        config: Optional[NormalizationConfig] = None,
        text_extractor: Optional[PyPdfTextExtractor] = None,
        rasterizer: Optional[PopplerPdfRasterizer] = None,
        preprocessor: Optional[PillowImagePreprocessor] = None,
    ):
        """
        Initialize normalizer.

        Args:
            config: Normalization configuration
            text_extractor: PDF text extractor
            rasterizer: PDF rasterizer
            preprocessor: Image preprocessor
        """
        self.config = config or NormalizationConfig()
        self.text_extractor = text_extractor or PyPdfTextExtractor()
        self.rasterizer = rasterizer or PopplerPdfRasterizer(default_dpi=self.config.raster_dpi)
        self.preprocessor = preprocessor or PillowImagePreprocessor()

    def normalize_pdf(self, pdf_bytes: bytes) -> NormalizedDocument:
        """
        Normalize a PDF document.

        1. Extract digital text with positions
        2. Classify pages as digital or scanned
        3. Rasterize pages that need OCR
        4. Build searchable text

        Args:
            pdf_bytes: PDF file bytes

        Returns:
            NormalizedDocument with all pages processed
        """
        # Extract text from all pages
        pages_with_tokens = self.text_extractor.extract_text_with_positions(pdf_bytes)

        # Process each page
        normalized_pages: list[NormalizedPage] = []
        all_tokens: list[DocumentToken] = []
        scanned_page_count = 0
        raster_bytes = 0

        for page_num, tokens in pages_with_tokens:
            # Classify page based on token density
            is_digital = self._classify_page(tokens)

            # If scanned (low text), rasterize for OCR
            raster: Optional[PageImage] = None
            if not is_digital:
                scanned_page_count += 1
                if scanned_page_count > MAX_SCANNED_PAGES:
                    raise DocumentLimitError(
                        f"PDF has more than {MAX_SCANNED_PAGES} scanned pages",
                    )
                raster = self.rasterizer.rasterize_page(
                    pdf_bytes,
                    page_num,
                    dpi=self.config.raster_dpi,
                )
                # Optionally preprocess for better OCR
                if raster and self.config.enable_deskew:
                    preprocessed_bytes = self.preprocessor.deskew(raster.image_bytes)
                    raster = PageImage(
                        page_num=raster.page_num,
                        image_bytes=preprocessed_bytes,
                        width_px=raster.width_px,
                        height_px=raster.height_px,
                        dpi=raster.dpi,
                    )
                if raster:
                    raster_bytes += len(raster.image_bytes)
                    if raster_bytes > MAX_RASTER_BYTES:
                        raise DocumentLimitError("PDF raster data exceeds extraction limit")

            # Build page text
            page_text = " ".join(t.text for t in tokens)

            # Collect all tokens
            all_tokens.extend(tokens)

            normalized_page = NormalizedPage(
                page_num=page_num,
                tokens=tokens,
                page_text=page_text,
                is_digital=is_digital,
                raster=raster,
            )
            normalized_pages.append(normalized_page)

        # Build searchable text from all tokens
        searchable_text = build_searchable_text(all_tokens)

        return NormalizedDocument(
            pages=normalized_pages,
            searchable_text=searchable_text,
            total_pages=len(normalized_pages),
        )

    def normalize_image(self, image_bytes: bytes) -> NormalizedDocument:
        """
        Normalize an image document (single page).

        Images are always considered scanned and need OCR.

        Args:
            image_bytes: Image file bytes (PNG/JPEG/TIFF)

        Returns:
            NormalizedDocument with single page
        """
        from PIL import Image
        from io import BytesIO

        # Get image dimensions
        pil_image = Image.open(BytesIO(image_bytes))
        width, height = pil_image.size
        if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
            raise DocumentLimitError(
                f"Image dimensions exceed {MAX_IMAGE_PIXELS} pixels",
            )

        # Preprocess if enabled
        if self.config.enable_deskew:
            image_bytes = self.preprocessor.deskew(image_bytes)

        # Create page image
        raster = PageImage(
            page_num=0,
            image_bytes=image_bytes,
            width_px=width,
            height_px=height,
            dpi=self.config.raster_dpi,  # Assumed DPI
        )

        # No digital text for images
        normalized_page = NormalizedPage(
            page_num=0,
            tokens=[],
            page_text="",
            is_digital=False,
            raster=raster,
        )

        # Empty searchable text (will be populated after OCR)
        searchable_text = SearchableText(full_text="", token_map={})

        return NormalizedDocument(
            pages=[normalized_page],
            searchable_text=searchable_text,
            total_pages=1,
        )

    def _classify_page(self, tokens: list[DocumentToken]) -> bool:
        """
        Classify a page as digital or scanned based on token characteristics.

        Digital pages typically have:
        - Higher token count
        - Tokens with good confidence
        - Tokens with reasonable positions

        Args:
            tokens: Tokens extracted from the page

        Returns:
            True if page appears to be digital, False if likely scanned
        """
        if not tokens:
            return False

        # Check token count threshold
        min_tokens_for_digital = 10
        if len(tokens) < min_tokens_for_digital:
            return False

        # Check average confidence
        avg_confidence = sum(t.confidence for t in tokens) / len(tokens)
        if avg_confidence < self.config.digital_text_confidence * 0.8:
            return False

        # Check if tokens have reasonable positions (not all at 0,0)
        positioned_tokens = sum(
            1 for t in tokens
            if t.bbox_norm != (0.0, 0.0, 1.0, 1.0)
        )
        if positioned_tokens < len(tokens) * 0.5:
            return False

        return True

    def update_with_ocr_tokens(
        self,
        document: NormalizedDocument,
        page_num: int,
        ocr_tokens: list[DocumentToken],
    ) -> NormalizedDocument:
        """
        Update a normalized document with OCR results for a page.

        Args:
            document: Original normalized document
            page_num: Page number to update
            ocr_tokens: Tokens from OCR

        Returns:
            Updated NormalizedDocument
        """
        # Update the specific page
        new_pages = []
        all_tokens: list[DocumentToken] = []

        for page in document.pages:
            if page.page_num == page_num:
                # Merge digital tokens with OCR tokens
                merged_tokens = page.tokens + ocr_tokens
                page_text = " ".join(t.text for t in merged_tokens)

                new_page = NormalizedPage(
                    page_num=page.page_num,
                    tokens=merged_tokens,
                    page_text=page_text,
                    is_digital=page.is_digital,
                    raster=page.raster,
                )
                new_pages.append(new_page)
                all_tokens.extend(merged_tokens)
            else:
                new_pages.append(page)
                all_tokens.extend(page.tokens)

        # Rebuild searchable text
        searchable_text = build_searchable_text(all_tokens)

        return NormalizedDocument(
            pages=new_pages,
            searchable_text=searchable_text,
            total_pages=document.total_pages,
        )
