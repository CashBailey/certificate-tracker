"""
Certificate template renderer for OCR test image generation.

Renders certificate images with known text content for ground truth verification.
"""

from PIL import Image, ImageDraw, ImageFont
from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class CertificateData:
    """Data structure for certificate content."""

    certificate_holder_name: str
    certificate_type: str
    issue_date: str
    expiration_date: str
    issuing_authority: str
    certificate_number: str

    def to_ground_truth(self) -> dict:
        """Convert to ground truth JSON format."""
        return {
            "certificate_holder_name": self.certificate_holder_name,
            "certificate_type": self.certificate_type,
            "issue_date": self.issue_date,
            "expiration_date": self.expiration_date,
            "issuing_authority": self.issuing_authority,
            "certificate_number": self.certificate_number,
        }


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Get a font for rendering. Falls back to default if system fonts unavailable.

    Args:
        size: Font size in points
        bold: Whether to use bold weight

    Returns:
        PIL ImageFont object
    """
    # Try common system font paths
    font_paths = [
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        # Windows
        "C:\\Windows\\Fonts\\arial.ttf",
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue

    # Fallback to default bitmap font
    return ImageFont.load_default()


def render_certificate(
    data: CertificateData,
    width: int = 800,
    height: int = 600,
    dpi: int = 300,
) -> Image.Image:
    """
    Render a certificate image with the given data.

    Creates a clean, readable certificate layout suitable for OCR testing.

    Args:
        data: Certificate content to render
        width: Image width in pixels
        height: Image height in pixels
        dpi: Target DPI (for scaling calculations)

    Returns:
        PIL Image with rendered certificate
    """
    # Create white background
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Get fonts
    title_font = get_font(28, bold=True)
    header_font = get_font(18, bold=True)
    body_font = get_font(16)
    small_font = get_font(12)

    # Colors
    black = (0, 0, 0)
    dark_gray = (64, 64, 64)
    blue = (0, 51, 102)

    # Draw border
    border_margin = 20
    draw.rectangle(
        [border_margin, border_margin, width - border_margin, height - border_margin],
        outline=blue,
        width=3,
    )

    # Inner border
    inner_margin = 30
    draw.rectangle(
        [inner_margin, inner_margin, width - inner_margin, height - inner_margin],
        outline=dark_gray,
        width=1,
    )

    # Title: Certificate Type
    y_pos = 60
    draw.text(
        (width // 2, y_pos),
        "CERTIFICATE OF COMPLETION",
        font=title_font,
        fill=blue,
        anchor="mm",
    )

    # Certificate type
    y_pos += 50
    draw.text(
        (width // 2, y_pos),
        data.certificate_type,
        font=header_font,
        fill=black,
        anchor="mm",
    )

    # Decorative line
    y_pos += 30
    line_width = 200
    draw.line(
        [(width // 2 - line_width, y_pos), (width // 2 + line_width, y_pos)],
        fill=blue,
        width=2,
    )

    # "This certifies that"
    y_pos += 40
    draw.text(
        (width // 2, y_pos),
        "This certifies that",
        font=body_font,
        fill=dark_gray,
        anchor="mm",
    )

    # Certificate holder name (prominent)
    y_pos += 40
    draw.text(
        (width // 2, y_pos),
        data.certificate_holder_name,
        font=header_font,
        fill=black,
        anchor="mm",
    )

    # "has successfully completed" text
    y_pos += 40
    draw.text(
        (width // 2, y_pos),
        "has successfully completed the requirements for",
        font=body_font,
        fill=dark_gray,
        anchor="mm",
    )

    # Certificate type again
    y_pos += 30
    draw.text(
        (width // 2, y_pos),
        data.certificate_type,
        font=body_font,
        fill=black,
        anchor="mm",
    )

    # Dates section
    y_pos += 60

    # Issue date (left side)
    draw.text(
        (150, y_pos),
        "Issue Date:",
        font=small_font,
        fill=dark_gray,
        anchor="mm",
    )
    draw.text(
        (150, y_pos + 20),
        data.issue_date,
        font=body_font,
        fill=black,
        anchor="mm",
    )

    # Expiration date (right side)
    draw.text(
        (width - 150, y_pos),
        "Expiration Date:",
        font=small_font,
        fill=dark_gray,
        anchor="mm",
    )
    draw.text(
        (width - 150, y_pos + 20),
        data.expiration_date,
        font=body_font,
        fill=black,
        anchor="mm",
    )

    # Issuing authority
    y_pos += 80
    draw.text(
        (width // 2, y_pos),
        "Issued by:",
        font=small_font,
        fill=dark_gray,
        anchor="mm",
    )
    draw.text(
        (width // 2, y_pos + 20),
        data.issuing_authority,
        font=body_font,
        fill=black,
        anchor="mm",
    )

    # Certificate number
    y_pos += 60
    draw.text(
        (width // 2, y_pos),
        f"Certificate No: {data.certificate_number}",
        font=small_font,
        fill=dark_gray,
        anchor="mm",
    )

    return image


# Sample certificate data for testing
SAMPLE_CERTIFICATES = [
    CertificateData(
        certificate_holder_name="John Michael Doe",
        certificate_type="CPR/BLS Certification",
        issue_date="2024-01-15",
        expiration_date="2026-01-15",
        issuing_authority="American Heart Association",
        certificate_number="AHA-2024-123456",
    ),
    CertificateData(
        certificate_holder_name="Maria Elena Garcia",
        certificate_type="First Aid Certification",
        issue_date="2024-02-20",
        expiration_date="2026-02-20",
        issuing_authority="American Red Cross",
        certificate_number="ARC-2024-789012",
    ),
    CertificateData(
        certificate_holder_name="Robert James Smith",
        certificate_type="HIPAA Compliance Training",
        issue_date="2024-03-10",
        expiration_date="2025-03-10",
        issuing_authority="City of Laredo Health Department",
        certificate_number="CLH-2024-345678",
    ),
    CertificateData(
        certificate_holder_name="Ana Isabel Martinez",
        certificate_type="Bloodborne Pathogens Training",
        issue_date="2024-04-05",
        expiration_date="2025-04-05",
        issuing_authority="OSHA Training Institute",
        certificate_number="OSHA-2024-901234",
    ),
    CertificateData(
        certificate_holder_name="William Thomas Johnson",
        certificate_type="Food Handler Certification",
        issue_date="2024-05-12",
        expiration_date="2026-05-12",
        issuing_authority="Texas Department of State Health Services",
        certificate_number="DSHS-2024-567890",
    ),
    CertificateData(
        certificate_holder_name="Carmen Rosa Lopez",
        certificate_type="Emergency Medical Responder",
        issue_date="2024-06-18",
        expiration_date="2026-06-18",
        issuing_authority="National Registry of EMTs",
        certificate_number="NREMT-2024-112233",
    ),
    CertificateData(
        certificate_holder_name="David Alexander Brown",
        certificate_type="Hazardous Materials Handling",
        issue_date="2024-07-22",
        expiration_date="2025-07-22",
        issuing_authority="EPA Training Center",
        certificate_number="EPA-2024-445566",
    ),
    CertificateData(
        certificate_holder_name="Patricia Ann Wilson",
        certificate_type="Tuberculosis Screening Certification",
        issue_date="2024-08-30",
        expiration_date="2025-08-30",
        issuing_authority="Texas Health and Human Services",
        certificate_number="THHS-2024-778899",
    ),
    CertificateData(
        certificate_holder_name="Miguel Angel Rodriguez",
        certificate_type="Infection Control Training",
        issue_date="2024-09-14",
        expiration_date="2025-09-14",
        issuing_authority="CDC Training Division",
        certificate_number="CDC-2024-001122",
    ),
    CertificateData(
        certificate_holder_name="Jennifer Lynn Davis",
        certificate_type="Mental Health First Aid",
        issue_date="2024-10-25",
        expiration_date="2027-10-25",
        issuing_authority="National Council for Mental Wellbeing",
        certificate_number="NCMW-2024-334455",
    ),
]
