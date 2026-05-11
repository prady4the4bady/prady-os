from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).parents[3]
SWARM_DIR = REPO_ROOT / "platform" / "swarm-coordinator"
if str(SWARM_DIR) not in sys.path:
    sys.path.insert(0, str(SWARM_DIR))

import swarm_coordinator as sc
from swarm_coordinator import app

TRANSPORT = ASGITransport(app=app)  # type: ignore[arg-type]

_LUMYN_TASK_DECOMPOSE_RESP = {
    "task_id": "h-1",
    "status": "done",
    "backend": "lumyn-agent",
    "result": {"output": '[{"id":1,"description":"Do part A"},{"id":2,"description":"Do part B"},{"id":3,"description":"Do part C"}]'},
}

_LUMYN_TASK_EXEC_RESP = {
    "task_id": "h-2",
    "status": "done",
    "backend": "lumyn-agent",
    "result": {"output": "done"},
}


def _lumyn_mock_post(url: str, **kwargs: Any) -> Any:
    mock = AsyncMock()
    mock.is_success = True
    if "task" in url:
        body = kwargs.get("json", {})
        task_text = body.get("task", "")
        if "Decompose" in task_text:
            mock.json.return_value = _LUMYN_TASK_DECOMPOSE_RESP
        else:
            mock.json.return_value = _LUMYN_TASK_EXEC_RESP
    return mock


@pytest.fixture(autouse=True)
def _clear_state() -> None:
    sc._tasks.clear()
    sc._active_sessions.clear()


@pytest.mark.asyncio
async def test_task_create_and_decompose() -> None:
    mock_client = AsyncMock()
    mock_resp_decompose = MagicMock()
    mock_resp_decompose.is_success = True
    mock_resp_decompose.json.return_value = _LUMYN_TASK_DECOMPOSE_RESP
    mock_resp_exec = MagicMock()
    mock_resp_exec.is_success = True
    mock_resp_exec.json.return_value = _LUMYN_TASK_EXEC_RESP
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=[mock_resp_decompose, mock_resp_exec, mock_resp_exec, mock_resp_exec])

    with patch("swarm_coordinator.httpx.AsyncClient", return_value=mock_client):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.post("/swarm/task", json={"description": "Open browser and search", "max_agents": 3})

    assert resp.status_code == 202
    body = resp.json()
    assert "task_id" in body
    assert body["subtask_count"] == 3


@pytest.mark.asyncio
async def test_task_status_tree() -> None:
    # Pre-populate a task
    import uuid, time as _time
    task_id = str(uuid.uuid4())
    subtask = sc.SubTask(id=str(uuid.uuid4()), parent_id=task_id, agent_id="a0", description="step1", status="done")
    task = sc.Task(id=task_id, description="test task", max_agents=1, subtasks=[subtask], status="done", created_at=_time.time())
    sc._tasks[task_id] = task

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
        resp = await client.get(f"/swarm/task/{task_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == task_id
    assert len(body["subtasks"]) == 1


@pytest.mark.asyncio
async def test_task_list_pagination() -> None:
    import uuid, time as _time
    for _ in range(5):
        t_id = str(uuid.uuid4())
        sc._tasks[t_id] = sc.Task(id=t_id, description="t", max_agents=1, status="done", created_at=_time.time())

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
        resp = await client.get("/swarm/tasks?limit=3&offset=0")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tasks"]) == 3
    assert body["total"] == 5


@pytest.mark.asyncio
async def test_task_cancel() -> None:
    import uuid, time as _time
    task_id = str(uuid.uuid4())
    sc._tasks[task_id] = sc.Task(id=task_id, description="cancel me", max_agents=1, status="running", created_at=_time.time())

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
        resp = await client.delete(f"/swarm/task/{task_id}")

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert task_id not in sc._tasks


@pytest.mark.asyncio
async def test_agent_list() -> None:
    import time as _time
    sc._active_sessions["a1"] = sc.AgentSession(agent_id="a1", task_id="t1", load=1, started_at=_time.time())

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
        resp = await client.get("/swarm/agents")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["agents"][0]["agent_id"] == "a1"


@pytest.mark.asyncio
async def test_graph_output_structure() -> None:
    import uuid, time as _time
    task_id = str(uuid.uuid4())
    st_id = str(uuid.uuid4())
    subtask = sc.SubTask(id=st_id, parent_id=task_id, agent_id="a0", description="subtask A", status="done")
    sc._tasks[task_id] = sc.Task(
        id=task_id, description="main task", max_agents=1,
        subtasks=[subtask], status="done", created_at=_time.time()
    )

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
        resp = await client.get(f"/swarm/graph/{task_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    assert body["edges"][0]["from"] == task_id
    assert body["edges"][0]["to"] == st_id


@pytest.mark.asyncio
async def test_policy_block_max_agents() -> None:
    policy = {
        "max_concurrent_agents": 2,
        "max_subtasks_per_task": 20,
        "allowed_task_types": ["*"],
        "require_user_confirmation_above_agents": 5,
        "max_task_duration_s": 600,
    }
    with patch("swarm_coordinator._load_policy", return_value=policy):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.post("/swarm/task", json={"description": "big task", "max_agents": 5})

    assert resp.status_code == 403
