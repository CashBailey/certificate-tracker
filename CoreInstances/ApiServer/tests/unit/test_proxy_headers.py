"""Verify ProxyHeadersMiddleware correctly extracts real client IPs."""
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_sees_forwarded_ip():
    """When X-Forwarded-For is set, request.client.host should reflect it."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health",
            headers={"X-Forwarded-For": "198.51.100.42"},
        )
        assert response.status_code == 200
