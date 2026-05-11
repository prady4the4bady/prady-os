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
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

try:
    import aiosqlite
except Exception:  # pragma: no cover
    aiosqlite = None

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "notifications.db"
_NOTIFICATION_NOT_FOUND_DETAIL = "notification not found"
_SELECT_NOTIFICATION_ID_SQL = "SELECT id FROM notifications WHERE id = ?"

# Active SSE client queues
_sse_clients: list[asyncio.Queue[str]] = []


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class NotifyRequest(BaseModel):
    type: str
    title: str
    body: str = ""
    source: str = "system"
    severity: str = "info"


class ReadAllRequest(BaseModel):
    pass


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ddl = """
    CREATE TABLE IF NOT EXISTS notifications (
      id TEXT PRIMARY KEY,
      type TEXT NOT NULL,
      title TEXT NOT NULL,
      body TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'system',
      severity TEXT NOT NULL DEFAULT 'info',
      read INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
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

    await asyncio.to_thread(_sync_init)


def _row_to_notif(row: Any) -> dict[str, Any]:
    if row is None:
        raise HTTPException(status_code=404, detail=_NOTIFICATION_NOT_FOUND_DETAIL)
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "body": row["body"],
        "source": row["source"],
        "severity": row["severity"],
        "read": bool(row["read"]),
        "created_at": row["created_at"],
    }


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _broadcast(event_json: str) -> None:
    """Push event string to all connected SSE client queues."""
    dead: list[asyncio.Queue[str]] = []
    for q in _sse_clients:
        try:
            q.put_nowait(event_json)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _sse_clients.remove(q)
        except ValueError:
            pass


async def _sse_generator() -> AsyncIterator[str]:
    """Async generator that yields SSE events for a single client."""
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
    _sse_clients.append(q)
    try:
        while True:
            try:
                event_json = await asyncio.wait_for(q.get(), timeout=15.0)
                yield f"data: {event_json}\n\n"
            except asyncio.TimeoutError:
                # Keep-alive ping
                yield ": ping\n\n"
    finally:
        try:
            _sse_clients.remove(q)
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _init_db()
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Kryos Notification Bus", version="1.0.0", lifespan=lifespan)

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

@app.get("/stream")
async def sse_stream() -> StreamingResponse:
    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/notify", status_code=201)
async def publish_notification(req: NotifyRequest) -> dict[str, Any]:
    await _init_db()
    notif_id = str(uuid.uuid4())
    now = _now_iso()

    notif = {
        "id": notif_id,
        "type": req.type,
        "title": req.title,
        "body": req.body,
        "source": req.source,
        "severity": req.severity,
        "read": False,
        "created_at": now,
    }

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO notifications (id, type, title, body, source, severity, read, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                (notif_id, req.type, req.title, req.body, req.source, req.severity, now),
            )
            await db.commit()
    else:
        def _sync_insert() -> None:
            conn = sqlite3.connect(DB_PATH)
            try:
                conn.execute(
                    "INSERT INTO notifications (id, type, title, body, source, severity, read, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                    (notif_id, req.type, req.title, req.body, req.source, req.severity, now),
                )
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_sync_insert)

    # Broadcast to all SSE subscribers
    _broadcast(json.dumps(notif))
    return notif


@app.get("/notification")
async def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    await _init_db()
    where = "WHERE read = 0" if unread_only else ""

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            total_cur = await db.execute(f"SELECT COUNT(*) FROM notifications {where}")  # noqa: S608
            total_row = await total_cur.fetchone()
            total = total_row[0] if total_row else 0
            cur = await db.execute(
                f"SELECT * FROM notifications {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",  # noqa: S608
                (limit, offset),
            )
            rows = await cur.fetchall()
            return {"notifications": [_row_to_notif(r) for r in rows], "total": total}

    def _sync_list() -> dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            total = conn.execute(f"SELECT COUNT(*) FROM notifications {where}").fetchone()[0]  # noqa: S608
            rows = conn.execute(
                f"SELECT * FROM notifications {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",  # noqa: S608
                (limit, offset),
            ).fetchall()
            return {"notifications": [_row_to_notif(r) for r in rows], "total": total}
        finally:
            conn.close()

    return await asyncio.to_thread(_sync_list)


@app.get("/notification/{notif_id}")
async def get_notification(notif_id: str) -> dict[str, Any]:
    await _init_db()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM notifications WHERE id = ?", (notif_id,))
            row = await cur.fetchone()
            return _row_to_notif(row)

    def _sync_get() -> dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM notifications WHERE id = ?", (notif_id,)).fetchone()
            return _row_to_notif(row)
        finally:
            conn.close()

    return await asyncio.to_thread(_sync_get)


@app.patch("/notification/{notif_id}/read")
async def mark_read(notif_id: str) -> dict[str, Any]:
    await _init_db()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(_SELECT_NOTIFICATION_ID_SQL, (notif_id,))
            if await cur.fetchone() is None:
                raise HTTPException(status_code=404, detail=_NOTIFICATION_NOT_FOUND_DETAIL)
            await db.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notif_id,))
            await db.commit()
    else:
        def _sync_read() -> None:
            conn = sqlite3.connect(DB_PATH)
            try:
                row = conn.execute(_SELECT_NOTIFICATION_ID_SQL, (notif_id,)).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail=_NOTIFICATION_NOT_FOUND_DETAIL)
                conn.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notif_id,))
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_sync_read)

    return {"ok": True, "id": notif_id}


@app.post("/notification/read-all")
async def read_all() -> dict[str, Any]:
    await _init_db()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("UPDATE notifications SET read = 1 WHERE read = 0")
            await db.commit()
            return {"ok": True, "updated": cur.rowcount}
    else:
        def _sync_read_all() -> int:
            conn = sqlite3.connect(DB_PATH)
            try:
                cur = conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()
        updated = await asyncio.to_thread(_sync_read_all)
        return {"ok": True, "updated": updated}


@app.delete("/notification/{notif_id}", status_code=204, response_model=None)
async def delete_notification(notif_id: str) -> None:
    await _init_db()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(_SELECT_NOTIFICATION_ID_SQL, (notif_id,))
            if await cur.fetchone() is None:
                raise HTTPException(status_code=404, detail=_NOTIFICATION_NOT_FOUND_DETAIL)
            await db.execute("DELETE FROM notifications WHERE id = ?", (notif_id,))
            await db.commit()
    else:
        def _sync_delete() -> None:
            conn = sqlite3.connect(DB_PATH)
            try:
                row = conn.execute(_SELECT_NOTIFICATION_ID_SQL, (notif_id,)).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail=_NOTIFICATION_NOT_FOUND_DETAIL)
                conn.execute("DELETE FROM notifications WHERE id = ?", (notif_id,))
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_sync_delete)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "connected_clients": len(_sse_clients)}
