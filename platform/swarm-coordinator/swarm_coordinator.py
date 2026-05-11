from __future__ import annotations

import os
import asyncio
import datetime
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Kryos Swarm Coordinator", version="1.0.0")

_DEFAULT_POLICY_PATH = Path(__file__).parent.parent.parent / "vyrex" / "policies" / "swarm_policy.yaml"
_LUMYN_URL = "http://lumyn-bridge:8102"
VYREX_PROXY_URL = os.environ.get("VYREX_PROXY_URL", "http://vyrex-proxy:8105")
_TASK_NOT_FOUND_DETAIL = "task not found"

# ── in-memory state ───────────────────────────────────────────────────────────

_tasks: dict[str, "Task"] = {}
_active_sessions: dict[str, "AgentSession"] = {}
_background_tasks: set[Any] = set()  # Track background tasks to prevent garbage collection


# ── data models ───────────────────────────────────────────────────────────────

class SubTask(BaseModel):
    id: str
    parent_id: str
    agent_id: str
    description: str
    status: str = "pending"
    result: Optional[str] = None


class Task(BaseModel):
    id: str
    description: str
    max_agents: int
    subtasks: list[SubTask] = []
    status: str = "pending"
    created_at: float
    completed_at: Optional[float] = None


class AgentSession(BaseModel):
    agent_id: str
    task_id: str
    load: int = 1
    started_at: float


class CreateTaskRequest(BaseModel):
    description: str
    max_agents: int = 3


# ── policy ────────────────────────────────────────────────────────────────────

def _load_policy() -> dict[str, Any]:
    path = Path(__file__).parent.parent.parent / "vyrex" / "policies" / "swarm_policy.yaml"
    if not path.exists():
        path = _DEFAULT_POLICY_PATH
    if not path.exists():
        return {
            "max_concurrent_agents": 10,
            "max_subtasks_per_task": 20,
            "allowed_task_types": ["*"],
            "require_user_confirmation_above_agents": 5,
            "max_task_duration_s": 600,
        }
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _assert_policy(req: CreateTaskRequest) -> None:
    policy = _load_policy()
    max_agents = int(policy.get("max_concurrent_agents", 10))
    if req.max_agents > max_agents:
        raise HTTPException(
            status_code=403,
            detail=f"max_agents {req.max_agents} exceeds policy limit {max_agents}",
        )
    max_subtasks = int(policy.get("max_subtasks_per_task", 20))
    if req.max_agents > max_subtasks:
        raise HTTPException(
            status_code=403,
            detail=f"max_agents exceeds max_subtasks_per_task {max_subtasks}",
        )


# ── Lumyn decomposition ──────────────────────────────────────────────────────

_DECOMPOSE_PROMPT = (
    "You are a task planner. Decompose this task into exactly {n} "
    "independent subtasks, each completable by a single AI agent. "
    'Output JSON array: [{{"id":1,"description":"..."}}]. '
    "Task: {desc}"
)


def _parse_subtasks(text: str, parent_id: str, n: int) -> list[SubTask]:
    match = re.search(r"\[[^\]]*\]", text, re.DOTALL)
    if not match:
        # Fallback: create n generic subtasks
        return [
            SubTask(
                id=str(uuid.uuid4()),
                parent_id=parent_id,
                agent_id=f"agent-{i}",
                description=f"Subtask {i + 1}",
                status="pending",
            )
            for i in range(n)
        ]
    try:
        raw = json.loads(match.group(0))
        subtasks: list[SubTask] = []
        for item in raw[:n]:
            subtasks.append(
                SubTask(
                    id=str(uuid.uuid4()),
                    parent_id=parent_id,
                    agent_id=f"agent-{len(subtasks)}",
                    description=str(item.get("description", f"Subtask {len(subtasks) + 1}")),
                    status="pending",
                )
            )
        return subtasks
    except (json.JSONDecodeError, AttributeError):
        return [
            SubTask(
                id=str(uuid.uuid4()),
                parent_id=parent_id,
                agent_id=f"agent-{i}",
                description=f"Subtask {i + 1}",
                status="pending",
            )
            for i in range(n)
        ]


async def _decompose_via_lumyn(task_id: str, description: str, n: int) -> list[SubTask]:
    lumyn_url = _LUMYN_URL
    prompt = _DECOMPOSE_PROMPT.format(n=n, desc=description)
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{lumyn_url}/lumyn/task",
                json={"task": prompt, "model_id": "lumyn-default", "context": {"task_type": "general"}},
            )
        if resp.is_success:
            body = resp.json()
            result_text = ""
            result = body.get("result", {})
            if isinstance(result, dict):
                result_text = str(result.get("output", "") or result.get("response", ""))
            else:
                result_text = str(result)
            return _parse_subtasks(result_text, task_id, n)
    except Exception:
        pass
    return _parse_subtasks("", task_id, n)


async def _dispatch_subtasks(task: Task) -> None:
    lumyn_url = _LUMYN_URL
    for subtask in task.subtasks:
        subtask.status = "running"
        session = AgentSession(
            agent_id=subtask.agent_id,
            task_id=task.id,
            load=1,
            started_at=time.time(),
        )
        _active_sessions[subtask.agent_id] = session
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{lumyn_url}/lumyn/task",
                    json={
                        "task": subtask.description,
                        "model_id": "lumyn-default",
                        "context": {"task_type": "automation", "subtask_id": subtask.id},
                    },
                )
            if resp.is_success:
                body = resp.json()
                result = body.get("result", {})
                if isinstance(result, dict):
                    subtask.result = str(result.get("output", "done"))
                else:
                    subtask.result = str(result)
                subtask.status = "done"
            else:
                subtask.status = "failed"
                subtask.result = f"HTTP {resp.status_code}"
        except Exception as exc:
            subtask.status = "failed"
            subtask.result = str(exc)
        finally:
            _active_sessions.pop(subtask.agent_id, None)

    all_done = all(st.status == "done" for st in task.subtasks)
    task.status = "done" if all_done else "failed"
    task.completed_at = time.time()


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.post("/swarm/task", status_code=202)
async def create_task(req: CreateTaskRequest) -> dict[str, Any]:
    _assert_policy(req)

    task_id = str(uuid.uuid4())
    task = Task(
        id=task_id,
        description=req.description,
        max_agents=req.max_agents,
        status="pending",
        created_at=time.time(),
    )
    _tasks[task_id] = task

    # Decompose subtasks
    subtasks = await _decompose_via_lumyn(task_id, req.description, req.max_agents)
    task.subtasks = subtasks
    task.status = "running"

    # Fire dispatch in background
    task_handle = asyncio.create_task(_dispatch_subtasks(task))
    _background_tasks.add(task_handle)
    task_handle.add_done_callback(_background_tasks.discard)

    return {"task_id": task_id, "status": task.status, "subtask_count": len(subtasks)}


@app.get("/swarm/task/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=_TASK_NOT_FOUND_DETAIL)
    return task.model_dump()


@app.get("/swarm/tasks")
def list_tasks(limit: int = 10, offset: int = 0) -> dict[str, Any]:
    all_tasks = sorted(_tasks.values(), key=lambda t: t.created_at, reverse=True)
    page = all_tasks[offset: offset + limit]
    return {"tasks": [t.model_dump() for t in page], "total": len(_tasks)}


@app.delete("/swarm/task/{task_id}")
def cancel_task(task_id: str) -> dict[str, Any]:
    task = _tasks.pop(task_id, None)
    if not task:
        raise HTTPException(status_code=404, detail=_TASK_NOT_FOUND_DETAIL)
    task.status = "cancelled"
    task.completed_at = time.time()
    for st in task.subtasks:
        if st.status in ("pending", "running"):
            st.status = "cancelled"
    # Remove sessions
    for st in task.subtasks:
        _active_sessions.pop(st.agent_id, None)
    return {"ok": True, "task_id": task_id}


@app.get("/swarm/agents")
def list_agents() -> dict[str, Any]:
    sessions = [s.model_dump() for s in _active_sessions.values()]
    return {"agents": sessions, "count": len(sessions)}


@app.get("/swarm/graph/{task_id}")
def task_graph(task_id: str) -> dict[str, Any]:
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=_TASK_NOT_FOUND_DETAIL)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Root node (the parent task)
    nodes.append({
        "id": task.id,
        "label": task.description[:60],
        "status": task.status,
        "depth": 0,
        "index_in_row": 0,
    })

    for idx, subtask in enumerate(task.subtasks):
        nodes.append({
            "id": subtask.id,
            "label": subtask.description[:60],
            "status": subtask.status,
            "agent_id": subtask.agent_id,
            "result": subtask.result,
            "depth": 1,
            "index_in_row": idx,
        })
        edges.append({"from": task.id, "to": subtask.id})

    return {"nodes": nodes, "edges": edges}
