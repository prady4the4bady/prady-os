"""Phase 9B-4: Autonomous loop runner — dequeues tasks, executes via swarm, applies self-correction."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager, suppress
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
SWARM_URL = os.getenv("SWARM_URL", "http://kryos-swarm:8000")
MEMORY_STORE_URL = os.getenv("MEMORY_STORE_URL", "http://memory-store:8094")
MODEL_GATEWAY_URL = os.getenv("MODEL_GATEWAY_URL", "http://model-gateway:8000")
QUEUE_NEXT_URL = f"{MEMORY_STORE_URL}/api/queue/next"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _stop_event.clear()
    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        _state["running"] = False
        _stop_event.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="PradyOS Loop Runner", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_state: dict[str, Any] = {
    "running": False,
    "paused": False,
    "tasks_processed": 0,
    "started_at": 0.0,
}
_stop_event = asyncio.Event()


async def _wait_or_stop(seconds: float) -> bool:
    try:
        await asyncio.wait_for(_stop_event.wait(), timeout=seconds)
        return True
    except TimeoutError:
        return False


async def _execute_task(task: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{SWARM_URL}/task/execute", json=task)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


async def _emit_progress(payload: dict[str, Any]) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{SWARM_URL}/agentnet/publish", json={"topic": "loop.progress", "payload": payload})
    except Exception as exc:
        logger.debug("AgentNet emit failed: %s", exc)


async def _fetch_next_task() -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(QUEUE_NEXT_URL)
        resp.raise_for_status()
        return resp.json().get("task")


async def _execute_with_correction(corrector: Any, task: dict[str, Any]) -> dict[str, Any]:
    try:
        return await _execute_task(task)
    except Exception as exc:
        logger.warning("Task %s failed: %s — attempting self-correction", task.get("task_id"), exc)
        return await corrector.correct({"task": task, "error": str(exc), "output": ""})


async def _poll_next_task() -> dict[str, Any] | None:
    if _state["paused"]:
        await _wait_or_stop(1)
        return None
    try:
        task = await _fetch_next_task()
    except Exception as exc:
        logger.warning("Failed to fetch next task: %s", exc)
        await _wait_or_stop(5)
        return None
    if task is None:
        await _wait_or_stop(2)
        return None
    return task


async def _loop() -> None:
    from self_correct import SelfCorrectionEngine  # imported lazily to avoid circular deps
    corrector = SelfCorrectionEngine()
    _state["running"] = True
    _state["started_at"] = time.time()

    while not _stop_event.is_set():
        task = await _poll_next_task()
        if task is None:
            continue

        logger.info("Processing task %s: %s", task.get("task_id"), task.get("goal"))
        result = await _execute_with_correction(corrector, task)

        _state["tasks_processed"] += 1
        await _emit_progress({"task_id": task.get("task_id"), "result": result})
        await _wait_or_stop(0.1)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/loop/status")
async def get_status() -> dict[str, Any]:
    return {
        "running": _state["running"],
        "paused": _state["paused"],
        "tasks_processed": _state["tasks_processed"],
        "uptime_seconds": int(time.time() - _state["started_at"]) if _state["started_at"] else 0,
    }


@app.post("/api/loop/pause")
async def pause_loop() -> dict[str, Any]:
    _state["paused"] = True
    return {"paused": True}


@app.post("/api/loop/resume")
async def resume_loop() -> dict[str, Any]:
    _state["paused"] = False
    return {"paused": False}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("loop_runner:app", host="0.0.0.0", port=8011, reload=False)
