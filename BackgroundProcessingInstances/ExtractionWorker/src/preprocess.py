"""
Image preprocessing for OCR.

Provides deskew and denoising operations using PIL and OpenCV.
"""

from io import BytesIO
from importlib.util import find_spec

import numpy as np
from PIL import Image


class PillowImagePreprocessor:
    """Image preprocessor using Pillow and OpenCV."""

    def deskew(self, image_bytes: bytes) -> bytes:
        """
        Deskew (straighten) an image.

        Uses Hough transform to detect dominant line angle and rotate.

        Args:
            image_bytes: Input image bytes (PNG/JPEG)

        Returns:
            Deskewed image bytes (PNG)
        """
        if find_spec("cv2") is None:
            # If OpenCV not available, return original
            return image_bytes

        # Load image
        pil_image = Image.open(BytesIO(image_bytes))

        # Convert to grayscale numpy array
        if pil_image.mode != 'L':
            gray = pil_image.convert('L')
        else:
            gray = pil_image

        img_array = np.array(gray)

        # Detect skew angle using Hough transform
        angle = self._detect_skew_angle(img_array)

        if abs(angle) < 0.5:
            # Negligible skew, return original
            return image_bytes

        # Rotate to correct skew
        # Convert back to RGB for rotation
        if pil_image.mode == 'L':
            pil_image = pil_image.convert('RGB')

        rotated = pil_image.rotate(
            angle,
            resample=Image.BICUBIC,
            expand=True,
            fillcolor=(255, 255, 255),
        )

        # Convert back to bytes
        output = BytesIO()
        rotated.save(output, format='PNG')
        return output.getvalue()

    def _detect_skew_angle(self, gray_array: np.ndarray) -> float:
        """
        Detect skew angle using Hough line transform.

        Args:
            gray_array: Grayscale image as numpy array

        Returns:
            Detected skew angle in degrees
        """
        try:
            import cv2
        except ImportError:
            return 0.0

        # Apply edge detection
        edges = cv2.Canny(gray_array, 50, 150, apertureSize=3)

        # Detect lines using Hough transform
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)

        if lines is None or len(lines) == 0:
            return 0.0

        # Calculate angles from detected lines
        angles = []
        for line in lines[:20]:  # Use top 20 lines
            rho, theta = line[0]
            angle = (theta * 180 / np.pi) - 90
            # Keep angles close to horizontal
            if -45 < angle < 45:
                angles.append(angle)

        if not angles:
            return 0.0

        # Return median angle
        return float(np.median(angles))

    def denoise(self, image_bytes: bytes) -> bytes:
        """
        Remove noise from an image.

        Uses bilateral filter to reduce noise while preserving edges.

        Args:
            image_bytes: Input image bytes

        Returns:
            Denoised image bytes (PNG)
        """
        try:
            import cv2
        except ImportError:
            return image_bytes

        # Load image
        pil_image = Image.open(BytesIO(image_bytes))
        img_array = np.array(pil_image)

        # Apply bilateral filter (preserves edges better than Gaussian)
        if len(img_array.shape) == 3:
            denoised = cv2.bilateralFilter(img_array, 9, 75, 75)
        else:
            denoised = cv2.bilateralFilter(img_array, 9, 75, 75)

        # Convert back to PIL and bytes
        result_image = Image.fromarray(denoised)
        output = BytesIO()
        result_image.save(output, format='PNG')
        return output.getvalue()

    def binarize(self, image_bytes: bytes) -> bytes:
        """
        Convert image to binary (black and white) using adaptive thresholding.

        Useful for improving OCR on low-contrast documents.

        Args:
            image_bytes: Input image bytes

        Returns:
            Binarized image bytes (PNG)
        """
        try:
            import cv2
        except ImportError:
            return image_bytes

        # Load and convert to grayscale
        pil_image = Image.open(BytesIO(image_bytes))
        gray = pil_image.convert('L')
        img_array = np.array(gray)

        # Apply adaptive thresholding
        binary = cv2.adaptiveThreshold(
            img_array,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11,
            2,
        )

        # Convert back to PIL and bytes
        result_image = Image.fromarray(binary)
        output = BytesIO()
        result_image.save(output, format='PNG')
        return output.getvalue()
