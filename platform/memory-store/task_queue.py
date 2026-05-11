"""Phase 9B-3: Redis-backed task queue router for memory-store service."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

REDIS_URL = "redis://redis:6379"
QUEUE_KEY = "kryos:task_queue"
TASK_PREFIX = "kryos:task:"

router = APIRouter(prefix="/api/queue", tags=["task-queue"])


def _redis() -> aioredis.Redis:  # type: ignore[type-arg]
    return aioredis.from_url(REDIS_URL, decode_responses=True)


class TaskPushRequest(BaseModel):
    goal: str
    priority: int = 5
    metadata: dict[str, Any] = {}


class TaskEntry(BaseModel):
    task_id: str
    goal: str
    priority: int
    status: str
    created_at: float
    metadata: dict[str, Any] = {}


@router.post("/push")
async def push_task(req: TaskPushRequest) -> dict[str, Any]:
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    entry = TaskEntry(
        task_id=task_id,
        goal=req.goal,
        priority=req.priority,
        status="pending",
        created_at=time.time(),
        metadata=req.metadata,
    )
    r = _redis()
    async with r:
        await r.set(f"{TASK_PREFIX}{task_id}", entry.model_dump_json())
        await r.zadd(QUEUE_KEY, {task_id: -req.priority})  # higher priority = lower score
    return {"task_id": task_id, "status": "pending"}


@router.get("/next")
async def get_next_task() -> dict[str, Any]:
    r = _redis()
    async with r:
        results = await r.zpopmin(QUEUE_KEY, count=1)
        if not results:
            return {"task": None}
        task_id, _ = results[0]
        raw = await r.get(f"{TASK_PREFIX}{task_id}")
        if raw is None:
            return {"task": None}
        await r.set(f"{TASK_PREFIX}{task_id}", _update_status(raw, "processing"))
        return {"task": json.loads(raw)}


@router.get("/list")
async def list_tasks() -> dict[str, Any]:
    r = _redis()
    async with r:
        ids = await r.zrange(QUEUE_KEY, 0, -1)
        tasks = []
        for tid in ids:
            raw = await r.get(f"{TASK_PREFIX}{tid}")
            if raw:
                tasks.append(json.loads(raw))
    return {"tasks": tasks, "total": len(tasks)}


@router.delete("/{task_id}")
async def delete_task(task_id: str) -> dict[str, Any]:
    r = _redis()
    async with r:
        removed = await r.zrem(QUEUE_KEY, task_id)
        await r.delete(f"{TASK_PREFIX}{task_id}")
    if not removed:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True, "task_id": task_id}


def _update_status(raw: str, status: str) -> str:
    data = json.loads(raw)
    data["status"] = status
    return json.dumps(data)
