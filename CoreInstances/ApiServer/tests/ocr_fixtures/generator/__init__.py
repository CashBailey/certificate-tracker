"""OCR test fixture generator package."""

from .certificate_template import CertificateData, render_certificate, SAMPLE_CERTIFICATES
from .distortions import DISTORTION_PRESETS

__all__ = [
    "CertificateData",
    "render_certificate",
    "SAMPLE_CERTIFICATES",
    "DISTORTION_PRESETS",
]
