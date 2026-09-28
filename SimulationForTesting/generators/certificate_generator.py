"""
Certificate image generator with variety.

Overlays employee name, course name, and completion date onto certificate templates
with randomized fonts, date formats, and name styles for realistic simulation.
"""

import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


# Date format variations with weights
DATE_FORMATS = [
    ("%m/%d/%Y", 40),       # 03/15/2024 - most common
    ("%B %d, %Y", 25),      # March 15, 2024
    ("%b %d, %Y", 15),      # Mar 15, 2024
    ("%m-%d-%Y", 10),       # 03-15-2024
    ("%Y-%m-%d", 5),        # 2024-03-15 (ISO)
    ("%d %B %Y", 5),        # 15 March 2024 (European style)
]

# Name style variations with weights
NAME_STYLES = [
    ("full", 50),           # Maria Elena Rodriguez
    ("formal", 25),         # Maria Rodriguez
    ("with_middle_initial", 15),  # Maria E. Rodriguez
    ("last_first", 10),     # Rodriguez, Maria
]

# Font size ranges for each field (min, max) - maximized for variety
FONT_SIZE_RANGES = {
    "name": (32, 54),      # Wide range: 32pt to 54pt
    "course": (16, 28),    # Wide range: 16pt to 28pt
    "date": (16, 28),      # Wide range: 16pt to 28pt
}

# Position jitter ranges (Y percent variation) - maximized within bounding boxes
# Name box: 36.5%-47.7%, Course box: 54%-60.7%, Date box: 64%-73.2%
POSITION_JITTER = {
    "name": (-3, 3),       # ±3% keeps within 39-45% (inside 36.5-47.7%)
    "course": (-2, 2),     # ±2% keeps within 55-59% (inside 54-60.7%)
    "date": (-3, 3),       # ±3% keeps within 66-72% (inside 64-73.2%)
}

# Color variations (navy blues and blacks)
COLOR_VARIATIONS = [
    "#2B3A67",  # Navy blue (default)
    "#1a237e",  # Dark blue
    "#283593",  # Indigo
    "#303F9F",  # Blue
    "#000000",  # Black
    "#1C1C1C",  # Near black
    "#2C3E50",  # Dark blue-gray
]


@dataclass
class FieldPosition:
    """Position configuration for a text field."""

    y_percent: float
    x_percent: float = 50
    alignment: str = "center"
    font_size: int = 48
    color: str = "#2B3A67"


@dataclass
class CertificateConfig:
    """Configuration for certificate generation."""

    template_path: Path
    name_position: FieldPosition
    course_position: FieldPosition
    date_position: FieldPosition
    font_path: Optional[Path] = None


# Default configuration for LMS certificate
# Positions from user-provided bounding boxes (image: 2000x1545px)
# Name: Y center at 650.5px = 42.1%, Course: 885.7px = 57.3%, Date: 1059.3px = 68.6%
DEFAULT_LMS_CONFIG = CertificateConfig(
    template_path=Path("SampleDocs/certificate_6275_preview_blank.png"),
    name_position=FieldPosition(y_percent=42, font_size=48, color="#2B3A67"),
    course_position=FieldPosition(y_percent=57, font_size=24, color="#2B3A67"),
    date_position=FieldPosition(y_percent=69, font_size=24, color="#2B3A67"),
)


class CertificateGenerator:
    """
    Generates certificate images with visual variety.
    """

    def __init__(
        self,
        config: Optional[CertificateConfig] = None,
        base_path: Optional[Path] = None,
        enable_variety: bool = True,
        random_seed: Optional[int] = None,
    ):
        """
        Initialize the generator.

        Args:
            config: Certificate configuration (defaults to LMS style)
            base_path: Base path for resolving template paths
            enable_variety: Enable random variations in fonts, dates, names
            random_seed: Random seed for reproducibility
        """
        self.config = config or DEFAULT_LMS_CONFIG
        self.base_path = base_path or Path(__file__).parent.parent.parent
        self.enable_variety = enable_variety

        if random_seed is not None:
            random.seed(random_seed)

        # Load template
        template_path = self.base_path / self.config.template_path
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        self.template = Image.open(template_path)
        self.width, self.height = self.template.size

        # Load multiple font families
        self.font_families = {}
        self._load_fonts()

    def _load_fonts(self) -> None:
        """Load multiple font families for variety."""
        # Define font families to try
        font_candidates = {
            "serif": [
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
                "/usr/share/fonts/TTF/DejaVuSerif.ttf",
            ],
            "serif_bold": [
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf",
            ],
            "sans": [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            ],
            "sans_bold": [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            ],
            "mono": [
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
                "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
            ],
        }

        sizes = [20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 64]

        for family_name, paths in font_candidates.items():
            font_path = None
            for path in paths:
                if Path(path).exists():
                    font_path = path
                    break

            if font_path:
                self.font_families[family_name] = {}
                for size in sizes:
                    try:
                        self.font_families[family_name][size] = ImageFont.truetype(
                            font_path, size
                        )
                    except Exception:
                        pass

        # Ensure we have at least one font family
        if not self.font_families:
            self.font_families["default"] = {}
            for size in sizes:
                self.font_families["default"][size] = ImageFont.load_default()

    def _get_font(
        self, size: int, family: Optional[str] = None
    ) -> ImageFont.FreeTypeFont:
        """Get font for given size and family."""
        if family is None or family not in self.font_families:
            family = random.choice(list(self.font_families.keys()))

        fonts = self.font_families[family]
        if not fonts:
            return ImageFont.load_default()

        # Find closest available size
        available = sorted(fonts.keys())
        closest = min(available, key=lambda x: abs(x - size))
        return fonts[closest]

    def _pick_weighted(self, choices: list[tuple]) -> any:
        """Pick from weighted choices list of (item, weight) tuples."""
        total = sum(w for _, w in choices)
        r = random.uniform(0, total)
        cumulative = 0
        for item, weight in choices:
            cumulative += weight
            if r <= cumulative:
                return item
        return choices[-1][0]

    def _format_name(self, full_name: str, style: str) -> str:
        """
        Format a name in the specified style.

        Args:
            full_name: Full name like "Maria Elena Rodriguez"
            style: One of 'full', 'formal', 'with_middle_initial', 'last_first'

        Returns:
            Formatted name
        """
        parts = full_name.split()
        if len(parts) < 2:
            return full_name

        if style == "full":
            return full_name

        elif style == "formal":
            # First Last (drop middle name)
            if len(parts) >= 3:
                return f"{parts[0]} {parts[-1]}"
            return full_name

        elif style == "with_middle_initial":
            # First M. Last
            if len(parts) >= 3:
                return f"{parts[0]} {parts[1][0]}. {parts[-1]}"
            return full_name

        elif style == "last_first":
            # Last, First
            if len(parts) >= 2:
                return f"{parts[-1]}, {parts[0]}"
            return full_name

        return full_name

    def _calculate_text_position(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        position: FieldPosition,
        font: ImageFont.FreeTypeFont,
    ) -> tuple[int, int]:
        """Calculate x, y position for text based on alignment."""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        y = int(self.height * position.y_percent / 100) - text_height // 2

        if position.alignment == "center":
            x = int(self.width * position.x_percent / 100) - text_width // 2
        elif position.alignment == "left":
            x = int(self.width * position.x_percent / 100)
        else:
            x = int(self.width * position.x_percent / 100) - text_width

        return x, y

    def generate(
        self,
        name: str,
        course: str,
        completion_date: date,
        date_format: Optional[str] = None,
        name_style: Optional[str] = None,
        font_family: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Image.Image:
        """
        Generate a certificate image with optional variety.

        Args:
            name: Certificate holder name
            course: Course/training name
            completion_date: Date of completion
            date_format: Date format (random if None and variety enabled)
            name_style: Name style (random if None and variety enabled)
            font_family: Font family (random if None and variety enabled)
            color: Text color (random if None and variety enabled)

        Returns:
            PIL Image with text overlaid
        """
        # Apply variety if enabled
        if self.enable_variety:
            if date_format is None:
                date_format = self._pick_weighted(DATE_FORMATS)
            if name_style is None:
                name_style = self._pick_weighted(NAME_STYLES)
            if font_family is None:
                # Prefer serif fonts but allow variety
                font_family = random.choices(
                    list(self.font_families.keys()),
                    weights=[3 if "serif" in f else 1 for f in self.font_families.keys()],
                )[0]
            if color is None:
                color = random.choice(COLOR_VARIATIONS)

            # Random font sizes within ranges
            name_size = random.randint(*FONT_SIZE_RANGES["name"])
            course_size = random.randint(*FONT_SIZE_RANGES["course"])
            date_size = random.randint(*FONT_SIZE_RANGES["date"])

            # Random position jitter (Y offset in percent)
            name_y_jitter = random.uniform(*POSITION_JITTER["name"])
            course_y_jitter = random.uniform(*POSITION_JITTER["course"])
            date_y_jitter = random.uniform(*POSITION_JITTER["date"])
        else:
            date_format = date_format or "%m/%d/%Y"
            name_style = name_style or "full"
            font_family = font_family or list(self.font_families.keys())[0]
            color = color or self.config.name_position.color
            name_size = self.config.name_position.font_size
            course_size = self.config.course_position.font_size
            date_size = self.config.date_position.font_size
            name_y_jitter = course_y_jitter = date_y_jitter = 0

        # Format the name
        formatted_name = self._format_name(name, name_style)

        # Create a copy of the template
        image = self.template.copy()
        draw = ImageDraw.ImageDraw(image)

        # Create position copies with jitter applied
        name_pos = FieldPosition(
            y_percent=self.config.name_position.y_percent + name_y_jitter,
            x_percent=self.config.name_position.x_percent,
            alignment=self.config.name_position.alignment,
        )
        course_pos = FieldPosition(
            y_percent=self.config.course_position.y_percent + course_y_jitter,
            x_percent=self.config.course_position.x_percent,
            alignment=self.config.course_position.alignment,
        )
        date_pos = FieldPosition(
            y_percent=self.config.date_position.y_percent + date_y_jitter,
            x_percent=self.config.date_position.x_percent,
            alignment=self.config.date_position.alignment,
        )

        # Draw name
        name_font = self._get_font(name_size, font_family)
        name_x, name_y = self._calculate_text_position(
            draw, formatted_name, name_pos, name_font
        )
        draw.text((name_x, name_y), formatted_name, font=name_font, fill=color)

        # Draw course name
        course_font = self._get_font(course_size, font_family)
        course_x, course_y = self._calculate_text_position(
            draw, course, course_pos, course_font
        )
        draw.text((course_x, course_y), course, font=course_font, fill=color)

        # Draw date
        date_str = completion_date.strftime(date_format)
        date_font = self._get_font(date_size, font_family)
        date_x, date_y = self._calculate_text_position(
            draw, date_str, date_pos, date_font
        )
        draw.text((date_x, date_y), date_str, font=date_font, fill=color)

        return image

    def generate_and_save(
        self,
        name: str,
        course: str,
        completion_date: date,
        output_path: Path,
        date_format: Optional[str] = None,
        name_style: Optional[str] = None,
        font_family: Optional[str] = None,
        color: Optional[str] = None,
        quality: int = 95,
    ) -> dict:
        """
        Generate and save a certificate with variety.

        Args:
            name: Certificate holder name
            course: Course/training name
            completion_date: Date of completion
            output_path: Path to save the image
            date_format: Date format (random if None)
            name_style: Name style (random if None)
            font_family: Font family (random if None)
            color: Text color (random if None)
            quality: JPEG quality

        Returns:
            Dict with metadata about variations used
        """
        image = self.generate(
            name, course, completion_date, date_format, name_style, font_family, color
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.suffix.lower() in [".jpg", ".jpeg"]:
            if image.mode == "RGBA":
                rgb_image = Image.new("RGB", image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[3])
                image = rgb_image
            image.save(output_path, "JPEG", quality=quality)
        else:
            image.save(output_path, "PNG")

        return {
            "date_format": date_format,
            "name_style": name_style,
            "font_family": font_family,
            "color": color,
        }


def generate_random_date(
    start_year: int = 2021,
    end_year: int = 2026,
    reference_date: Optional[date] = None,
) -> date:
    """Generate a random date within range."""
    if reference_date is None:
        reference_date = date.today()

    start = date(start_year, 1, 1)
    end = min(date(end_year, 12, 31), reference_date)

    days_between = (end - start).days
    if days_between <= 0:
        return start

    random_days = random.randint(0, days_between)
    return start + __import__("datetime").timedelta(days=random_days)


if __name__ == "__main__":
    from datetime import date

    print("=== Certificate Generator Test with Variety ===")

    generator = CertificateGenerator(enable_variety=True, random_seed=None)
    print(f"Template size: {generator.width}x{generator.height}")
    print(f"Font families loaded: {list(generator.font_families.keys())}")

    output_dir = Path(__file__).parent.parent / "output" / "certificates"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate several certificates to show variety
    test_names = [
        "Maria Elena Rodriguez",
        "John Michael Smith",
        "Karen Ann Baker",
        "Robert James Johnson",
        "Ana Sofia Martinez",
    ]

    test_courses = [
        "HIPAA Privacy & Security Training",
        "CPR / Basic Life Support (BLS)",
        "Workplace Violence Prevention",
    ]

    print("\nGenerating certificates with variety:")
    for i, name in enumerate(test_names):
        course = test_courses[i % len(test_courses)]
        test_date = date(2024, random.randint(1, 12), random.randint(1, 28))
        output_path = output_dir / f"variety_test_{i+1}.png"

        metadata = generator.generate_and_save(
            name=name,
            course=course,
            completion_date=test_date,
            output_path=output_path,
        )
        print(f"  {i+1}. {name[:20]:20s} -> {output_path.name}")
        print(f"      Font: {metadata.get('font_family', 'N/A')}, "
              f"Name: {metadata.get('name_style', 'N/A')}, "
              f"Date: {metadata.get('date_format', 'N/A')}")

    print("\nDone!")
