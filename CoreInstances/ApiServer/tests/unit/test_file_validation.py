"""
Unit tests for file validation utilities.

Tests the pure functions in src/shared/utils.py related to file handling.
"""

import pytest
from src.shared.utils import (
    build_content_disposition,
    sanitize_filename,
    detect_mime_from_bytes,
    validate_upload_bytes_and_type,
)


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_normal_filename_unchanged(self):
        """Normal filenames should pass through unchanged."""
        assert sanitize_filename("document.pdf") == "document.pdf"
        assert sanitize_filename("my-file_2024.png") == "my-file_2024.png"

    def test_removes_path_separators(self):
        """Path separators should be replaced with underscores."""
        assert sanitize_filename("path/to/file.pdf") == "path_to_file.pdf"
        assert sanitize_filename("path\\to\\file.pdf") == "path_to_file.pdf"

    def test_removes_null_bytes(self):
        """Null bytes should be removed."""
        assert sanitize_filename("file\x00name.pdf") == "filename.pdf"

    def test_removes_newlines(self):
        """Newline characters should be replaced (header injection prevention)."""
        assert sanitize_filename("file\nname.pdf") == "file_name.pdf"
        assert sanitize_filename("file\rname.pdf") == "file_name.pdf"
        assert sanitize_filename("file\r\nname.pdf") == "file__name.pdf"

    def test_removes_leading_dots(self):
        """Leading dots should be stripped to prevent hidden files."""
        assert sanitize_filename(".hidden") == "hidden"
        assert sanitize_filename("..hidden") == "hidden"
        assert sanitize_filename("...file.pdf") == "file.pdf"

    def test_truncates_long_filenames(self):
        """Filenames exceeding 255 characters should be truncated."""
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".pdf")

    def test_empty_filename_becomes_unnamed(self):
        """Empty or all-dots filename should become 'unnamed'."""
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename("...") == "unnamed"

    def test_preserves_extension_on_truncation(self):
        """Extension should be preserved when truncating long filenames."""
        long_name = "a" * 260 + ".pdf"
        result = sanitize_filename(long_name)
        assert result.endswith(".pdf")


class TestDetectMimeFromBytes:
    """Tests for detect_mime_from_bytes function."""

    def test_detects_pdf(self, valid_pdf_bytes):
        """Should detect PDF files from magic bytes."""
        assert detect_mime_from_bytes(valid_pdf_bytes) == "application/pdf"

    def test_detects_png(self, valid_png_bytes):
        """Should detect PNG files from magic bytes."""
        assert detect_mime_from_bytes(valid_png_bytes) == "image/png"

    def test_detects_jpeg(self):
        """Should detect JPEG files from magic bytes."""
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        assert detect_mime_from_bytes(jpeg_bytes) == "image/jpeg"

    def test_detects_tiff_little_endian(self):
        """Should detect little-endian TIFF files."""
        tiff_bytes = b"II\x2a\x00rest of file"
        assert detect_mime_from_bytes(tiff_bytes) == "image/tiff"

    def test_detects_tiff_big_endian(self):
        """Should detect big-endian TIFF files."""
        tiff_bytes = b"MM\x00\x2arest of file"
        assert detect_mime_from_bytes(tiff_bytes) == "image/tiff"

    def test_returns_none_for_unknown(self, invalid_file_bytes):
        """Should return None for unrecognized file types."""
        assert detect_mime_from_bytes(invalid_file_bytes) is None

    def test_returns_none_for_short_bytes(self):
        """Should return None for files too short to identify."""
        assert detect_mime_from_bytes(b"AB") is None
        assert detect_mime_from_bytes(b"") is None


class TestBuildContentDisposition:
    """Tests for safe Content-Disposition header generation."""

    def test_builds_attachment_header_with_quoted_and_utf8_filename(self):
        header = build_content_disposition("attachment", 'report "Q1".pdf')
        assert header.startswith('attachment; filename="')
        assert "filename*=UTF-8''" in header
        assert "\n" not in header
        assert "\r" not in header

    def test_builds_inline_header_with_unicode_filename(self):
        header = build_content_disposition("inline", "Certificado-ñ.pdf")
        assert header.startswith('inline; filename="')
        assert "filename*=UTF-8''Certificado-%C3%B1.pdf" in header

    def test_rejects_invalid_disposition_type(self):
        with pytest.raises(ValueError, match="Invalid disposition type"):
            build_content_disposition("download", "file.pdf")


class TestValidateUploadBytesAndType:
    """Tests for validate_upload_bytes_and_type function."""

    def test_accepts_valid_pdf(self, valid_pdf_bytes):
        """Should accept valid PDF files."""
        is_valid, mime_type, error = validate_upload_bytes_and_type(
            valid_pdf_bytes, "document.pdf"
        )
        assert is_valid is True
        assert mime_type == "application/pdf"
        assert error is None

    def test_accepts_valid_png(self, valid_png_bytes):
        """Should accept valid PNG files."""
        is_valid, mime_type, error = validate_upload_bytes_and_type(
            valid_png_bytes, "image.png"
        )
        assert is_valid is True
        assert mime_type == "image/png"
        assert error is None

    def test_rejects_empty_file(self):
        """Should reject empty files."""
        is_valid, mime_type, error = validate_upload_bytes_and_type(
            b"", "empty.pdf"
        )
        assert is_valid is False
        assert error is not None
        assert "empty" in error.lower()

    def test_rejects_unknown_type(self, invalid_file_bytes):
        """Should reject files with unrecognized types."""
        is_valid, mime_type, error = validate_upload_bytes_and_type(
            invalid_file_bytes, "unknown.xyz"
        )
        assert is_valid is False
        assert error is not None

    def test_rejects_oversized_file(self, valid_pdf_bytes):
        """Should reject files exceeding max size."""
        # Create oversized content
        oversized = valid_pdf_bytes + (b"x" * (51 * 1024 * 1024))
        is_valid, mime_type, error = validate_upload_bytes_and_type(
            oversized, "large.pdf"
        )
        assert is_valid is False
        assert error is not None
        assert "size" in error.lower() or "large" in error.lower()

    def test_custom_allowed_types(self, valid_pdf_bytes):
        """Should respect custom allowed types parameter."""
        # PDF should be rejected if not in allowed types
        is_valid, mime_type, error = validate_upload_bytes_and_type(
            valid_pdf_bytes,
            "document.pdf",
            allowed_types={"image/png", "image/jpeg"},
        )
        assert is_valid is False

    def test_custom_max_size(self, valid_pdf_bytes):
        """Should respect custom max size parameter."""
        # Even small file should be rejected with tiny max size
        is_valid, mime_type, error = validate_upload_bytes_and_type(
            valid_pdf_bytes,
            "document.pdf",
            max_size_bytes=10,
        )
        assert is_valid is False
