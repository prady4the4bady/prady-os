from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, model_validator

_SHARED_PATH = Path(__file__).resolve().parents[1] / "shared"
if str(_SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(_SHARED_PATH))

from auth_middleware import require_auth

try:
    import aiosqlite
except Exception:  # pragma: no cover
    aiosqlite = None

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
except Exception:  # pragma: no cover
    AsyncIOScheduler = None  # type: ignore[assignment,misc]
    CronTrigger = None  # type: ignore[assignment,misc]
    IntervalTrigger = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "scheduler.db"

PERSONA_SERVICE_URL = os.environ.get("PERSONA_SERVICE_URL", "http://persona-service:8109")
MEMORY_SERVICE_URL = os.environ.get("MEMORY_SERVICE_URL", "http://memory-service:8108")
AGENT_RUNTIME_URL = os.environ.get("AGENT_RUNTIME_URL", "http://agent-runtime:8100")
NOTIFICATION_BUS_URL = os.environ.get("NOTIFICATION_BUS_URL", "http://notification-bus:8111")
_JOB_NOT_FOUND = "job not found"
_SELECT_JOB_BY_ID_SQL = "SELECT * FROM jobs WHERE id = ?"

_scheduler: AsyncIOScheduler | None = None
_scheduled_tasks: dict[str, asyncio.Task[None]] = {}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class JobCreateRequest(BaseModel):
    name: str
    cron_expr: str | None = None
    interval_seconds: int | None = None
    payload: dict[str, Any] = {}
    persona_id: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def _check_schedule(self) -> "JobCreateRequest":
        if self.cron_expr is None and self.interval_seconds is None:
            raise ValueError("either cron_expr or interval_seconds must be provided")
        if self.cron_expr is not None and self.interval_seconds is not None:
            raise ValueError("cron_expr and interval_seconds are mutually exclusive")
        return self


class JobPatchRequest(BaseModel):
    name: str | None = None
    cron_expr: str | None = None
    interval_seconds: int | None = None
    payload: dict[str, Any] | None = None
    persona_id: str | None = None
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ddl = """
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL UNIQUE,
      cron_expr TEXT,
      interval_seconds INTEGER,
      payload TEXT NOT NULL DEFAULT '{}',
      persona_id TEXT,
      enabled INTEGER NOT NULL DEFAULT 1,
      last_run TEXT,
      next_run TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS job_runs (
      id TEXT PRIMARY KEY,
      job_id TEXT NOT NULL,
      status TEXT NOT NULL,
      result TEXT,
      error TEXT,
      started_at TEXT NOT NULL,
      finished_at TEXT
    );
    """
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript(ddl)
            await db.commit()
        return

    def _sync_init() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.executescript(ddl)
            conn.commit()
        finally:
            conn.close()

    import asyncio
    await asyncio.to_thread(_sync_init)


def _row_to_job(row: Any) -> dict[str, Any]:
    if row is None:
        raise HTTPException(status_code=404, detail=_JOB_NOT_FOUND)
    return {
        "id": row["id"],
        "name": row["name"],
        "cron_expr": row["cron_expr"],
        "interval_seconds": row["interval_seconds"],
        "payload": json.loads(row["payload"]) if row["payload"] else {},
        "persona_id": row["persona_id"],
        "enabled": bool(row["enabled"]),
        "last_run": row["last_run"],
        "next_run": row["next_run"],
        "created_at": row["created_at"],
    }


def _row_to_run(row: Any) -> dict[str, Any]:
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "id": row["id"],
        "job_id": row["job_id"],
        "status": row["status"],
        "result": row["result"],
        "error": row["error"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


# ---------------------------------------------------------------------------
# APScheduler helpers
# ---------------------------------------------------------------------------

def _register_job_in_scheduler(job: dict[str, Any]) -> None:
    """Register or re-register a job in the APScheduler instance."""
    if _scheduler is None or not job["enabled"]:
        return
    job_id = job["id"]
    # Remove existing job if present
    try:
        _scheduler.remove_job(job_id)
    except Exception:
        pass
    if job["cron_expr"]:
        trigger = CronTrigger.from_crontab(job["cron_expr"])
    else:
        trigger = IntervalTrigger(seconds=job["interval_seconds"])
    _scheduler.add_job(_execute_job, trigger=trigger, id=job_id, kwargs={"job_id": job_id})


async def _fetch_job_for_execution(job_id: str) -> dict[str, Any] | None:
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(_SELECT_JOB_BY_ID_SQL, (job_id,))
            row = await cur.fetchone()
            return _row_to_job(row) if row is not None else None

    import asyncio

    def _sync_fetch() -> dict[str, Any] | None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(_SELECT_JOB_BY_ID_SQL, (job_id,)).fetchone()
            return _row_to_job(row) if row else None
        finally:
            conn.close()

    return await asyncio.to_thread(_sync_fetch)


async def _insert_running_job_run(run_id: str, job_id: str, started_at: str) -> None:
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO job_runs (id, job_id, status, started_at) VALUES (?, ?, ?, ?)",
                (run_id, job_id, "running", started_at),
            )
            await db.commit()
        return

    import asyncio

    def _sync_insert() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                "INSERT INTO job_runs (id, job_id, status, started_at) VALUES (?, ?, ?, ?)",
                (run_id, job_id, "running", started_at),
            )
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_sync_insert)


async def _get_persona_context(client: httpx.AsyncClient) -> dict[str, Any]:
    try:
        response = await client.get(f"{PERSONA_SERVICE_URL}/persona/active")
    except Exception:
        return {}
    return response.json() if response.is_success else {}


async def _get_memory_context(client: httpx.AsyncClient, job_name: str) -> dict[str, Any]:
    try:
        response = await client.get(
            f"{MEMORY_SERVICE_URL}/context/build",
            params={"q": job_name, "user_id": "scheduler", "max_tokens": 500},
        )
    except Exception:
        return {}
    return response.json() if response.is_success else {}


async def _dispatch_agent_task(
    client: httpx.AsyncClient,
    run_id: str,
    task_payload: dict[str, Any],
) -> tuple[str, str | None, str | None, dict[str, Any] | None]:
    response = await client.post(
        f"{AGENT_RUNTIME_URL}/api/task",
        json=task_payload,
        headers={"X-Run-ID": run_id},
        timeout=120,
    )
    if response.is_success:
        agent_result = response.json()
        return "done", json.dumps(agent_result), None, agent_result
    return "failed", None, f"agent returned {response.status_code}: {response.text[:200]}", None


async def _ingest_execution_result(
    client: httpx.AsyncClient,
    job_name: str,
    agent_result: dict[str, Any] | None,
    job_id: str,
    run_id: str,
) -> None:
    if agent_result is None:
        return
    try:
        await client.post(
            f"{MEMORY_SERVICE_URL}/memory/ingest-task",
            json={
                "task": job_name,
                "result": agent_result,
                "job_id": job_id,
                "run_id": run_id,
            },
        )
    except Exception:
        pass


async def _finish_job_run(
    run_id: str,
    job_id: str,
    status: str,
    result_str: str | None,
    error_str: str | None,
    finished_at: str,
) -> None:
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE job_runs SET status=?, result=?, error=?, finished_at=? WHERE id=?",
                (status, result_str, error_str, finished_at, run_id),
            )
            await db.execute(
                "UPDATE jobs SET last_run=?, next_run=NULL WHERE id=?",
                (finished_at, job_id),
            )
            await db.commit()
        return

    import asyncio

    def _sync_finish() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                "UPDATE job_runs SET status=?, result=?, error=?, finished_at=? WHERE id=?",
                (status, result_str, error_str, finished_at, run_id),
            )
            conn.execute(
                "UPDATE jobs SET last_run=?, next_run=NULL WHERE id=?",
                (finished_at, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_sync_finish)


def _build_completion_notification_payload(
    status: str,
    job_name: str,
    result_str: str | None,
    error_str: str | None,
) -> dict[str, Any]:
    if status == "done":
        return {
            "type": "job_complete",
            "title": f"Job {job_name} completed",
            "body": result_str[:80] if result_str else "",
            "source": "task-scheduler",
            "severity": "success",
        }
    return {
        "type": "job_failed",
        "title": f"Job {job_name} failed",
        "body": error_str[:80] if error_str else "",
        "source": "task-scheduler",
        "severity": "error",
    }


async def _notify_job_completion(payload: dict[str, Any]) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{NOTIFICATION_BUS_URL}/notify", json=payload)
    except Exception:
        pass


async def _execute_job(job_id: str) -> None:
    """Execute a scheduled job: fetch persona+context, call agent, ingest result."""
    run_id = str(uuid.uuid4())
    started_at = _now_iso()
    status = "running"
    result_str: str | None = None
    error_str: str | None = None

    try:
        job = await _fetch_job_for_execution(job_id)
    except Exception as exc:
        logger.error("Failed to fetch job %s: %s", job_id, exc)
        return

    if job is None:
        logger.warning("Job %s not found during execution", job_id)
        return

    await _insert_running_job_run(run_id, job_id, started_at)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            persona_ctx = await _get_persona_context(client)
            memory_ctx = await _get_memory_context(client, job["name"])
            task_payload = {
                "task": job["name"],
                "payload": job["payload"],
                "persona": persona_ctx,
                "context": memory_ctx,
                "job_id": job_id,
            }
            logger.info("_execute_job: dispatching run_id=%s job_id=%s", run_id, job_id)
            status, result_str, error_str, agent_result = await _dispatch_agent_task(
                client,
                run_id,
                task_payload,
            )
            if status == "done":
                await _ingest_execution_result(client, job["name"], agent_result, job_id, run_id)
    except Exception as exc:
        error_str = str(exc)[:500]
        status = "failed"

    finished_at = _now_iso()
    await _finish_job_run(run_id, job_id, status, result_str, error_str, finished_at)
    logger.info("Job %s run %s finished with status=%s", job_id, run_id, status)

    payload = _build_completion_notification_payload(status, job["name"], result_str, error_str)
    notify_task = asyncio.create_task(_notify_job_completion(payload))
    _scheduled_tasks[f"notify:{run_id}"] = notify_task


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _scheduler
    await _init_db()
    if AsyncIOScheduler is not None:
        _scheduler = AsyncIOScheduler()
        _scheduler.start()
        # Re-register all enabled jobs from DB
        try:
            if aiosqlite is not None:
                async with aiosqlite.connect(DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    cur = await db.execute("SELECT * FROM jobs WHERE enabled = 1")
                    rows = await cur.fetchall()
                    for row in rows:
                        job = _row_to_job(row)
                        _register_job_in_scheduler(job)
        except Exception as exc:
            logger.warning("Failed to restore scheduled jobs: %s", exc)
    yield
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Kryos Task Scheduler", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/job", status_code=201)
async def create_job(
    req: JobCreateRequest,
    _current_user: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    await _init_db()
    job_id = str(uuid.uuid4())
    now = _now_iso()
    payload_json = json.dumps(req.payload)

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            try:
                await db.execute(
                    """
                    INSERT INTO jobs (id, name, cron_expr, interval_seconds, payload, persona_id, enabled, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (job_id, req.name, req.cron_expr, req.interval_seconds, payload_json,
                     req.persona_id, int(req.enabled), now),
                )
                await db.commit()
            except Exception as exc:
                raise HTTPException(status_code=409, detail=f"job create failed: {exc}") from exc
    else:
        def _sync_insert() -> None:
            conn = sqlite3.connect(DB_PATH)
            try:
                conn.execute(
                    """
                    INSERT INTO jobs (id, name, cron_expr, interval_seconds, payload, persona_id, enabled, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (job_id, req.name, req.cron_expr, req.interval_seconds, payload_json,
                     req.persona_id, int(req.enabled), now),
                )
                conn.commit()
            finally:
                conn.close()
        import asyncio
        try:
            await asyncio.to_thread(_sync_insert)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"job create failed: {exc}") from exc

    job = {
        "id": job_id,
        "name": req.name,
        "cron_expr": req.cron_expr,
        "interval_seconds": req.interval_seconds,
        "payload": req.payload,
        "persona_id": req.persona_id,
        "enabled": req.enabled,
        "last_run": None,
        "next_run": None,
        "created_at": now,
    }
    if req.enabled:
        _register_job_in_scheduler(job)
    return job


@app.get("/job")
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    await _init_db()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            total_cur = await db.execute("SELECT COUNT(*) FROM jobs")
            total_row = await total_cur.fetchone()
            total = total_row[0] if total_row else 0
            cur = await db.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
            )
            rows = await cur.fetchall()
            return {"jobs": [_row_to_job(r) for r in rows], "total": total}

    def _sync_list() -> dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
            return {"jobs": [_row_to_job(r) for r in rows], "total": total}
        finally:
            conn.close()

    import asyncio
    return await asyncio.to_thread(_sync_list)


@app.get("/job/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    await _init_db()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(_SELECT_JOB_BY_ID_SQL, (job_id,))
            row = await cur.fetchone()
            return _row_to_job(row)

    def _sync_get() -> dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(_SELECT_JOB_BY_ID_SQL, (job_id,)).fetchone()
            return _row_to_job(row)
        finally:
            conn.close()

    import asyncio
    return await asyncio.to_thread(_sync_get)


@app.patch("/job/{job_id}")
async def patch_job(job_id: str, req: JobPatchRequest) -> dict[str, Any]:
    await _init_db()
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")

    # Build SET clause
    set_parts: list[str] = []
    params: list[Any] = []
    for key, val in updates.items():
        if key == "payload":
            set_parts.append("payload = ?")
            params.append(json.dumps(val))
        elif key == "enabled":
            set_parts.append("enabled = ?")
            params.append(int(val))
        else:
            set_parts.append(f"{key} = ?")
            params.append(val)
    params.append(job_id)
    sql = f"UPDATE jobs SET {', '.join(set_parts)} WHERE id = ?"  # noqa: S608

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(sql, params)
            await db.commit()
            db.row_factory = aiosqlite.Row
            cur = await db.execute(_SELECT_JOB_BY_ID_SQL, (job_id,))
            row = await cur.fetchone()
            job = _row_to_job(row)
    else:
        def _sync_patch() -> dict[str, Any]:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(sql, params)
                conn.commit()
                row = conn.execute(_SELECT_JOB_BY_ID_SQL, (job_id,)).fetchone()
                return _row_to_job(row)
            finally:
                conn.close()
        import asyncio
        job = await asyncio.to_thread(_sync_patch)

    # Re-register with scheduler
    if _scheduler is not None:
        try:
            _scheduler.remove_job(job_id)
        except Exception:
            pass
        if job["enabled"]:
            _register_job_in_scheduler(job)
    return job


@app.delete("/job/{job_id}", status_code=204, response_model=None)
async def delete_job(job_id: str) -> None:
    await _init_db()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
            if await cur.fetchone() is None:
                raise HTTPException(status_code=404, detail=_JOB_NOT_FOUND)
            await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            await db.execute("DELETE FROM job_runs WHERE job_id = ?", (job_id,))
            await db.commit()
    else:
        def _sync_delete() -> None:
            conn = sqlite3.connect(DB_PATH)
            try:
                row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail=_JOB_NOT_FOUND)
                conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                conn.execute("DELETE FROM job_runs WHERE job_id = ?", (job_id,))
                conn.commit()
            finally:
                conn.close()
        import asyncio
        await asyncio.to_thread(_sync_delete)

    if _scheduler is not None:
        try:
            _scheduler.remove_job(job_id)
        except Exception:
            pass


@app.post("/job/{job_id}/run-now", status_code=202)
async def run_job_now(job_id: str) -> dict[str, Any]:
    # Verify the job exists
    await get_job(job_id)
    import asyncio
    execute_task = asyncio.create_task(_execute_job(job_id))
    _scheduled_tasks[f"job:{job_id}"] = execute_task
    return {"ok": True, "job_id": job_id, "queued": True}


@app.get("/job/{job_id}/runs")
async def get_job_runs(
    job_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    await _init_db()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            total_cur = await db.execute("SELECT COUNT(*) FROM job_runs WHERE job_id = ?", (job_id,))
            total_row = await total_cur.fetchone()
            total = total_row[0] if total_row else 0
            cur = await db.execute(
                "SELECT * FROM job_runs WHERE job_id = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (job_id, limit, offset),
            )
            rows = await cur.fetchall()
            return {"runs": [_row_to_run(r) for r in rows], "total": total}

    def _sync_runs() -> dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            total = conn.execute("SELECT COUNT(*) FROM job_runs WHERE job_id = ?", (job_id,)).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM job_runs WHERE job_id = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (job_id, limit, offset),
            ).fetchall()
            return {"runs": [_row_to_run(r) for r in rows], "total": total}
        finally:
            conn.close()

    import asyncio
    return await asyncio.to_thread(_sync_runs)


@app.get("/health")
async def health() -> dict[str, Any]:
    scheduler_running = _scheduler is not None and _scheduler.running
    return {"status": "ok", "scheduler_running": scheduler_running}
