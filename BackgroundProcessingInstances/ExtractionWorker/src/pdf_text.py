"""
PDF text extraction using pypdf.

Extracts text with bounding box positions from digital PDFs.
"""

from pypdf import PdfReader

from shared.models import DocumentToken
from shared.utils import pdf_bbox_to_norm_top_left

MAX_PDF_PAGES = 20
MAX_PDF_PAGE_TEXT_CHARS = 500_000
MAX_PDF_TOTAL_TOKENS = 200_000
MAX_PDF_PAGE_TOKENS = 25_000


class DocumentLimitError(ValueError):
    """Raised when untrusted document complexity exceeds worker budgets."""


class PyPdfTextExtractor:
    """PDF text extractor using pypdf library."""

    def extract_text_with_positions(
        self,
        pdf_bytes: bytes,
    ) -> list[tuple[int, list[DocumentToken]]]:
        """
        Extract text with positions from all pages of a PDF.

        Args:
            pdf_bytes: PDF file bytes

        Returns:
            List of (page_num, tokens) tuples
        """
        from io import BytesIO

        reader = PdfReader(BytesIO(pdf_bytes))
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentLimitError(
                f"PDF has more than {MAX_PDF_PAGES} pages",
            )
        result: list[tuple[int, list[DocumentToken]]] = []
        token_counter = 0

        for page_num, page in enumerate(reader.pages):
            tokens = self._extract_page_tokens(page, page_num, token_counter)
            token_counter += len(tokens)
            if token_counter > MAX_PDF_TOTAL_TOKENS:
                raise DocumentLimitError(
                    f"PDF has more than {MAX_PDF_TOTAL_TOKENS} text tokens",
                )
            result.append((page_num, tokens))

        return result

    def _extract_page_tokens(
        self,
        page,
        page_num: int,
        token_id_start: int,
    ) -> list[DocumentToken]:
        """
        Extract tokens from a single page.

        Uses pypdf's visitor pattern to extract text with positions.
        """
        tokens: list[DocumentToken] = []
        token_counter = token_id_start
        page_text_chars = 0

        # Get page dimensions
        mediabox = page.mediabox
        page_width = float(mediabox.width)
        page_height = float(mediabox.height)

        if page_width == 0 or page_height == 0:
            return tokens

        def visitor_text(text: str, cm, tm, font_dict, font_size):
            """Visitor function called for each text element."""
            nonlocal token_counter
            nonlocal page_text_chars

            if not text or not text.strip():
                return

            # tm is the text matrix [a, b, c, d, e, f]
            # e, f are the x, y translation
            if tm is None:
                return

            page_text_chars += len(text)
            if page_text_chars > MAX_PDF_PAGE_TEXT_CHARS:
                raise DocumentLimitError("PDF page text exceeds extraction limit")

            x = tm[4]
            y = tm[5]

            # Estimate text width based on font size and character count
            # This is approximate - real width depends on font metrics
            estimated_width = len(text) * font_size * 0.5 if font_size else len(text) * 5
            estimated_height = font_size if font_size else 12

            # Create bounding box in PDF coordinates
            pdf_bbox = (
                x,
                y,
                x + estimated_width,
                y + estimated_height,
            )

            # Convert to normalized top-left coordinates
            norm_bbox = pdf_bbox_to_norm_top_left(
                pdf_bbox,
                page_width,
                page_height,
            )

            # Split text into words/tokens
            words = text.split()
            if len(tokens) + len(words) > MAX_PDF_PAGE_TOKENS:
                raise DocumentLimitError("PDF page token count exceeds extraction limit")
            for word in words:
                if word.strip():
                    token = DocumentToken(
                        token_id=f"t_{token_counter}",
                        text=word.strip(),
                        bbox_norm=norm_bbox,
                        page_num=page_num,
                        confidence=1.0,  # Digital text has high confidence
                    )
                    tokens.append(token)
                    token_counter += 1

        try:
            page.extract_text(visitor_text=visitor_text)
        except DocumentLimitError:
            raise
        except Exception:
            # Fall back to simple text extraction without positions
            text = page.extract_text() or ""
            if len(text) > MAX_PDF_PAGE_TEXT_CHARS:
                raise DocumentLimitError("PDF page text exceeds extraction limit")
            words = text.split()
            if len(words) > MAX_PDF_PAGE_TOKENS:
                raise DocumentLimitError("PDF page token count exceeds extraction limit")
            for word in words:
                if word.strip():
                    token = DocumentToken(
                        token_id=f"t_{token_counter}",
                        text=word.strip(),
                        bbox_norm=(0.0, 0.0, 1.0, 1.0),  # Unknown position
                        page_num=page_num,
                        confidence=0.5,  # Lower confidence without position
                    )
                    tokens.append(token)
                    token_counter += 1

        return tokens

    def extract_raw_text(self, pdf_bytes: bytes) -> str:
        """
        Extract plain text from PDF without positions.

        Args:
            pdf_bytes: PDF file bytes

        Returns:
            Concatenated text from all pages
        """
        from io import BytesIO

        reader = PdfReader(BytesIO(pdf_bytes))
        text_parts = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        return "\n\n".join(text_parts)

    def get_page_count(self, pdf_bytes: bytes) -> int:
        """Get the number of pages in a PDF."""
        from io import BytesIO
        reader = PdfReader(BytesIO(pdf_bytes))
        return len(reader.pages)
