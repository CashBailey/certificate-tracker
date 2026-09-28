"""Untrusted OCR queue messages are validated before native image processing."""

import base64
import json

import pytest

from src.ocr_service import (
    MAX_OCR_IMAGE_BYTES,
    deserialize_ocr_request,
)


def _request(**overrides) -> bytes:
    payload = {
        "request_id": "123e4567-e89b-12d3-a456-426614174000",
        "page_num": 0,
        "image_b64": base64.b64encode(b"image").decode(),
        "width_px": 100,
        "height_px": 100,
        "dpi": 300,
        "bbox_norm": [0.0, 0.0, 1.0, 1.0],
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


@pytest.mark.parametrize(
    "overrides",
    [
        {"request_id": "../result-key"},
        {"width_px": 100_000},
        {"height_px": 0},
        {"dpi": 10_000},
        {"bbox_norm": [-1.0, 0.0, 1.0, 1.0]},
        {"bbox_norm": [0.0, 0.0, float("nan"), 1.0]},
    ],
)
def test_invalid_request_metadata_is_rejected(overrides):
    with pytest.raises(ValueError):
        deserialize_ocr_request(_request(**overrides))


def test_invalid_base64_is_rejected():
    with pytest.raises(ValueError):
        deserialize_ocr_request(_request(image_b64="!!!not-base64!!!"))


def test_decoded_image_payload_is_bounded():
    encoded = base64.b64encode(b"x" * (MAX_OCR_IMAGE_BYTES + 1)).decode()

    with pytest.raises(ValueError, match="payload exceeds"):
        deserialize_ocr_request(_request(image_b64=encoded))


def test_valid_request_is_deserialized():
    request_id, page, bbox = deserialize_ocr_request(_request())

    assert request_id.startswith("123e4567")
    assert page.width_px == 100
    assert bbox == (0.0, 0.0, 1.0, 1.0)
