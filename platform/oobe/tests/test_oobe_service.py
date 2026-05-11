from __future__ import annotations

import json
from pathlib import Path

import pytest


def valid_payload() -> dict:
    return {
        "user": {"name": "Kryos User", "username": "kryos_user", "avatar": "avatar-1"},
        "ai": {"model": "llama3-8b", "allow_cloud": False},
        "locale": {"timezone": "UTC", "language": "English", "keyboard": "US"},
    }


@pytest.mark.asyncio
async def test_status_returns_false_before_complete(client) -> None:
    resp = await client.get("/api/oobe/status")
    assert resp.status_code == 200
    assert resp.json() == {"complete": False}


@pytest.mark.asyncio
async def test_oobe_complete_writes_file(client) -> None:
    resp = await client.post("/api/oobe/complete", json=valid_payload())
    assert resp.status_code == 200

    from oobe_service import USER_CONFIG_PATH

    assert USER_CONFIG_PATH.exists()
    payload = json.loads(USER_CONFIG_PATH.read_text(encoding="utf-8"))
    assert payload["user"]["username"] == "kryos_user"


@pytest.mark.asyncio
async def test_status_returns_true_after_complete(client) -> None:
    await client.post("/api/oobe/complete", json=valid_payload())
    resp = await client.get("/api/oobe/status")
    assert resp.status_code == 200
    assert resp.json() == {"complete": True}


@pytest.mark.asyncio
async def test_payload_validation_username(client) -> None:
    payload = valid_payload()
    payload["user"]["username"] = "Invalid-Name"
    resp = await client.post("/api/oobe/complete", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_422_on_bad_data(client) -> None:
    resp = await client.post("/api/oobe/complete", json={"bad": "payload"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_oobe_route_serves_index(client) -> None:
    resp = await client.get("/oobe")
    assert resp.status_code == 200
    assert "oobe" in resp.text
