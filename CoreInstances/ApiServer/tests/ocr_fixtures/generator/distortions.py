"""
Distortion functions for OCR test image generation.

Applies controlled degradations to certificate images to test OCR resilience.
"""

import io
import random
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


def apply_skew(image: Image.Image, angle_degrees: float) -> Image.Image:
    """
    Rotate image by specified angle to simulate scanner skew.

    Args:
        image: PIL Image to rotate
        angle_degrees: Rotation angle in degrees (positive = counterclockwise)

    Returns:
        Rotated image with white background fill
    """
    return image.rotate(
        angle_degrees,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(255, 255, 255),
    )


def apply_gaussian_blur(image: Image.Image, sigma: float) -> Image.Image:
    """
    Apply Gaussian blur to simulate out-of-focus scan.

    Args:
        image: PIL Image to blur
        sigma: Standard deviation for Gaussian kernel (higher = more blur)

    Returns:
        Blurred image
    """
    # PIL's GaussianBlur radius is approximately sigma * 2
    radius = max(1, int(sigma * 2))
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def apply_jpeg_compression(image: Image.Image, quality: int) -> Image.Image:
    """
    Apply JPEG compression artifacts by re-encoding.

    Args:
        image: PIL Image to compress
        quality: JPEG quality (1-100, lower = more artifacts)

    Returns:
        Image with JPEG compression artifacts
    """
    buffer = io.BytesIO()
    # Convert to RGB if necessary (JPEG doesn't support alpha)
    if image.mode == "RGBA":
        image = image.convert("RGB")
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).copy()


def apply_low_dpi(image: Image.Image, target_dpi: int, original_dpi: int = 300) -> Image.Image:
    """
    Simulate low-resolution scan by downscaling then upscaling.

    Args:
        image: PIL Image to degrade
        target_dpi: Target DPI to simulate
        original_dpi: Original image DPI (default 300)

    Returns:
        Image simulating lower DPI capture
    """
    scale_factor = target_dpi / original_dpi
    original_size = image.size

    # Downscale
    small_size = (int(image.width * scale_factor), int(image.height * scale_factor))
    small = image.resize(small_size, resample=Image.Resampling.BILINEAR)

    # Upscale back to original size (introduces pixelation)
    return small.resize(original_size, resample=Image.Resampling.BILINEAR)


def apply_noise(image: Image.Image, noise_level: float = 0.02) -> Image.Image:
    """
    Add salt-and-pepper noise to simulate scanner dust/defects.

    Args:
        image: PIL Image to add noise to
        noise_level: Probability of each pixel being affected (0-1)

    Returns:
        Image with noise added
    """
    img_array = np.array(image)

    # Generate noise mask
    noise_mask = np.random.random(img_array.shape[:2])

    # Salt (white pixels)
    salt_mask = noise_mask < (noise_level / 2)
    img_array[salt_mask] = 255

    # Pepper (black pixels)
    pepper_mask = noise_mask > (1 - noise_level / 2)
    img_array[pepper_mask] = 0

    return Image.fromarray(img_array)


def apply_contrast_reduction(image: Image.Image, factor: float = 0.7) -> Image.Image:
    """
    Reduce contrast to simulate faded document.

    Args:
        image: PIL Image to adjust
        factor: Contrast factor (1.0 = original, <1 = reduced contrast)

    Returns:
        Image with reduced contrast
    """
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


def apply_brightness_variation(image: Image.Image, factor: float = 0.9) -> Image.Image:
    """
    Adjust brightness to simulate uneven scanner lighting.

    Args:
        image: PIL Image to adjust
        factor: Brightness factor (1.0 = original, <1 = darker)

    Returns:
        Image with adjusted brightness
    """
    enhancer = ImageEnhance.Brightness(image)
    return enhancer.enhance(factor)


def apply_scanner_shadow(image: Image.Image, shadow_width: int = 30) -> Image.Image:
    """
    Add dark gradient on edges to simulate scanner lid shadow.

    Args:
        image: PIL Image to add shadow to
        shadow_width: Width of shadow gradient in pixels

    Returns:
        Image with edge shadows
    """
    img_array = np.array(image).astype(np.float32)

    # Create gradient for left edge
    for x in range(min(shadow_width, image.width)):
        factor = x / shadow_width
        img_array[:, x] = img_array[:, x] * (0.7 + 0.3 * factor)

    # Create gradient for right edge
    for x in range(max(0, image.width - shadow_width), image.width):
        factor = (image.width - x) / shadow_width
        img_array[:, x] = img_array[:, x] * (0.7 + 0.3 * factor)

    return Image.fromarray(np.clip(img_array, 0, 255).astype(np.uint8))


def apply_paper_texture(image: Image.Image, intensity: float = 0.1) -> Image.Image:
    """
    Add subtle paper grain texture.

    Args:
        image: PIL Image to add texture to
        intensity: Texture visibility (0-1)

    Returns:
        Image with paper texture overlay
    """
    img_array = np.array(image).astype(np.float32)

    # Generate noise texture
    texture = np.random.normal(0, 255 * intensity, img_array.shape)

    # Add texture
    result = img_array + texture
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def apply_scanned_simulation(
    image: Image.Image,
    skew_range: tuple[float, float] = (-3, 3),
    add_shadow: bool = True,
    add_texture: bool = True,
    blur_sigma: float = 0.5,
) -> Image.Image:
    """
    Apply combined distortions to simulate a realistic scanned document.

    Args:
        image: PIL Image to distort
        skew_range: Range of random skew angles (min, max) in degrees
        add_shadow: Whether to add scanner edge shadows
        add_texture: Whether to add paper texture
        blur_sigma: Gaussian blur sigma (0 = no blur)

    Returns:
        Image simulating a scanned document
    """
    result = image.copy()

    # Random slight skew
    skew_angle = random.uniform(*skew_range)
    if abs(skew_angle) > 0.5:
        result = apply_skew(result, skew_angle)

    # Scanner shadows
    if add_shadow:
        result = apply_scanner_shadow(result, shadow_width=20)

    # Paper texture
    if add_texture:
        result = apply_paper_texture(result, intensity=0.05)

    # Slight blur
    if blur_sigma > 0:
        result = apply_gaussian_blur(result, blur_sigma)

    # Slight contrast reduction (common in scans)
    result = apply_contrast_reduction(result, factor=0.9)

    return result


# Distortion presets for test generation
DISTORTION_PRESETS = {
    "skew_05": {
        "func": apply_skew,
        "params": {"angle_degrees": 5},
        "accuracy_threshold": 0.90,
        "description": "5 degree rotation",
    },
    "skew_10": {
        "func": apply_skew,
        "params": {"angle_degrees": 10},
        "accuracy_threshold": 0.65,
        "description": "10 degree rotation",
    },
    "blur_1": {
        "func": apply_gaussian_blur,
        "params": {"sigma": 0.5},
        "accuracy_threshold": 0.80,
        "description": "Light Gaussian blur (sigma=0.5)",
    },
    "blur_2": {
        "func": apply_gaussian_blur,
        "params": {"sigma": 1.0},
        "accuracy_threshold": 0.50,
        "description": "Medium Gaussian blur (sigma=1)",
    },
    "lowdpi_150": {
        "func": apply_low_dpi,
        "params": {"target_dpi": 150},
        "accuracy_threshold": 0.65,
        "description": "Low resolution (150 DPI)",
    },
    "jpeg_40": {
        "func": apply_jpeg_compression,
        "params": {"quality": 40},
        "accuracy_threshold": 0.85,
        "description": "JPEG compression (Q=40)",
    },
    "noise": {
        "func": apply_noise,
        "params": {"noise_level": 0.02},
        "accuracy_threshold": 0.80,
        "description": "Salt and pepper noise",
    },
    "scanned": {
        "func": apply_scanned_simulation,
        "params": {},
        "accuracy_threshold": 0.75,
        "description": "Simulated scan (skew + shadow + texture + blur)",
    },
}
