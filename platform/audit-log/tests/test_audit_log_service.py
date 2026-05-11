from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).parent.parent))
import audit_log_service as als
from audit_log_service import app

TRANSPORT = ASGITransport(app=app)
BASE = "http://test"


def _run_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture(autouse=True)
async def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(als, "DATA_DIR", tmp_path)
    monkeypatch.setattr(als, "DB_PATH", tmp_path / "audit.db")
    # Cancel any existing subscriber task so startup doesn't hang
    if als._subscriber_task is not None and not als._subscriber_task.done():
        als._subscriber_task.cancel()
    als._subscriber_task = None
    await als._init_db()


async def _insert_sample(
    *,
    run_id: str | None = None,
    status: str = "done",
    agent_id: str = "computer-use",
    task_description: str = "click the button",
) -> str:
    rid = run_id or _run_id()
    await als._insert_run(
        {
            "id": rid,
            "task_id": _run_id(),
            "agent_id": agent_id,
            "persona_id": None,
            "status": status,
            "started_at": "2024-01-01T00:00:00+00:00",
            "finished_at": "2024-01-01T00:00:10+00:00",
            "steps_json": "[]",
            "result_json": "{}",
            "error": None if status == "done" else "something broke",
            "replay_count": 0,
            "source": agent_id,
            "task_description": task_description,
            "created_at": "2024-01-01T00:00:00+00:00",
        }
    )
    return rid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_health() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "audit-log"


async def test_list_runs_empty() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get("/runs")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["runs"] == []


async def test_list_runs_with_data() -> None:
    await _insert_sample(status="done")
    await _insert_sample(status="failed")

    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get("/runs")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert len(data["runs"]) == 2


async def test_list_runs_filter_by_status() -> None:
    await _insert_sample(status="done")
    await _insert_sample(status="failed")

    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get("/runs", params={"status": "done"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["runs"][0]["status"] == "done"


async def test_list_runs_filter_by_agent_id() -> None:
    await _insert_sample(agent_id="computer-use")
    await _insert_sample(agent_id="task-scheduler")

    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get("/runs", params={"agent_id": "task-scheduler"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["runs"][0]["agent_id"] == "task-scheduler"


async def test_list_runs_pagination() -> None:
    for _ in range(5):
        await _insert_sample()

    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r1 = await ac.get("/runs", params={"limit": 2, "offset": 0})
        r2 = await ac.get("/runs", params={"limit": 2, "offset": 4})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(r1.json()["runs"]) == 2
    assert r1.json()["total"] == 5
    assert len(r2.json()["runs"]) == 1


async def test_list_runs_date_range() -> None:
    await als._insert_run(
        {
            "id": _run_id(),
            "task_id": "",
            "agent_id": "test",
            "persona_id": None,
            "status": "done",
            "started_at": "2024-01-01T00:00:00+00:00",
            "finished_at": "2024-01-01T00:00:10+00:00",
            "steps_json": "[]",
            "result_json": "{}",
            "error": None,
            "replay_count": 0,
            "source": "test",
            "task_description": "old task",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
    )
    await als._insert_run(
        {
            "id": _run_id(),
            "task_id": "",
            "agent_id": "test",
            "persona_id": None,
            "status": "done",
            "started_at": "2025-06-01T00:00:00+00:00",
            "finished_at": "2025-06-01T00:00:10+00:00",
            "steps_json": "[]",
            "result_json": "{}",
            "error": None,
            "replay_count": 0,
            "source": "test",
            "task_description": "new task",
            "created_at": "2025-06-01T00:00:00+00:00",
        }
    )

    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get("/runs", params={"date_from": "2025-01-01"})
    data = r.json()
    assert data["total"] == 1
    assert data["runs"][0]["task_description"] == "new task"


async def test_get_run() -> None:
    rid = await _insert_sample(task_description="open browser")

    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get(f"/runs/{rid}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == rid
    assert data["task_description"] == "open browser"
    assert data["status"] == "done"


async def test_get_run_not_found() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get(f"/runs/{_run_id()}")
    assert r.status_code == 404


async def test_stats_empty() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get("/runs/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["by_status"]["done"] == 0
    assert data["by_status"]["failed"] == 0


async def test_stats_with_data() -> None:
    await _insert_sample(status="done")
    await _insert_sample(status="done")
    await _insert_sample(status="failed")

    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.get("/runs/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["by_status"]["done"] == 2
    assert data["by_status"]["failed"] == 1


async def test_replay_run() -> None:
    rid = await _insert_sample(task_description="type hello world")

    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("audit_log_service.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
            r = await ac.post(f"/runs/{rid}/replay")

    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "run_id" in data
    assert data["replayed_from"] == rid

    # Verify replay_count incremented
    row = await als._fetch_run(rid)
    assert row is not None
    assert row["replay_count"] == 1


async def test_replay_run_not_found() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url=BASE) as ac:
        r = await ac.post(f"/runs/{_run_id()}/replay")
    assert r.status_code == 404


def test_sse_event_to_record_task_complete() -> None:
    event = {
        "id": "notif-123",
        "type": "task_complete",
        "title": "Task completed",
        "body": "click the submit button",
        "source": "computer-use",
        "severity": "success",
        "read": False,
        "created_at": "2024-06-01T12:00:00+00:00",
    }
    record = als._event_to_record(event)
    assert record["status"] == "done"
    assert record["source"] == "computer-use"
    assert record["task_description"] == "click the submit button"
    assert record["task_id"] == "notif-123"
    assert json.loads(record["result_json"])["type"] == "task_complete"


def test_sse_event_to_record_job_failed() -> None:
    event = {
        "id": "notif-456",
        "type": "job_failed",
        "title": "Job nightly-report failed",
        "body": "timeout after 120s",
        "source": "task-scheduler",
        "severity": "error",
        "read": False,
        "created_at": "2024-06-01T12:05:00+00:00",
    }
    record = als._event_to_record(event)
    assert record["status"] == "failed"
    assert record["agent_id"] == "task-scheduler"
    assert record["error"] == "timeout after 120s"
