"""
Redis-based OCR client for communicating with OcrEngine worker.

Sends OCR requests via Redis queue and waits for results.
"""

import base64
import json
import uuid

import redis

from shared.models import PageImage, TextSpan


class RedisOcrClient:
    """
    OCR client that communicates with OcrEngine via Redis.

    Sends OCR requests to the 'ocr_tasks' queue and waits for
    results on 'ocr_results:{request_id}' keys.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        timeout: float = 30.0,
    ):
        """
        Initialize OCR client.

        Args:
            redis_client: Redis client instance
            timeout: Maximum time to wait for OCR result in seconds
        """
        self.redis = redis_client
        self.timeout = timeout

    def ocr_region(
        self,
        page_image: PageImage,
        bbox_norm: tuple[float, float, float, float],
    ) -> list[TextSpan]:
        """
        Send OCR request for a region and wait for result.

        Args:
            page_image: Page image to process
            bbox_norm: Normalized bounding box (x0, y0, x1, y1) in 0-1 range

        Returns:
            List of TextSpan objects from OCR

        Raises:
            TimeoutError: If OCR takes longer than timeout
            RuntimeError: If OCR fails
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Serialize request
        request_data = self._serialize_request(request_id, page_image, bbox_norm)

        # Push to OCR tasks queue
        self.redis.rpush("ocr_tasks", request_data)

        # Wait for result on response key
        result_key = f"ocr_results:{request_id}"

        # Block-wait with polling (BLPOP doesn't work well with SET keys)
        # OcrEngine uses SETEX, so we need to GET with polling
        import time
        start_time = time.time()
        while True:
            result_data = self.redis.get(result_key)
            if result_data:
                # Delete the result key after reading
                self.redis.delete(result_key)
                return self._deserialize_result(result_data)

            # Check timeout
            elapsed = time.time() - start_time
            if elapsed >= self.timeout:
                raise TimeoutError(
                    f"OCR request {request_id} timed out after {self.timeout}s"
                )

            # Small sleep before polling again
            time.sleep(0.1)

    async def ocr_region_async(
        self,
        page_image: PageImage,
        bbox_norm: tuple[float, float, float, float],
    ) -> list[TextSpan]:
        """
        Async version of ocr_region.

        Uses asyncio.sleep for non-blocking polling.

        Args:
            page_image: Page image to process
            bbox_norm: Normalized bounding box

        Returns:
            List of TextSpan objects from OCR
        """
        import asyncio

        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Serialize request
        request_data = self._serialize_request(request_id, page_image, bbox_norm)

        # Push to OCR tasks queue
        self.redis.rpush("ocr_tasks", request_data)

        # Wait for result with async polling
        result_key = f"ocr_results:{request_id}"

        start_time = asyncio.get_event_loop().time()
        while True:
            result_data = self.redis.get(result_key)
            if result_data:
                # Delete the result key after reading
                self.redis.delete(result_key)
                return self._deserialize_result(result_data)

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= self.timeout:
                raise TimeoutError(
                    f"OCR request {request_id} timed out after {self.timeout}s"
                )

            # Async sleep before polling again
            await asyncio.sleep(0.1)

    def _serialize_request(
        self,
        request_id: str,
        page_image: PageImage,
        bbox_norm: tuple[float, float, float, float],
    ) -> bytes:
        """
        Serialize OCR request for Redis queue.

        Args:
            request_id: Unique request identifier
            page_image: Page image
            bbox_norm: Region bounding box

        Returns:
            JSON bytes
        """
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

    def _deserialize_result(self, data: bytes) -> list[TextSpan]:
        """
        Deserialize OCR result from Redis.

        Args:
            data: JSON bytes from Redis

        Returns:
            List of TextSpan objects
        """
        parsed = json.loads(data.decode('utf-8'))

        text_spans = [
            TextSpan(
                text=s["text"],
                bbox_norm=tuple(s["bbox_norm"]),
                confidence=s["confidence"],
            )
            for s in parsed.get("spans", [])
        ]

        return text_spans
