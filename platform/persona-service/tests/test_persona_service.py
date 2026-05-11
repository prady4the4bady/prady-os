from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


REPO_ROOT = Path(__file__).parents[3]
SERVICE_DIR = REPO_ROOT / "platform" / "persona-service"
sys.path.insert(0, str(SERVICE_DIR))

import persona_service as ps
from persona_service import app

TRANSPORT = ASGITransport(app=app)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._payload


@pytest_asyncio.fixture(autouse=True)
async def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ps, "DB_PATH", tmp_path / "persona.db")
    await ps._init_db()


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_persona_plural_endpoint():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/personas",
            json={
                "name": "Planner",
                "avatar_color": "#0A84FF",
                "system_prompt": "You are a planning specialist.",
                "preferred_model_id": "qwen3-30b-a3b-q4",
                "memory_policy": "balanced",
                "tags": ["planning"],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Planner"
    assert body["preferred_model_id"] == "qwen3-30b-a3b-q4"


@pytest.mark.asyncio
async def test_create_duplicate_name_conflict():
    payload = {
        "name": "Analyst",
        "avatar_color": "#34C759",
        "system_prompt": "You provide analysis and risk checks.",
        "preferred_model_id": "qwen3-30b-a3b-q4",
        "memory_policy": "balanced",
        "tags": ["work"],
    }
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        first = await ac.post("/personas", json=payload)
        second = await ac.post("/personas", json=payload)
    assert first.status_code == 200
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_list_personas():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post(
            "/personas",
            json={
                "name": "Alpha",
                "avatar_color": "#0A84FF",
                "system_prompt": "You are persona A.",
                "preferred_model_id": "m-a",
                "memory_policy": "balanced",
                "tags": [],
            },
        )
        await ac.post(
            "/personas",
            json={
                "name": "Beta",
                "avatar_color": "#30D158",
                "system_prompt": "You are persona B.",
                "preferred_model_id": "m-b",
                "memory_policy": "minimal",
                "tags": ["x"],
            },
        )
        listed = await ac.get("/personas")
    assert listed.status_code == 200
    assert listed.json()["total"] == 2


@pytest.mark.asyncio
async def test_get_persona_by_id():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/personas",
            json={
                "name": "Navigator",
                "avatar_color": "#FF9F0A",
                "system_prompt": "Guide by priorities and deadlines.",
                "preferred_model_id": "m-nav",
                "memory_policy": "balanced",
                "tags": [],
            },
        )
        pid = created.json()["id"]
        got = await ac.get(f"/personas/{pid}")
    assert got.status_code == 200
    assert got.json()["id"] == pid


@pytest.mark.asyncio
async def test_patch_persona_fields():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/personas",
            json={
                "name": "Fixer",
                "avatar_color": "#5E5CE6",
                "system_prompt": "Old prompt text here.",
                "preferred_model_id": "old-model",
                "memory_policy": "balanced",
                "tags": ["legacy"],
            },
        )
        pid = created.json()["id"]
        patched = await ac.patch(
            f"/personas/{pid}",
            json={"system_prompt": "New prompt text.", "preferred_model_id": "new-model", "tags": ["new"]},
        )
    assert patched.status_code == 200
    body = patched.json()
    assert body["system_prompt"] == "New prompt text."
    assert body["preferred_model_id"] == "new-model"
    assert body["tags"] == ["new"]


@pytest.mark.asyncio
async def test_patch_persona_without_fields_400():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/personas",
            json={
                "name": "Patchless",
                "avatar_color": "#64D2FF",
                "system_prompt": "Patchless baseline prompt.",
                "preferred_model_id": "m-patch",
                "memory_policy": "balanced",
                "tags": [],
            },
        )
        pid = created.json()["id"]
        patched = await ac.patch(f"/personas/{pid}", json={})
    assert patched.status_code == 400


@pytest.mark.asyncio
async def test_clone_persona():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/personas",
            json={
                "name": "Original",
                "avatar_color": "#BF5AF2",
                "system_prompt": "Original prompt.",
                "preferred_model_id": "m-orig",
                "memory_policy": "aggressive",
                "tags": ["alpha"],
            },
        )
        pid = created.json()["id"]
        cloned = await ac.post(f"/personas/{pid}/clone")
    assert cloned.status_code == 200
    assert cloned.json()["name"].startswith("Copy of")


@pytest.mark.asyncio
async def test_activate_persona_ok_when_hot_swap_unavailable():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        p1 = await ac.post(
            "/personas",
            json={
                "name": "One",
                "avatar_color": "#0A84FF",
                "system_prompt": "Persona one system prompt.",
                "preferred_model_id": "m1",
                "memory_policy": "balanced",
                "tags": [],
            },
        )
        p2 = await ac.post(
            "/personas",
            json={
                "name": "Two",
                "avatar_color": "#34C759",
                "system_prompt": "Persona two system prompt.",
                "preferred_model_id": "m2",
                "memory_policy": "minimal",
                "tags": [],
            },
        )
        pid1 = p1.json()["id"]
        pid2 = p2.json()["id"]
        await ac.post(f"/personas/{pid1}/activate")
        activated = await ac.post(f"/personas/{pid2}/activate")
        active = await ac.get("/persona/active")
    assert activated.status_code == 200
    assert activated.json()["ok"] is True
    assert active.status_code == 200
    assert active.json()["active"]["id"] == pid2


@pytest.mark.asyncio
async def test_activate_missing_persona_404():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/personas/not-found/activate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_archive_persona_hides_from_list():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/personas",
            json={
                "name": "Drop",
                "avatar_color": "#FF375F",
                "system_prompt": "Archive me when done.",
                "preferred_model_id": "m-drop",
                "memory_policy": "minimal",
                "tags": [],
            },
        )
        pid = created.json()["id"]
        deleted = await ac.delete(f"/personas/{pid}")
        listed = await ac.get("/personas")
    assert deleted.status_code == 200
    assert all(p["id"] != pid for p in listed.json()["personas"])


@pytest.mark.asyncio
async def test_memory_summary_success(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str):
            await asyncio.sleep(0)
            if "/memories/by-persona/" in url:
                return FakeResponse(
                    200,
                    {
                        "memories": [
                            {"content": "alpha", "created_at": "2026-01-01T00:00:00Z"},
                            {"content": "beta", "created_at": "2026-02-01T00:00:00Z"},
                        ]
                    },
                )
            return FakeResponse(200, {"topics": [{"topic": "work", "count": 2}]})

        async def post(self, _url: str, json: dict | None = None):
            await asyncio.sleep(0)
            return FakeResponse(200, {"ok": True, "echo": json or {}})

    monkeypatch.setattr(ps.httpx, "AsyncClient", lambda timeout=10.0: FakeClient())

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/personas",
            json={
                "name": "Memory",
                "avatar_color": "#0A84FF",
                "system_prompt": "Memory summary persona prompt.",
                "preferred_model_id": "m-mem",
                "memory_policy": "balanced",
                "tags": [],
            },
        )
        pid = created.json()["id"]
        summary = await ac.get(f"/personas/{pid}/memory-summary")
    assert summary.status_code == 200
    assert summary.json()["total_memories"] == 2


@pytest.mark.asyncio
async def test_memory_summary_downstream_error(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, _url: str):
            await asyncio.sleep(0)
            return FakeResponse(503, {})

        async def post(self, _url: str, json: dict | None = None):
            await asyncio.sleep(0)
            return FakeResponse(200, {"ok": True, "echo": json or {}})

    monkeypatch.setattr(ps.httpx, "AsyncClient", lambda timeout=10.0: FakeClient())

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/personas",
            json={
                "name": "ErrPersona",
                "avatar_color": "#0A84FF",
                "system_prompt": "Error path prompt for summary.",
                "preferred_model_id": "m-err",
                "memory_policy": "balanced",
                "tags": [],
            },
        )
        pid = created.json()["id"]
        summary = await ac.get(f"/personas/{pid}/memory-summary")
    assert summary.status_code == 502


@pytest.mark.asyncio
async def test_compress_memory_accepts_request():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/personas",
            json={
                "name": "Compressor",
                "avatar_color": "#30D158",
                "system_prompt": "Compression test persona prompt.",
                "preferred_model_id": "m-comp",
                "memory_policy": "aggressive",
                "tags": [],
            },
        )
        pid = created.json()["id"]
        queued = await ac.post(f"/personas/{pid}/compress-memory")
    assert queued.status_code == 202
    assert queued.json()["accepted"] is True


@pytest.mark.asyncio
async def test_compress_memory_updates_summary(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str):
            await asyncio.sleep(0)
            if "/memories/by-persona/" in url:
                return FakeResponse(
                    200,
                    {
                        "memories": [
                            {"content": "older memory one", "created_at": "2025-01-01T00:00:00Z"},
                            {"content": "older memory two", "created_at": "2025-01-02T00:00:00Z"},
                        ]
                    },
                )
            return FakeResponse(200, {"topics": []})

        async def post(self, _url: str, json: dict | None = None):
            await asyncio.sleep(0)
            return FakeResponse(200, {"ok": True, "echo": json or {}})

    monkeypatch.setattr(ps.httpx, "AsyncClient", lambda timeout=10.0: FakeClient())

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/personas",
            json={
                "name": "Compressor2",
                "avatar_color": "#64D2FF",
                "system_prompt": "Compression update persona prompt.",
                "preferred_model_id": "m-comp2",
                "memory_policy": "balanced",
                "tags": [],
            },
        )
        pid = created.json()["id"]

    await ps._run_memory_compression(pid)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        got = await ac.get(f"/personas/{pid}")
    assert got.status_code == 200
    assert "older memory" in (got.json()["compressed_summary"] or "")


@pytest.mark.asyncio
async def test_legacy_endpoints_mapping():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/persona",
            json={
                "name": "Legacy",
                "system_prompt": "Legacy system prompt text.",
                "model_id": "legacy-model",
                "memory_scope": "task",
            },
        )
        pid = created.json()["id"]
        got = await ac.get(f"/persona/{pid}")
        patched = await ac.patch(f"/persona/{pid}", json={"model_id": "legacy-model-v2"})
    assert created.status_code == 200
    assert got.status_code == 200
    assert patched.status_code == 200
    assert got.json()["model_id"] == "legacy-model"
    assert patched.json()["model_id"] == "legacy-model-v2"
