#!/usr/bin/env python3
"""
Check prerequisites for OCR worker queue/recovery tests.

Profiles:
- tesseract (default): baseline dependencies required for required CI lane
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path


REQUIRED_TEST_MODULES = (
    "redis",
    "structlog",
    "PIL",
    "pytesseract",
)


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _can_import_shared_models(repo_root: Path) -> tuple[bool, str]:
    api_src = repo_root / "CoreInstances" / "ApiServer" / "src"
    if not api_src.exists():
        return False, f"missing path: {api_src}"

    sys.path.insert(0, str(api_src))
    try:
        __import__("shared.models")
        return True, ""
    except Exception as exc:  # pragma: no cover - defensive runtime detail
        return False, str(exc)
    finally:
        try:
            sys.path.remove(str(api_src))
        except ValueError:
            pass


def _can_import_ocr_service(repo_root: Path) -> tuple[bool, str]:
    ocr_src = repo_root / "BackgroundProcessingInstances" / "OcrEngine" / "src"
    if not ocr_src.exists():
        return False, f"missing path: {ocr_src}"

    sys.path.insert(0, str(ocr_src))
    try:
        __import__("ocr_service")
        return True, ""
    except Exception as exc:  # pragma: no cover - defensive runtime detail
        return False, str(exc)
    finally:
        try:
            sys.path.remove(str(ocr_src))
        except ValueError:
            pass


def _check_tesseract_binary() -> tuple[bool, str]:
    if not shutil.which("tesseract"):
        return False, "tesseract binary not found in PATH"
    result = subprocess.run(
        ["tesseract", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return False, "tesseract --version failed"
    return True, ""


def run_check(profile: str, repo_root: Path) -> dict[str, object]:
    missing: list[dict[str, str]] = []

    for module_name in REQUIRED_TEST_MODULES:
        if not _module_available(module_name):
            missing.append(
                {
                    "type": "python_module",
                    "name": module_name,
                    "detail": "module not importable",
                }
            )

    ok_shared, shared_err = _can_import_shared_models(repo_root)
    if not ok_shared:
        missing.append(
            {
                "type": "python_import",
                "name": "shared.models",
                "detail": shared_err,
            }
        )

    ok_ocr_service, ocr_err = _can_import_ocr_service(repo_root)
    if not ok_ocr_service:
        missing.append(
            {
                "type": "python_import",
                "name": "ocr_service",
                "detail": ocr_err,
            }
        )

    if profile == "tesseract":
        ok_tess, tess_err = _check_tesseract_binary()
        if not ok_tess:
            missing.append(
                {
                    "type": "binary",
                    "name": "tesseract",
                    "detail": tess_err,
                }
            )

    return {
        "ok": len(missing) == 0,
        "profile": profile,
        "missing": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OCR test dependencies")
    parser.add_argument(
        "--profile",
        default="tesseract",
        choices=["tesseract"],
        help="dependency profile to validate",
    )
    parser.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="output format",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    result = run_check(args.profile, repo_root)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"OCR dependency check profile: {result['profile']}")
        if result["ok"]:
            print("status: ok")
        else:
            print("status: failed")
            print("missing prerequisites:")
            for item in result["missing"]:
                print(f"- [{item['type']}] {item['name']}: {item['detail']}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
