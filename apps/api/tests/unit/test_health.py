import pytest

pytestmark = pytest.mark.asyncio


async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_liveness_returns_alive(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_readiness_returns_ready(client):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    # WP-03: readiness now carries per-dependency detail.
    assert response.json() == {"status": "ready", "checks": {"postgres": "ok", "redis": "ok"}}


async def test_request_id_header_is_echoed(client):
    response = await client.get("/health", headers={"x-request-id": "test-rid-123"})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == "test-rid-123"


async def test_request_id_header_generated_when_missing(client):
    response = await client.get("/health")
    assert response.headers.get("x-request-id")
