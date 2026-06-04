import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_readiness(client):
    resp = await client.get("/ready")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_search_requires_body(client):
    resp = await client.post("/api/v1/search/", json={})
    assert resp.status_code == 422  # validation error — query is required
