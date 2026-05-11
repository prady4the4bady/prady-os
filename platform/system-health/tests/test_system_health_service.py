from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_system_about(client) -> None:
    response = await client.get("/api/system/about")
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Prady OS"
    assert payload["version"]


@pytest.mark.asyncio
async def test_system_health(client) -> None:
    response = await client.get("/api/system/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["checks"]["oobe"] == "ok"
