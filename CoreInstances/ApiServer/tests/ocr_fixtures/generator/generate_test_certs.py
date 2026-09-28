#!/usr/bin/env python3
"""
Generate OCR test certificates with ground truth labels.

This script creates certificate images and their corresponding JSON ground truth
files for automated OCR accuracy testing.

Usage:
    python generate_test_certs.py [--output-dir PATH] [--clean-only]

The script generates:
- Clean certificates (10 images)
- Skewed variants (5°, 10°)
- Degraded variants (blur, low DPI, JPEG artifacts)
- Scanned simulation (combined distortions)

Total: ~60 image/label pairs
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from certificate_template import (
    CertificateData,
    render_certificate,
    SAMPLE_CERTIFICATES,
)
from distortions import DISTORTION_PRESETS


def save_ground_truth(
    cert_data: CertificateData,
    output_path: Path,
    cert_id: str,
    distortions: list[str] | None = None,
    accuracy_threshold: float = 0.95,
) -> None:
    """
    Save ground truth JSON file for a certificate image.

    Args:
        cert_data: Certificate content
        output_path: Path to save JSON file
        cert_id: Unique identifier for this certificate/variant
        distortions: List of distortion names applied
        accuracy_threshold: Expected OCR accuracy for this variant
    """
    ground_truth = {
        "id": cert_id,
        "distortions": distortions or [],
        "accuracy_threshold": accuracy_threshold,
        "expected_fields": cert_data.to_ground_truth(),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2, ensure_ascii=False)


def generate_clean_certificates(
    certificates: list[CertificateData],
    output_dir: Path,
) -> list[tuple[str, Path]]:
    """
    Generate clean (undistorted) certificate images.

    Args:
        certificates: List of certificate data to render
        output_dir: Directory for clean certificates

    Returns:
        List of (cert_id, image_path) tuples for variant generation
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    for i, cert_data in enumerate(certificates, start=1):
        cert_id = f"cert_{i:03d}"

        # Render clean image
        image = render_certificate(cert_data)
        image_path = output_dir / f"{cert_id}.png"
        image.save(image_path, "PNG")

        # Save ground truth
        json_path = output_dir / f"{cert_id}.json"
        save_ground_truth(
            cert_data,
            json_path,
            cert_id,
            distortions=[],
            accuracy_threshold=0.90,  # 90% is realistic for OCR on clean images
        )

        generated.append((cert_id, image_path, cert_data))
        print(f"  Generated: {image_path.name}")

    return generated


def generate_distorted_variants(
    clean_certs: list[tuple[str, Path, CertificateData]],
    base_output_dir: Path,
    distortion_presets: dict,
) -> int:
    """
    Generate distorted variants of clean certificates.

    Args:
        clean_certs: List of (cert_id, image_path, cert_data) from clean generation
        base_output_dir: Base directory for test fixtures
        distortion_presets: Dictionary of distortion configurations

    Returns:
        Count of generated variants
    """
    from PIL import Image

    count = 0

    # Group presets by output directory
    preset_groups = {
        "skewed": ["skew_05", "skew_10"],
        "degraded": ["blur_1", "blur_2", "lowdpi_150", "jpeg_40", "noise"],
        "scanned": ["scanned"],
    }

    for group_name, preset_names in preset_groups.items():
        output_dir = base_output_dir / group_name
        output_dir.mkdir(parents=True, exist_ok=True)

        for preset_name in preset_names:
            if preset_name not in distortion_presets:
                print(f"  Warning: Unknown preset '{preset_name}', skipping")
                continue

            preset = distortion_presets[preset_name]

            for cert_id, image_path, cert_data in clean_certs:
                # Load clean image
                image = Image.open(image_path)

                # Apply distortion
                distorted = preset["func"](image, **preset["params"])

                # Generate variant ID
                variant_id = f"{cert_id}_{preset_name}"

                # Save distorted image
                variant_image_path = output_dir / f"{variant_id}.png"

                # Convert to RGB if needed (some distortions may change mode)
                if distorted.mode == "RGBA":
                    distorted = distorted.convert("RGB")

                distorted.save(variant_image_path, "PNG")

                # Save ground truth (same expected values, different threshold)
                variant_json_path = output_dir / f"{variant_id}.json"
                save_ground_truth(
                    cert_data,
                    variant_json_path,
                    variant_id,
                    distortions=[preset_name],
                    accuracy_threshold=preset["accuracy_threshold"],
                )

                count += 1

        print(f"  Generated {group_name}/ variants: {len(preset_names) * len(clean_certs)} images")

    return count


def main():
    parser = argparse.ArgumentParser(
        description="Generate OCR test certificates with ground truth labels"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Base output directory for test fixtures",
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="Only generate clean certificates (no distortions)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of base certificates to generate (default: 10)",
    )

    args = parser.parse_args()

    print(f"Generating OCR test certificates...")
    print(f"Output directory: {args.output_dir}")
    print()

    # Limit certificates to requested count
    certificates = SAMPLE_CERTIFICATES[: args.count]

    # Generate clean certificates
    print(f"Phase 1: Generating {len(certificates)} clean certificates...")
    clean_dir = args.output_dir / "clean"
    clean_certs = generate_clean_certificates(certificates, clean_dir)
    print(f"  Total clean: {len(clean_certs)}")
    print()

    if args.clean_only:
        print("Clean-only mode, skipping distortions.")
        total = len(clean_certs)
    else:
        # Generate distorted variants
        print("Phase 2: Generating distorted variants...")
        variant_count = generate_distorted_variants(
            clean_certs,
            args.output_dir,
            DISTORTION_PRESETS,
        )
        total = len(clean_certs) + variant_count
        print()

    print(f"Generation complete!")
    print(f"Total images generated: {total}")
    print(f"Total JSON labels: {total}")

    # Verify output
    png_count = len(list(args.output_dir.rglob("*.png")))
    json_count = len(list(args.output_dir.rglob("*.json")))
    print(f"\nVerification:")
    print(f"  PNG files found: {png_count}")
    print(f"  JSON files found: {json_count}")

    if png_count != json_count:
        print("  WARNING: PNG and JSON counts don't match!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
