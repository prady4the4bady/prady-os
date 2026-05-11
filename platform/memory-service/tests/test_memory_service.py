from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


REPO_ROOT = Path(__file__).parents[3]
SERVICE_DIR = REPO_ROOT / "platform" / "memory-service"
sys.path.insert(0, str(SERVICE_DIR))

import memory_service as ms
from memory_service import app

TRANSPORT = ASGITransport(app=app)


@pytest_asyncio.fixture(autouse=True)
async def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ms, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(ms, "_EMBED_MODEL", None)
    await ms._init_db()


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_memory():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/memory", json={"type": "fact", "content": "uses firefox"})
    assert resp.status_code == 200
    assert resp.json()["id"]


@pytest.mark.asyncio
async def test_create_memory_missing_type_422():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/memory", json={"content": "missing type"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_memory_fts():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post("/memory", json={"type": "fact", "content": "likes dark theme"})
        await ac.post("/memory", json={"type": "task", "content": "opened browser"})
        await ac.post("/memory", json={"type": "shortcut", "content": "cmd+m opens memory"})
        resp = await ac.get("/memory/search", params={"q": "browser"})
    assert resp.status_code == 200
    assert any("browser" in r["content"] for r in resp.json()["results"])


@pytest.mark.asyncio
async def test_search_memory_with_type_filter():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post("/memory", json={"type": "fact", "content": "prefers kitty"})
        await ac.post("/memory", json={"type": "task", "content": "opened kitty"})
        resp = await ac.get("/memory/search", params={"q": "kitty", "type": "fact"})
    assert resp.status_code == 200
    assert all(r["type"] == "fact" for r in resp.json()["results"])


@pytest.mark.asyncio
async def test_get_memory_by_id():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post("/memory", json={"type": "fact", "content": "uses hyprland"})
        memory_id = created.json()["id"]
        got = await ac.get(f"/memory/{memory_id}")
    assert got.status_code == 200
    assert got.json()["id"] == memory_id


@pytest.mark.asyncio
async def test_patch_memory():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post("/memory", json={"type": "fact", "content": "uses terminal"})
        memory_id = created.json()["id"]
        patched = await ac.patch(f"/memory/{memory_id}", json={"content": "uses kitty terminal"})
        got = await ac.get(f"/memory/{memory_id}")
    assert patched.status_code == 200
    assert "kitty" in got.json()["content"]


@pytest.mark.asyncio
async def test_delete_memory():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post("/memory", json={"type": "fact", "content": "temp memory"})
        memory_id = created.json()["id"]
        deleted = await ac.delete(f"/memory/{memory_id}")
        missing = await ac.get(f"/memory/{memory_id}")
    assert deleted.status_code == 200
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_ingest_task_auto_memory():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/memory/ingest-task",
            json={"task_description": "open browser", "result": "done", "duration_s": 2.4, "steps_taken": 5},
        )
        memory_id = resp.json()["id"]
        got = await ac.get(f"/memory/{memory_id}")
    assert resp.status_code == 200
    assert got.status_code == 200
    assert got.json()["type"] == "task"


@pytest.mark.asyncio
async def test_session_start_and_end():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        started = await ac.post("/session/start", json={"user_id": "default"})
        sid = started.json()["session_id"]
        ended = await ac.post("/session/end", json={"session_id": sid, "summary": "worked on setup"})
    assert started.status_code == 200
    assert ended.status_code == 200


@pytest.mark.asyncio
async def test_session_list():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post("/session/start", json={"user_id": "default"})
        resp = await ac.get("/session/list", params={"user_id": "default"})
    assert resp.status_code == 200
    assert "sessions" in resp.json()


@pytest.mark.asyncio
async def test_context_build():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post("/memory", json={"type": "fact", "content": "user likes concise answers"})
        resp = await ac.get("/context/build", params={"q": "likes", "max_tokens": 200})
    assert resp.status_code == 200
    assert resp.json()["context"].startswith("## User Memory Context")


@pytest.mark.asyncio
async def test_memories_by_persona_endpoint():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post(
            "/memory",
            json={"type": "fact", "content": "persona memory one", "persona_id": "persona-123", "tags": ["work"]},
        )
        await ac.post(
            "/memory",
            json={"type": "task", "content": "persona memory two", "persona_id": "persona-123", "tags": ["work", "task"]},
        )
        await ac.post(
            "/memory",
            json={"type": "fact", "content": "other persona", "persona_id": "persona-other", "tags": ["other"]},
        )
        resp = await ac.get("/memories/by-persona/persona-123")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(m["persona_id"] == "persona-123" for m in body["memories"])


@pytest.mark.asyncio
async def test_memories_topics_endpoint():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post(
            "/memory",
            json={"type": "fact", "content": "topic 1", "persona_id": "persona-abc", "tags": ["Work", "Urgent"]},
        )
        await ac.post(
            "/memory",
            json={"type": "fact", "content": "topic 2", "persona_id": "persona-abc", "tags": ["work"]},
        )
        resp = await ac.get("/memories/topics/persona-abc")
    assert resp.status_code == 200
    topics = resp.json()["topics"]
    work_topic = next((t for t in topics if t["topic"] == "work"), None)
    assert work_topic is not None
    assert work_topic["count"] >= 2
