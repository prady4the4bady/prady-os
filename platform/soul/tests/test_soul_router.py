"""Tests for platform/soul/router.py"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from soul.router import router


@pytest.fixture
def client(tmp_path, monkeypatch):
    import soul.soul_manager as sm
    monkeypatch.setattr(sm, "SOUL_DATA_ROOT", tmp_path)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_soul_default(client):
    resp = client.get("/soul/test-user")
    assert resp.status_code == 200
    data = resp.json()
    assert "fields" in data
    assert "name" in data["fields"]


def test_put_soul_update(client):
    resp = client.put("/soul/test-user", json={"name": "Kryos"})
    assert resp.status_code == 200
    # verify via GET
    resp2 = client.get("/soul/test-user")
    assert resp2.json()["fields"]["name"] == "Kryos"


def test_put_soul_partial_update(client):
    client.put("/soul/test-user", json={"name": "First"})
    client.put("/soul/test-user", json={"personality": "curious"})
    resp = client.get("/soul/test-user")
    data = resp.json()
    assert data["fields"]["name"] == "First"
    assert data["fields"]["personality"] == "curious"


def test_post_memory(client):
    resp = client.post(
        "/soul/test-user/memory",
        json={"interaction": "hello world"},
    )
    assert resp.status_code == 200
    # router returns {"user_id": ..., "content": ...} — no "ok" key
    assert "user_id" in resp.json()


def test_get_soul_after_memory(client):
    client.post(
        "/soul/test-user2/memory",
        json={"interaction": "world message"},
    )
    resp = client.get("/soul/test-user2")
    data = resp.json()
    import json
    memories_raw = data["fields"].get("memory_summary", "[]")
    memories = json.loads(memories_raw) if isinstance(memories_raw, str) else memories_raw
    assert len(memories) >= 1
