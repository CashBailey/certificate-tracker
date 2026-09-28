"""Tests for bounded, non-destructive image preview generation."""

import io

import pytest
from PIL import Image

from src.routes import documents


def _image_bytes(format_name: str = "PNG", *, size: tuple[int, int] = (20, 10)) -> bytes:
    output = io.BytesIO()
    with Image.new("RGBA", size, (255, 0, 0, 128)) as image:
        image.save(output, format_name)
    return output.getvalue()


def test_image_preview_is_pdf_without_mutating_source_bytes():
    source = _image_bytes()

    preview = documents._convert_image_to_pdf_preview(source)

    assert preview.startswith(b"%PDF")
    assert source.startswith(b"\x89PNG\r\n\x1a\n")


def test_multi_page_tiff_preview_preserves_all_pages():
    output = io.BytesIO()
    with Image.new("RGB", (20, 10), "white") as first:
        with Image.new("RGB", (20, 10), "black") as second:
            first.save(output, "TIFF", save_all=True, append_images=[second])

    preview = documents._convert_image_to_pdf_preview(output.getvalue())

    assert preview.startswith(b"%PDF")
    assert preview.count(b"/Type /Page") >= 2


def test_corrupt_image_is_rejected():
    with pytest.raises(ValueError, match="cannot be previewed"):
        documents._convert_image_to_pdf_preview(b"not an image")


def test_total_pixel_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(documents, "_MAX_PREVIEW_PIXELS", 10)

    with pytest.raises(ValueError, match="too large"):
        documents._convert_image_to_pdf_preview(_image_bytes())
