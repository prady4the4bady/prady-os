from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


REPO_ROOT = Path(__file__).parents[3]
SERVICE_DIR = REPO_ROOT / "platform" / "task-scheduler"
sys.path.insert(0, str(SERVICE_DIR))

import scheduler_service as ss
from scheduler_service import app

TRANSPORT = ASGITransport(app=app)


@pytest_asyncio.fixture(autouse=True)
async def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ss, "DB_PATH", tmp_path / "scheduler.db")
    monkeypatch.setattr(ss, "_scheduler", None)
    await ss._init_db()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "scheduler_running" in data


# ---------------------------------------------------------------------------
# Create — cron
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_job_cron():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/job",
            json={"name": "nightly-report", "cron_expr": "0 2 * * *", "payload": {"key": "val"}},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "nightly-report"
    assert data["cron_expr"] == "0 2 * * *"
    assert data["interval_seconds"] is None
    assert data["payload"] == {"key": "val"}
    assert data["enabled"] is True


# ---------------------------------------------------------------------------
# Create — interval
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_job_interval():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/job",
            json={"name": "heartbeat", "interval_seconds": 60},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["interval_seconds"] == 60
    assert data["cron_expr"] is None


# ---------------------------------------------------------------------------
# Create — both fields → 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_job_both_schedule_422():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/job",
            json={"name": "bad-job", "cron_expr": "* * * * *", "interval_seconds": 30},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Create — neither field → 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_job_neither_schedule_422():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/job",
            json={"name": "no-schedule"},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get by ID
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_job_by_id():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/job",
            json={"name": "fetch-test", "interval_seconds": 120},
        )
        job_id = created.json()["id"]
        resp = await ac.get(f"/job/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


# ---------------------------------------------------------------------------
# Get — not found → 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_job_not_found():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/job/nonexistent-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_jobs():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post("/job", json={"name": "job-a", "interval_seconds": 10})
        await ac.post("/job", json={"name": "job-b", "cron_expr": "*/5 * * * *"})
        resp = await ac.get("/job")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["jobs"]) == 2


# ---------------------------------------------------------------------------
# List — pagination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_jobs_pagination():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        for i in range(5):
            await ac.post("/job", json={"name": f"job-{i}", "interval_seconds": 10 + i})
        page1 = await ac.get("/job", params={"limit": 2, "offset": 0})
        page2 = await ac.get("/job", params={"limit": 2, "offset": 2})
    assert page1.status_code == 200
    assert len(page1.json()["jobs"]) == 2
    assert page1.json()["total"] == 5
    assert len(page2.json()["jobs"]) == 2


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_job():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post(
            "/job",
            json={"name": "updatable", "interval_seconds": 30},
        )
        job_id = created.json()["id"]
        patched = await ac.patch(f"/job/{job_id}", json={"name": "updated-name", "enabled": False})
    assert patched.status_code == 200
    assert patched.json()["name"] == "updated-name"
    assert patched.json()["enabled"] is False


# ---------------------------------------------------------------------------
# Patch — empty fields → 400
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_job_no_fields_400():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post("/job", json={"name": "patchless", "interval_seconds": 10})
        job_id = created.json()["id"]
        resp = await ac.patch(f"/job/{job_id}", json={})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_job():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post("/job", json={"name": "deletable", "interval_seconds": 10})
        job_id = created.json()["id"]
        del_resp = await ac.delete(f"/job/{job_id}")
        get_resp = await ac.get(f"/job/{job_id}")
    assert del_resp.status_code == 204
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete — not found → 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_job_not_found():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.delete("/job/nonexistent-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Run-now
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_now():
    with patch("scheduler_service._execute_job", new_callable=AsyncMock):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
            created = await ac.post("/job", json={"name": "run-me", "interval_seconds": 3600})
            job_id = created.json()["id"]
            resp = await ac.post(f"/job/{job_id}/run-now")
    assert resp.status_code == 202
    assert resp.json()["ok"] is True
    assert resp.json()["job_id"] == job_id


# ---------------------------------------------------------------------------
# Run-now — not found → 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_now_not_found():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/job/nonexistent/run-now")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Get runs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_runs_empty():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        created = await ac.post("/job", json={"name": "no-runs", "interval_seconds": 60})
        job_id = created.json()["id"]
        resp = await ac.get(f"/job/{job_id}/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["runs"] == []


# ---------------------------------------------------------------------------
# Duplicate name → 409
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_duplicate_name_409():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post("/job", json={"name": "unique-job", "interval_seconds": 10})
        resp = await ac.post("/job", json={"name": "unique-job", "interval_seconds": 20})
    assert resp.status_code == 409
