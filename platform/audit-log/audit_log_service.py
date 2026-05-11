"""
audit_log_service.py – FastAPI service for persistent task history, replay & audit log.

Endpoints:
  GET  /runs                   paginated list with filters
  GET  /runs/stats             aggregate statistics
  GET  /runs/{run_id}          full detail
  POST /runs/{run_id}/replay   re-submit original task
  GET  /health
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

try:
    import aiosqlite
except Exception:  # pragma: no cover
    aiosqlite = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "audit.db"

NOTIFICATION_BUS_URL = os.environ.get("NOTIFICATION_BUS_URL", "http://notification-bus:8111")
AGENT_RUNTIME_URL = os.environ.get("AGENT_RUNTIME_URL", "http://agent-runtime:8100")

# Event types we capture from the notification bus
_CAPTURED_TYPES = {"task_complete", "task_failed", "job_complete", "job_failed", "memory_ingested"}

_subscriber_task: asyncio.Task[None] | None = None


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS task_runs (
    id             TEXT PRIMARY KEY,
    task_id        TEXT,
    agent_id       TEXT,
    persona_id     TEXT,
    status         TEXT,
    started_at     TEXT,
    finished_at    TEXT,
    steps_json     TEXT,
    result_json    TEXT,
    error          TEXT,
    replay_count   INTEGER NOT NULL DEFAULT 0,
    source         TEXT,
    task_description TEXT,
    created_at     TEXT
)
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(_DDL)
            await db.commit()
    else:
        def _sync_init() -> None:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(_DDL)
                conn.commit()

        await asyncio.to_thread(_sync_init)


async def _insert_run(record: dict[str, Any]) -> None:
    sql = """
        INSERT OR IGNORE INTO task_runs
            (id, task_id, agent_id, persona_id, status, started_at, finished_at,
             steps_json, result_json, error, replay_count, source, task_description, created_at)
        VALUES
            (:id, :task_id, :agent_id, :persona_id, :status, :started_at, :finished_at,
             :steps_json, :result_json, :error, :replay_count, :source, :task_description, :created_at)
    """
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(sql, record)
            await db.commit()
    else:
        def _sync_insert() -> None:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(sql, record)
                conn.commit()

        await asyncio.to_thread(_sync_insert)


async def _increment_replay(run_id: str) -> None:
    sql = "UPDATE task_runs SET replay_count = replay_count + 1 WHERE id = :id"
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(sql, {"id": run_id})
            await db.commit()
    else:
        def _sync_update() -> None:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(sql, {"id": run_id})
                conn.commit()

        await asyncio.to_thread(_sync_update)


async def _fetch_runs(
    *,
    status: str | None,
    agent_id: str | None,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    conditions: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if status:
        conditions.append("status = :status")
        params["status"] = status
    if agent_id:
        conditions.append("agent_id = :agent_id")
        params["agent_id"] = agent_id
    if date_from:
        conditions.append("created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("created_at <= :date_to")
        params["date_to"] = date_to

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    data_sql = f"SELECT * FROM task_runs {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    count_sql = f"SELECT COUNT(*) FROM task_runs {where}"

    rows: list[dict[str, Any]] = []
    total = 0

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(data_sql, params) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
            async with db.execute(count_sql, count_params) as cur:
                row = await cur.fetchone()
                total = row[0] if row else 0
    else:
        def _sync_fetch() -> tuple[list[dict[str, Any]], int]:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(data_sql, params)
                r = [dict(x) for x in cur.fetchall()]
                count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
                c = conn.execute(count_sql, count_params).fetchone()
                t = c[0] if c else 0
            return r, t

        rows, total = await asyncio.to_thread(_sync_fetch)

    return rows, total


async def _fetch_run(run_id: str) -> dict[str, Any] | None:
    sql = "SELECT * FROM task_runs WHERE id = :id"
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, {"id": run_id}) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
    else:
        def _sync_get() -> dict[str, Any] | None:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(sql, {"id": run_id}).fetchone()
                return dict(row) if row else None

        return await asyncio.to_thread(_sync_get)


async def _fetch_stats() -> dict[str, Any]:
    sql = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done_count,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
            SUM(CASE WHEN status = 'stopped' THEN 1 ELSE 0 END) as stopped_count
        FROM task_runs
    """
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(sql) as cur:
                row = await cur.fetchone()
    else:
        def _sync_stats() -> Any:
            with sqlite3.connect(DB_PATH) as conn:
                return conn.execute(sql).fetchone()

        row = await asyncio.to_thread(_sync_stats)

    if row:
        total, done, failed, stopped = row[0], row[1] or 0, row[2] or 0, row[3] or 0
    else:
        total, done, failed, stopped = 0, 0, 0, 0

    return {
        "total": total,
        "by_status": {"done": done, "failed": failed, "stopped": stopped},
    }


# ---------------------------------------------------------------------------
# SSE subscriber
# ---------------------------------------------------------------------------

def _event_to_record(event: dict[str, Any]) -> dict[str, Any]:
    event_type = event.get("type", "")
    source = event.get("source", "system")
    title = event.get("title", "")
    body = event.get("body", "")
    created_at = event.get("created_at", _now_iso())

    # Map notification type to task run status
    if event_type in ("task_complete", "job_complete"):
        status = "done"
    elif event_type in ("task_failed", "job_failed"):
        status = "failed"
    else:
        status = "info"

    task_description = body or title

    return {
        "id": str(uuid.uuid4()),
        "task_id": event.get("id", ""),
        "agent_id": source,
        "persona_id": None,
        "status": status,
        "started_at": created_at,
        "finished_at": created_at,
        "steps_json": "[]",
        "result_json": json.dumps({"title": title, "body": body, "type": event_type}),
        "error": body if status == "failed" else None,
        "replay_count": 0,
        "source": source,
        "task_description": task_description,
        "created_at": created_at,
    }


def _decode_sse_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data: "):
        return None
    raw = line[len("data: "):]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def _consume_notification_stream(resp: httpx.Response) -> None:
    async for line in resp.aiter_lines():
        event = _decode_sse_line(line)
        if event is None or event.get("type") not in _CAPTURED_TYPES:
            continue
        record = _event_to_record(event)
        try:
            await _insert_run(record)
        except Exception as exc:
            logger.warning("audit-log: failed to insert run: %s", exc)


async def _open_notification_stream(client: httpx.AsyncClient) -> None:
    async with client.stream("GET", f"{NOTIFICATION_BUS_URL}/stream") as resp:
        await _consume_notification_stream(resp)


async def _subscribe_notifications() -> None:
    """Background task: subscribe to notification-bus SSE and persist relevant events."""
    backoff = 2.0
    while True:
        try:
            logger.info("audit-log: connecting to notification-bus SSE stream")
            async with httpx.AsyncClient(timeout=None) as client:
                backoff = 2.0
                await _open_notification_stream(client)
        except asyncio.CancelledError:
            logger.info("audit-log: SSE subscriber cancelled")
            raise
        except Exception as exc:
            logger.warning("audit-log: SSE subscriber error, retrying in %.0fs: %s", backoff, exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[type-arg]
    global _subscriber_task
    await _init_db()
    _subscriber_task = asyncio.create_task(_subscribe_notifications())
    yield
    if _subscriber_task is not None:
        _subscriber_task.cancel()
        await _subscriber_task
        _subscriber_task = None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Kryos Audit Log", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/runs")
async def list_runs(
    status: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    rows, total = await _fetch_runs(
        status=status,
        agent_id=agent_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "runs": rows, "limit": limit, "offset": offset}


@app.get("/runs/stats")
async def get_stats() -> dict[str, Any]:
    return await _fetch_stats()


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    row = await _fetch_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    return row


@app.post("/runs/{run_id}/replay")
async def replay_run(run_id: str) -> dict[str, Any]:
    row = await _fetch_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")

    task_description = row.get("task_description") or ""
    if not task_description:
        raise HTTPException(status_code=422, detail="run has no task_description; cannot replay")

    new_run_id = str(uuid.uuid4())

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{AGENT_RUNTIME_URL}/computer/task/run",
                json={"task_description": task_description, "max_steps": 20},
                headers={"X-Run-ID": new_run_id},
            )
    except Exception as exc:
        logger.warning("audit-log: replay dispatch failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"agent-runtime unavailable: {exc}") from exc

    await _increment_replay(run_id)

    return {"ok": True, "run_id": new_run_id, "replayed_from": run_id}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "audit-log"}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8112)
