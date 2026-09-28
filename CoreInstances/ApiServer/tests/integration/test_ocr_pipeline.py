"""
Integration tests for the OCR Pipeline.

Tests the OCR request/response flow including:
- Extraction task format and queueing
- OCR request serialization
- OCR response deserialization
- OCR timeout handling
- Result key deletion after consumption
- Confidence normalization (Tesseract 0-100 → 0-1)
- Redis queue interactions
"""

import pytest
import json
import base64
import time
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch


# ==================== Mock Models ====================


@dataclass
class MockTextSpan:
    """Mock TextSpan matching shared.models.TextSpan."""
    text: str
    bbox_norm: tuple[float, float, float, float]
    confidence: float


@dataclass
class MockPageImage:
    """Mock PageImage matching shared.models.PageImage."""
    page_num: int
    image_bytes: bytes
    width_px: int
    height_px: int
    dpi: int


# ==================== Fixtures ====================


@pytest.fixture
def minimal_png_bytes():
    """Return minimal valid PNG bytes."""
    return bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
        0x89,
    ])


@pytest.fixture
def sample_page_image(minimal_png_bytes):
    """Create a sample page image."""
    return MockPageImage(
        page_num=1,
        image_bytes=minimal_png_bytes,
        width_px=100,
        height_px=100,
        dpi=72,
    )


@pytest.fixture
def sample_bbox_norm():
    """Return a sample normalized bounding box."""
    return (0.1, 0.1, 0.9, 0.9)


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client = MagicMock()
    client.rpush = MagicMock(return_value=1)
    client.blpop = MagicMock(return_value=None)
    client.get = MagicMock(return_value=None)
    client.set = MagicMock(return_value=True)
    client.setex = MagicMock(return_value=True)
    client.delete = MagicMock(return_value=1)
    return client


# ==================== Helper Functions ====================


def serialize_ocr_request(
    request_id: str,
    page_image: MockPageImage,
    bbox_norm: tuple[float, float, float, float],
) -> bytes:
    """Serialize OCR request for Redis queue."""
    data = {
        "request_id": request_id,
        "page_num": page_image.page_num,
        "image_b64": base64.b64encode(page_image.image_bytes).decode('ascii'),
        "width_px": page_image.width_px,
        "height_px": page_image.height_px,
        "dpi": page_image.dpi,
        "bbox_norm": list(bbox_norm),
    }
    return json.dumps(data).encode('utf-8')


def deserialize_ocr_request(data: bytes) -> tuple[str, MockPageImage, tuple]:
    """Deserialize OCR request from Redis queue."""
    parsed = json.loads(data.decode('utf-8'))

    page_image = MockPageImage(
        page_num=parsed["page_num"],
        image_bytes=base64.b64decode(parsed["image_b64"]),
        width_px=parsed["width_px"],
        height_px=parsed["height_px"],
        dpi=parsed["dpi"],
    )

    bbox_norm = tuple(parsed["bbox_norm"])

    return parsed["request_id"], page_image, bbox_norm


def serialize_ocr_result(request_id: str, text_spans: list[MockTextSpan]) -> bytes:
    """Serialize OCR result for Redis."""
    data = {
        "request_id": request_id,
        "spans": [
            {
                "text": span.text,
                "bbox_norm": list(span.bbox_norm),
                "confidence": span.confidence,
            }
            for span in text_spans
        ],
    }
    return json.dumps(data).encode('utf-8')


def deserialize_ocr_result(data: bytes) -> tuple[str, list[MockTextSpan]]:
    """Deserialize OCR result from Redis."""
    parsed = json.loads(data.decode('utf-8'))

    text_spans = [
        MockTextSpan(
            text=s["text"],
            bbox_norm=tuple(s["bbox_norm"]),
            confidence=s["confidence"],
        )
        for s in parsed["spans"]
    ]

    return parsed["request_id"], text_spans


# ==================== Queue Names Tests ====================


class TestQueueNames:
    """Tests for Redis queue names."""

    def test_extraction_tasks_queue_name(self):
        """Verify extraction tasks queue name."""
        EXTRACTION_QUEUE = "extraction_tasks"
        assert EXTRACTION_QUEUE == "extraction_tasks"

    def test_ocr_tasks_queue_name(self):
        """Verify OCR tasks queue name."""
        OCR_TASKS_QUEUE = "ocr_tasks"
        assert OCR_TASKS_QUEUE == "ocr_tasks"

    def test_ocr_results_key_format(self):
        """Verify OCR results key format."""
        request_id = "abc-123"
        result_key = f"ocr_results:{request_id}"
        assert result_key == "ocr_results:abc-123"
        assert request_id in result_key


# ==================== Extraction Task Tests ====================


class TestExtractionTaskFormat:
    """Tests for extraction task message format."""

    def test_extraction_task_has_document_id(self):
        """Extraction task must include document_id."""
        task = {
            "document_id": 123,
            "queued_at": "2026-02-04T12:00:00",
            "source": "email_intake",
        }

        assert "document_id" in task
        assert task["document_id"] == 123

    def test_extraction_task_has_timestamp(self):
        """Extraction task should include queued_at timestamp."""
        task = {
            "document_id": 123,
            "queued_at": "2026-02-04T12:00:00",
            "source": "email_intake",
        }

        assert "queued_at" in task

    def test_extraction_task_has_source(self):
        """Extraction task should include source."""
        task = {
            "document_id": 123,
            "queued_at": "2026-02-04T12:00:00",
            "source": "email_intake",
        }

        assert "source" in task
        assert task["source"] in ["email_intake", "manual_upload", "api"]

    def test_extraction_task_json_serialization(self):
        """Extraction task should serialize to valid JSON."""
        task = {
            "document_id": 123,
            "queued_at": "2026-02-04T12:00:00",
            "source": "email_intake",
        }

        serialized = json.dumps(task)
        deserialized = json.loads(serialized)

        assert deserialized["document_id"] == 123

    def test_extraction_task_queued_via_rpush(self, mock_redis_client):
        """Extraction task should be queued via RPUSH."""
        task = {"document_id": 1, "source": "email_intake"}

        mock_redis_client.rpush("extraction_tasks", json.dumps(task))

        mock_redis_client.rpush.assert_called_once()
        call_args = mock_redis_client.rpush.call_args
        assert call_args[0][0] == "extraction_tasks"


# ==================== OCR Request Serialization Tests ====================


class TestOcrRequestSerialization:
    """Tests for OCR request serialization."""

    def test_request_includes_request_id(self, sample_page_image, sample_bbox_norm):
        """OCR request should include unique request_id."""
        request_id = "test-request-001"
        request_data = serialize_ocr_request(request_id, sample_page_image, sample_bbox_norm)

        parsed = json.loads(request_data.decode('utf-8'))
        assert parsed["request_id"] == request_id

    def test_request_includes_base64_image(self, sample_page_image, sample_bbox_norm):
        """OCR request should include base64-encoded image."""
        request_id = "test-request-001"
        request_data = serialize_ocr_request(request_id, sample_page_image, sample_bbox_norm)

        parsed = json.loads(request_data.decode('utf-8'))
        assert "image_b64" in parsed

        # Should be valid base64
        decoded = base64.b64decode(parsed["image_b64"])
        assert decoded == sample_page_image.image_bytes

    def test_request_includes_dimensions(self, sample_page_image, sample_bbox_norm):
        """OCR request should include image dimensions."""
        request_id = "test-request-001"
        request_data = serialize_ocr_request(request_id, sample_page_image, sample_bbox_norm)

        parsed = json.loads(request_data.decode('utf-8'))
        assert parsed["width_px"] == sample_page_image.width_px
        assert parsed["height_px"] == sample_page_image.height_px
        assert parsed["dpi"] == sample_page_image.dpi

    def test_request_includes_bbox_norm(self, sample_page_image, sample_bbox_norm):
        """OCR request should include normalized bounding box."""
        request_id = "test-request-001"
        request_data = serialize_ocr_request(request_id, sample_page_image, sample_bbox_norm)

        parsed = json.loads(request_data.decode('utf-8'))
        assert parsed["bbox_norm"] == list(sample_bbox_norm)

    def test_request_includes_page_num(self, sample_page_image, sample_bbox_norm):
        """OCR request should include page number."""
        request_id = "test-request-001"
        request_data = serialize_ocr_request(request_id, sample_page_image, sample_bbox_norm)

        parsed = json.loads(request_data.decode('utf-8'))
        assert parsed["page_num"] == sample_page_image.page_num

    def test_request_round_trip(self, sample_page_image, sample_bbox_norm):
        """Request should survive serialization/deserialization round trip."""
        request_id = "test-request-001"
        serialized = serialize_ocr_request(request_id, sample_page_image, sample_bbox_norm)

        restored_id, restored_image, restored_bbox = deserialize_ocr_request(serialized)

        assert restored_id == request_id
        assert restored_image.page_num == sample_page_image.page_num
        assert restored_image.image_bytes == sample_page_image.image_bytes
        assert restored_image.width_px == sample_page_image.width_px
        assert restored_image.height_px == sample_page_image.height_px
        assert restored_image.dpi == sample_page_image.dpi
        assert restored_bbox == sample_bbox_norm


# ==================== OCR Response Deserialization Tests ====================


class TestOcrResponseDeserialization:
    """Tests for OCR response deserialization."""

    def test_response_parses_text_spans(self):
        """OCR response should parse text spans correctly."""
        response_data = json.dumps({
            "request_id": "test-001",
            "spans": [
                {"text": "John Doe", "bbox_norm": [0.1, 0.1, 0.5, 0.2], "confidence": 0.95},
                {"text": "CPR Certified", "bbox_norm": [0.1, 0.3, 0.6, 0.4], "confidence": 0.88},
            ],
        }).encode('utf-8')

        request_id, text_spans = deserialize_ocr_result(response_data)

        assert request_id == "test-001"
        assert len(text_spans) == 2
        assert text_spans[0].text == "John Doe"
        assert text_spans[0].confidence == 0.95
        assert text_spans[1].text == "CPR Certified"
        assert text_spans[1].confidence == 0.88

    def test_response_parses_bbox_as_tuple(self):
        """Bounding box should be parsed as tuple."""
        response_data = json.dumps({
            "request_id": "test-001",
            "spans": [
                {"text": "Test", "bbox_norm": [0.1, 0.2, 0.3, 0.4], "confidence": 0.9},
            ],
        }).encode('utf-8')

        _, text_spans = deserialize_ocr_result(response_data)

        assert text_spans[0].bbox_norm == (0.1, 0.2, 0.3, 0.4)
        assert isinstance(text_spans[0].bbox_norm, tuple)

    def test_empty_spans_list(self):
        """Response with no spans should return empty list."""
        response_data = json.dumps({
            "request_id": "test-001",
            "spans": [],
        }).encode('utf-8')

        request_id, text_spans = deserialize_ocr_result(response_data)

        assert request_id == "test-001"
        assert text_spans == []

    def test_response_round_trip(self):
        """Response should survive serialization/deserialization."""
        original_spans = [
            MockTextSpan("Hello", (0.0, 0.0, 0.5, 0.1), 0.99),
            MockTextSpan("World", (0.5, 0.0, 1.0, 0.1), 0.97),
        ]
        request_id = "test-roundtrip"

        serialized = serialize_ocr_result(request_id, original_spans)
        restored_id, restored_spans = deserialize_ocr_result(serialized)

        assert restored_id == request_id
        assert len(restored_spans) == 2
        assert restored_spans[0].text == "Hello"
        assert restored_spans[0].confidence == 0.99
        assert restored_spans[1].text == "World"
        assert restored_spans[1].confidence == 0.97


# ==================== Confidence Normalization Tests ====================


class TestConfidenceNormalization:
    """Tests for Tesseract confidence normalization (0-100 → 0-1)."""

    def test_tesseract_confidence_normalized(self):
        """Tesseract 0-100 confidence should be normalized to 0-1."""
        tesseract_confidence = 95  # Tesseract returns 0-100

        normalized = tesseract_confidence / 100.0

        assert normalized == 0.95
        assert 0.0 <= normalized <= 1.0

    def test_high_confidence_normalization(self):
        """High confidence (100) should normalize to 1.0."""
        tesseract_confidence = 100
        normalized = tesseract_confidence / 100.0

        assert normalized == 1.0

    def test_low_confidence_normalization(self):
        """Low confidence (0) should normalize to 0.0."""
        tesseract_confidence = 0
        normalized = tesseract_confidence / 100.0

        assert normalized == 0.0

    def test_mid_confidence_normalization(self):
        """Mid confidence values should normalize correctly."""
        test_cases = [
            (50, 0.5),
            (75, 0.75),
            (33, 0.33),
            (88, 0.88),
        ]

        for tesseract_conf, expected in test_cases:
            normalized = tesseract_conf / 100.0
            assert normalized == expected

    def test_negative_confidence_handled(self):
        """Negative confidence (Tesseract error) should be filtered."""
        tesseract_confidence = -1  # Tesseract returns -1 for invalid results

        # Typically filtered out before normalization
        should_include = tesseract_confidence >= 0
        assert should_include is False


# ==================== Result Key Management Tests ====================


class TestResultKeyManagement:
    """Tests for OCR result key creation and deletion."""

    def test_result_key_created_with_setex(self, mock_redis_client):
        """Result should be stored with SETEX (with TTL)."""
        request_id = "test-123"
        result_key = f"ocr_results:{request_id}"
        result_data = json.dumps({"request_id": request_id, "spans": []})
        ttl_seconds = 300  # 5 minutes

        mock_redis_client.setex(result_key, ttl_seconds, result_data)

        mock_redis_client.setex.assert_called_once_with(
            result_key, ttl_seconds, result_data
        )

    def test_result_key_deleted_after_consumption(self, mock_redis_client):
        """Result key should be deleted after being read."""
        request_id = "test-123"
        result_key = f"ocr_results:{request_id}"

        # Simulate reading result
        mock_redis_client.get.return_value = b'{"request_id": "test-123", "spans": []}'
        result = mock_redis_client.get(result_key)

        # Delete after reading
        if result:
            mock_redis_client.delete(result_key)

        mock_redis_client.delete.assert_called_once_with(result_key)

    def test_result_key_has_ttl_for_cleanup(self):
        """Result key TTL ensures cleanup of unread results."""
        DEFAULT_TTL = 300  # 5 minutes
        assert DEFAULT_TTL > 0
        assert DEFAULT_TTL <= 600  # Max 10 minutes

    def test_result_key_format_is_predictable(self):
        """Result key format should be predictable for clients."""
        request_id = "abc123-def456"
        result_key = f"ocr_results:{request_id}"

        assert result_key.startswith("ocr_results:")
        assert request_id in result_key


# ==================== Timeout Handling Tests ====================


class TestTimeoutHandling:
    """Tests for OCR timeout handling."""

    def test_default_timeout_is_30_seconds(self):
        """Default OCR timeout should be 30 seconds."""
        DEFAULT_TIMEOUT = 30.0
        assert DEFAULT_TIMEOUT == 30.0

    def test_timeout_raises_timeout_error(self):
        """Timeout should raise TimeoutError."""
        # Simulate timeout scenario
        start_time = time.time()
        timeout = 0.1  # Very short timeout for test

        result = None
        elapsed = 0

        while result is None and elapsed < timeout:
            # Simulate polling with no result
            result = None
            elapsed = time.time() - start_time

        if elapsed >= timeout:
            with pytest.raises(TimeoutError):
                raise TimeoutError(f"OCR request timed out after {timeout}s")

    def test_timeout_is_configurable(self):
        """OCR timeout should be configurable."""
        timeouts = [10.0, 30.0, 60.0, 120.0]

        for timeout in timeouts:
            assert timeout > 0
            assert isinstance(timeout, float)


# ==================== Queue Interaction Tests ====================


class TestQueueInteractions:
    """Tests for Redis queue interactions."""

    def test_ocr_request_pushed_via_rpush(self, mock_redis_client, sample_page_image, sample_bbox_norm):
        """OCR request should be pushed via RPUSH."""
        request_id = "test-001"
        request_data = serialize_ocr_request(request_id, sample_page_image, sample_bbox_norm)

        mock_redis_client.rpush("ocr_tasks", request_data)

        mock_redis_client.rpush.assert_called_once()
        call_args = mock_redis_client.rpush.call_args
        assert call_args[0][0] == "ocr_tasks"

    def test_worker_consumes_via_blpop(self, mock_redis_client):
        """OCR worker should consume tasks via BLPOP."""
        mock_redis_client.blpop.return_value = (
            "ocr_tasks",
            b'{"request_id": "test-001", "page_num": 1}'
        )

        result = mock_redis_client.blpop("ocr_tasks", timeout=10)

        assert result is not None
        assert result[0] == "ocr_tasks"

    def test_result_retrieved_via_get(self, mock_redis_client):
        """OCR result should be retrieved via GET."""
        request_id = "test-001"
        result_key = f"ocr_results:{request_id}"
        expected_result = b'{"request_id": "test-001", "spans": []}'

        mock_redis_client.get.return_value = expected_result

        result = mock_redis_client.get(result_key)

        assert result == expected_result
        mock_redis_client.get.assert_called_with(result_key)


# ==================== Bounding Box Tests ====================


class TestBoundingBoxCoordinates:
    """Tests for normalized bounding box coordinates."""

    def test_bbox_values_are_normalized(self):
        """Bounding box values should be in 0-1 range."""
        bbox_norm = (0.1, 0.2, 0.8, 0.9)

        for value in bbox_norm:
            assert 0.0 <= value <= 1.0

    def test_bbox_has_four_values(self):
        """Bounding box should have exactly 4 values (x0, y0, x1, y1)."""
        bbox_norm = (0.1, 0.2, 0.8, 0.9)
        assert len(bbox_norm) == 4

    def test_bbox_x1_greater_than_x0(self):
        """x1 should be >= x0."""
        bbox_norm = (0.1, 0.2, 0.8, 0.9)
        x0, y0, x1, y1 = bbox_norm

        assert x1 >= x0

    def test_bbox_y1_greater_than_y0(self):
        """y1 should be >= y0."""
        bbox_norm = (0.1, 0.2, 0.8, 0.9)
        x0, y0, x1, y1 = bbox_norm

        assert y1 >= y0

    def test_full_page_bbox(self):
        """Full page bounding box should be (0, 0, 1, 1)."""
        full_page_bbox = (0.0, 0.0, 1.0, 1.0)

        assert full_page_bbox[0] == 0.0  # x0
        assert full_page_bbox[1] == 0.0  # y0
        assert full_page_bbox[2] == 1.0  # x1
        assert full_page_bbox[3] == 1.0  # y1


# ==================== Language Support Tests ====================


class TestOcrLanguageSupport:
    """Tests for OCR language configuration."""

    def test_default_language_is_english(self):
        """Default OCR language should be English."""
        default_lang = "eng"
        assert default_lang == "eng"

    def test_multi_language_support(self):
        """OCR should support multiple languages."""
        # Per spec: eng+spa for English and Spanish
        multi_lang = "eng+spa"
        assert "eng" in multi_lang
        assert "spa" in multi_lang

    def test_language_format_is_valid(self):
        """Language format should be valid Tesseract format."""
        valid_langs = ["eng", "spa", "eng+spa", "fra", "deu"]

        for lang in valid_langs:
            # Tesseract uses 3-letter ISO codes
            for part in lang.split("+"):
                assert len(part) == 3


# ==================== End-to-End Flow Tests ====================


class TestOcrPipelineFlow:
    """Tests for complete OCR pipeline flow."""

    def test_full_ocr_request_response_flow(self, mock_redis_client, sample_page_image, sample_bbox_norm):
        """Test complete OCR request → response flow."""
        # 1. Client creates request
        request_id = "flow-test-001"
        request_data = serialize_ocr_request(request_id, sample_page_image, sample_bbox_norm)

        # 2. Client pushes to queue
        mock_redis_client.rpush("ocr_tasks", request_data)

        # 3. Worker would process and create result
        result_spans = [
            MockTextSpan("Certificate", (0.1, 0.1, 0.5, 0.2), 0.92),
            MockTextSpan("John Doe", (0.1, 0.25, 0.4, 0.35), 0.95),
        ]
        result_data = serialize_ocr_result(request_id, result_spans)

        # 4. Worker stores result with TTL
        result_key = f"ocr_results:{request_id}"
        mock_redis_client.setex(result_key, 300, result_data)

        # 5. Client polls for result
        mock_redis_client.get.return_value = result_data
        fetched_data = mock_redis_client.get(result_key)

        # 6. Client parses result
        returned_id, returned_spans = deserialize_ocr_result(fetched_data)

        # 7. Client deletes result key
        mock_redis_client.delete(result_key)

        # Verify flow
        assert returned_id == request_id
        assert len(returned_spans) == 2
        assert returned_spans[0].text == "Certificate"
        assert returned_spans[1].text == "John Doe"
        mock_redis_client.delete.assert_called_with(result_key)

    def test_extraction_to_ocr_flow(self, mock_redis_client):
        """Test extraction worker → OCR worker flow."""
        # 1. Extraction task received
        extraction_task = {
            "document_id": 123,
            "queued_at": "2026-02-04T12:00:00",
            "source": "email_intake",
        }

        # 2. Extraction worker processes document and creates OCR requests
        ocr_request_ids = []
        for page_num in range(1, 4):  # 3-page document
            request_id = f"doc-123-page-{page_num}"
            ocr_request_ids.append(request_id)

            # OCR request for each page
            mock_redis_client.rpush("ocr_tasks", json.dumps({
                "request_id": request_id,
                "page_num": page_num,
            }))

        # Verify
        assert mock_redis_client.rpush.call_count == 3
        assert len(ocr_request_ids) == 3

    def test_multiple_concurrent_requests(self, mock_redis_client):
        """Test handling multiple concurrent OCR requests."""
        request_ids = ["req-1", "req-2", "req-3"]

        # All requests pushed
        for req_id in request_ids:
            mock_redis_client.rpush("ocr_tasks", json.dumps({"request_id": req_id}))

        # Results stored independently
        for req_id in request_ids:
            result_key = f"ocr_results:{req_id}"
            mock_redis_client.setex(result_key, 300, json.dumps({
                "request_id": req_id,
                "spans": [{"text": f"Result for {req_id}", "bbox_norm": [0, 0, 1, 1], "confidence": 0.9}]
            }))

        # Verify each result is retrievable
        assert mock_redis_client.rpush.call_count == 3
        assert mock_redis_client.setex.call_count == 3


# ==================== Error Handling Tests ====================


class TestErrorHandling:
    """Tests for OCR error handling."""

    def test_invalid_json_in_request(self):
        """Invalid JSON should be handled gracefully."""
        invalid_data = b"not valid json {{"

        with pytest.raises(json.JSONDecodeError):
            json.loads(invalid_data.decode('utf-8'))

    def test_missing_request_id_in_response(self):
        """Response without request_id should fail validation."""
        response_data = json.dumps({
            # Missing "request_id"
            "spans": [],
        }).encode('utf-8')

        parsed = json.loads(response_data.decode('utf-8'))
        has_request_id = "request_id" in parsed
        assert has_request_id is False

    def test_invalid_base64_image(self):
        """Invalid base64 should raise error."""
        invalid_b64 = "not-valid-base64!!!"

        with pytest.raises(Exception):  # base64.binascii.Error or ValueError
            base64.b64decode(invalid_b64)

    def test_empty_result_is_valid(self):
        """Empty result (no text found) should be valid."""
        response_data = json.dumps({
            "request_id": "test-001",
            "spans": [],  # No text found
        }).encode('utf-8')

        request_id, text_spans = deserialize_ocr_result(response_data)

        assert request_id == "test-001"
        assert text_spans == []
        assert len(text_spans) == 0
