from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).parent.parent))
import notification_service as ns
from notification_service import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ns, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ns, "DB_PATH", tmp_path / "notifications.db")
    # Clear SSE clients between tests
    ns._sse_clients.clear()
    await ns._init_db()


TRANSPORT = ASGITransport(app=app)
BASE = "http://test"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "connected_clients" in data


@pytest.mark.asyncio
async def test_publish_notification() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.post("/notify", json={
            "type": "job_complete",
            "title": "Job done",
            "body": "result ok",
            "source": "task-scheduler",
            "severity": "success",
        })
    assert r.status_code == 201
    data = r.json()
    assert data["type"] == "job_complete"
    assert data["title"] == "Job done"
    assert data["severity"] == "success"
    assert data["read"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_list_notifications() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        await ac.post("/notify", json={"type": "system", "title": "Test 1", "body": "", "source": "test", "severity": "info"})
        await ac.post("/notify", json={"type": "system", "title": "Test 2", "body": "", "source": "test", "severity": "warning"})
        r = await ac.get("/notification")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert len(data["notifications"]) == 2


@pytest.mark.asyncio
async def test_list_unread_only() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        await ac.post("/notify", json={"type": "system", "title": "Unread", "body": "", "source": "test", "severity": "info"})
        r2 = await ac.post("/notify", json={"type": "system", "title": "To read", "body": "", "source": "test", "severity": "info"})
        notif_id = r2.json()["id"]
        # Mark one as read
        await ac.patch(f"/notification/{notif_id}/read")
        r = await ac.get("/notification", params={"unread_only": "true"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["notifications"][0]["title"] == "Unread"


@pytest.mark.asyncio
async def test_get_notification() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        create_r = await ac.post("/notify", json={"type": "agent_error", "title": "Oops", "body": "details here", "source": "agent", "severity": "error"})
        notif_id = create_r.json()["id"]
        r = await ac.get(f"/notification/{notif_id}")
    assert r.status_code == 200
    assert r.json()["id"] == notif_id
    assert r.json()["title"] == "Oops"


@pytest.mark.asyncio
async def test_get_notification_not_found() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get("/notification/nonexistent-id")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_mark_read() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        create_r = await ac.post("/notify", json={"type": "system", "title": "Ping", "body": "", "source": "test", "severity": "info"})
        notif_id = create_r.json()["id"]
        r = await ac.patch(f"/notification/{notif_id}/read")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # Confirm it's now read
        get_r = await ac.get(f"/notification/{notif_id}")
        assert get_r.json()["read"] is True


@pytest.mark.asyncio
async def test_mark_read_not_found() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.patch("/notification/no-such-id/read")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_read_all() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        for i in range(3):
            await ac.post("/notify", json={"type": "system", "title": f"N{i}", "body": "", "source": "test", "severity": "info"})
        r = await ac.post("/notification/read-all")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["updated"] == 3
        # All should now be read
        list_r = await ac.get("/notification", params={"unread_only": "true"})
        assert list_r.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_notification() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        create_r = await ac.post("/notify", json={"type": "system", "title": "Del me", "body": "", "source": "test", "severity": "info"})
        notif_id = create_r.json()["id"]
        del_r = await ac.delete(f"/notification/{notif_id}")
        assert del_r.status_code == 204
        get_r = await ac.get(f"/notification/{notif_id}")
        assert get_r.status_code == 404


@pytest.mark.asyncio
async def test_delete_notification_not_found() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.delete("/notification/ghost-id")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_pagination() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        for i in range(5):
            await ac.post("/notify", json={"type": "system", "title": f"N{i}", "body": "", "source": "test", "severity": "info"})
        r = await ac.get("/notification", params={"limit": 2, "offset": 0})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5
    assert len(data["notifications"]) == 2


@pytest.mark.asyncio
async def test_pagination_offset() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        for i in range(5):
            await ac.post("/notify", json={"type": "system", "title": f"P{i}", "body": "", "source": "test", "severity": "info"})
        r = await ac.get("/notification", params={"limit": 3, "offset": 4})
    assert r.status_code == 200
    assert len(r.json()["notifications"]) == 1


@pytest.mark.asyncio
async def test_sse_stream_receives_event() -> None:
    """Test that a published notification is placed into connected SSE client queues."""
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
    ns._sse_clients.append(q)

    try:
        async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
            await ac.post("/notify", json={
                "type": "job_complete",
                "title": "SSE test",
                "body": "hello",
                "source": "test",
                "severity": "success",
            })

        # Queue should now have the event
        assert not q.empty()
        event_json = q.get_nowait()
        event = json.loads(event_json)
        assert event["title"] == "SSE test"
        assert event["type"] == "job_complete"
    finally:
        try:
            ns._sse_clients.remove(q)
        except ValueError:
            pass
