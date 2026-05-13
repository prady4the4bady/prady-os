from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from inventor_db import InventorDB
from inventor_service import app, state


@pytest.fixture(autouse=True)
async def reset_state(tmp_path):
    state.loop_active = False
    state.current_phase = "idle"
    state.active_project = None
    state.pending_proposal = None
    state.completed_projects = 0
    state.db = InventorDB(str(tmp_path / "test_inventor.db"))
    await state.db.init()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "inventor-engine"
    assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_get_status_returns_correct_schema(client: AsyncClient):
    resp = await client.get("/inventor/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "loop_active" in data
    assert "current_phase" in data
    assert "active_project" in data
    assert "completed_projects" in data
    assert "pending_proposal" in data
    assert "last_scan_ts" in data


@pytest.mark.asyncio
async def test_start_sets_loop_active(client: AsyncClient):
    resp = await client.post("/inventor/start")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"


@pytest.mark.asyncio
async def test_start_when_already_running_returns_idempotent(client: AsyncClient):
    await client.post("/inventor/start")
    resp = await client.post("/inventor/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_running"


@pytest.mark.asyncio
async def test_stop_sets_loop_inactive(client: AsyncClient):
    await client.post("/inventor/start")
    resp = await client.post("/inventor/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


@pytest.mark.asyncio
async def test_get_proposals_returns_list(client: AsyncClient):
    resp = await client.get("/inventor/proposals")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_approve_unknown_proposal_returns_404(client: AsyncClient):
    resp = await client.post("/inventor/proposals/nonexistent/approve")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_unknown_proposal_returns_404(client: AsyncClient):
    resp = await client.post("/inventor/proposals/nonexistent/reject")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_projects_returns_list(client: AsyncClient):
    resp = await client.get("/inventor/projects")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_project_progress_unknown_returns_404(client: AsyncClient):
    resp = await client.get("/inventor/projects/nonexistent/progress")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_release_unknown_project_returns_404(client: AsyncClient):
    resp = await client.post("/inventor/projects/nonexistent/release")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_proposal_triggers_build(client: AsyncClient, sample_proposal):
    await state.db.save_proposal(sample_proposal)
    with patch("inventor_service._build_and_verify", AsyncMock()):
        resp = await client.post(f"/inventor/proposals/{sample_proposal.proposal_id}/approve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "building"
    assert "project_id" in data


@pytest.mark.asyncio
async def test_reject_proposal_marks_rejected(client: AsyncClient, sample_proposal):
    await state.db.save_proposal(sample_proposal)
    resp = await client.post(f"/inventor/proposals/{sample_proposal.proposal_id}/reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_get_project_progress_returns_schema(client: AsyncClient, sample_proposal):
    await state.db.save_proposal(sample_proposal)
    project_id = "test-project-123"
    await state.db.approve_proposal(sample_proposal.proposal_id, project_id)
    await state.db.update_project_status(project_id, "building")
    resp = await client.get(f"/inventor/projects/{project_id}/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == project_id
    assert "status" in data
    assert "test_results" in data
    assert "verified" in data
