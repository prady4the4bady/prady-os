from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import aiosqlite
except Exception:  # pragma: no cover
    aiosqlite = None

try:
    from sentence_transformers import SentenceTransformer

    _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
except Exception:  # pragma: no cover
    # Keep service importable in lean/test environments without full ML stacks.
    _EMBED_MODEL = None


DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "memory.db"
NOTIFICATION_BUS_URL = os.environ.get("NOTIFICATION_BUS_URL", "http://notification-bus:8111")
_FTS_REBUILD_SQL = "INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')"
_MEMORY_NOT_FOUND = "memory not found"
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _init_db()
    yield


app = FastAPI(title="Kryos Memory Service", version="1.0.0", lifespan=lifespan)


class MemoryCreateRequest(BaseModel):
    user_id: str = "default"
    persona_id: str | None = None
    type: str
    content: str
    tags: list[str] = []
    importance: float = 0.5


class MemoryPatchRequest(BaseModel):
    content: str | None = None
    tags: list[str] | None = None
    importance: float | None = None


class IngestTaskRequest(BaseModel):
    task_description: str
    result: str
    duration_s: float
    steps_taken: int


class SessionStartRequest(BaseModel):
    user_id: str = "default"


class SessionEndRequest(BaseModel):
    session_id: str
    summary: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _embedding_bytes(text: str) -> bytes | None:
    if _EMBED_MODEL is None or np is None:
        return None
    vec = _EMBED_MODEL.encode(text)
    arr = np.asarray(vec, dtype=np.float32)
    return arr.tobytes()


def _cosine_score(query_vec: np.ndarray, stored: bytes | None) -> float:
    if np is None:
        return 0.0
    if not stored:
        return 0.0
    vec = np.frombuffer(stored, dtype=np.float32)
    denom = (np.linalg.norm(query_vec) * np.linalg.norm(vec))
    if denom == 0:
        return 0.0
    return float(np.dot(query_vec, vec) / denom)


def _is_query_mode(query: str) -> bool:
    return bool(query.strip())


def _build_memory_query_sql(query: str, user_id: str, top_k: int, memory_type: str | None) -> tuple[str, tuple[Any, ...]]:
    if _is_query_mode(query):
        sql = """
        SELECT m.rowid AS rowid, m.id, m.type, m.content, m.tags, m.importance, m.access_count, m.created_at, m.embedding
        FROM memories_fts f
        JOIN memories m ON m.rowid = f.rowid
        WHERE memories_fts MATCH ? AND m.user_id = ?
        """
        params: list[Any] = [query, user_id]
        if memory_type:
            sql += " AND m.type = ?"
            params.append(memory_type)
        sql += " ORDER BY m.updated_at DESC LIMIT ?"
        params.append(top_k)
        return sql, tuple(params)

    sql = """
    SELECT rowid, id, type, content, tags, importance, access_count, created_at, embedding
    FROM memories
    WHERE user_id = ?
    """
    params = [user_id]
    if memory_type:
        sql += " AND type = ?"
        params.append(memory_type)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(top_k)
    return sql, tuple(params)


def _row_to_memory_result(row: Any, query_vec: np.ndarray | None) -> dict[str, Any]:
    score = _cosine_score(query_vec, row["embedding"]) if query_vec is not None else 0.0
    return {
        "id": row["id"],
        "type": row["type"],
        "content": row["content"],
        "tags": json.loads(row["tags"] or "[]"),
        "importance": row["importance"],
        "access_count": row["access_count"],
        "created_at": row["created_at"],
        "score": score,
    }


def _sort_by_score_if_needed(results: list[dict[str, Any]], query_vec: np.ndarray | None) -> None:
    if query_vec is not None:
        results.sort(key=lambda item: item["score"], reverse=True)


async def _increment_access_counts_async(db: Any, results: list[dict[str, Any]]) -> None:
    for item in results:
        await db.execute("UPDATE memories SET access_count = access_count + 1 WHERE id = ?", (item["id"],))


def _increment_access_counts_sync(conn: sqlite3.Connection, results: list[dict[str, Any]]) -> None:
    for item in results:
        conn.execute("UPDATE memories SET access_count = access_count + 1 WHERE id = ?", (item["id"],))


async def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ddl = """
    CREATE TABLE IF NOT EXISTS memories (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL DEFAULT 'default',
      persona_id TEXT,
      type TEXT NOT NULL,
      content TEXT NOT NULL,
      embedding BLOB,
      tags TEXT,
      importance REAL DEFAULT 0.5,
      access_count INTEGER DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL DEFAULT 'default',
      started_at TEXT NOT NULL,
      ended_at TEXT,
      summary TEXT,
      task_count INTEGER DEFAULT 0
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
      USING fts5(content, tags, content=memories, content_rowid=rowid);
    """

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript(ddl)
            cur = await db.execute("PRAGMA table_info(memories)")
            cols = [r[1] for r in await cur.fetchall()]
            await cur.close()
            if "persona_id" not in cols:
                await db.execute("ALTER TABLE memories ADD COLUMN persona_id TEXT")
            await db.commit()
        return

    def _sync_init() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.executescript(ddl)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()]
            if "persona_id" not in cols:
                conn.execute("ALTER TABLE memories ADD COLUMN persona_id TEXT")
            conn.commit()
        finally:
            conn.close()

    import asyncio

    await asyncio.to_thread(_sync_init)


async def _insert_memory_row(
    memory_id: str,
    user_id: str,
    persona_id: str | None,
    memory_type: str,
    content: str,
    tags: list[str],
    importance: float,
    embedding: bytes | None,
) -> None:
    now = _now_iso()
    tags_json = json.dumps(tags)
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO memories (id, user_id, persona_id, type, content, embedding, tags, importance, access_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (memory_id, user_id, persona_id, memory_type, content, embedding, tags_json, importance, now, now),
            )
            await db.execute(_FTS_REBUILD_SQL)
            await db.commit()
        return

    def _sync_insert() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO memories (id, user_id, persona_id, type, content, embedding, tags, importance, access_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (memory_id, user_id, persona_id, memory_type, content, embedding, tags_json, importance, now, now),
            )
            cur.execute(_FTS_REBUILD_SQL)
            conn.commit()
        finally:
            conn.close()

    import asyncio

    await asyncio.to_thread(_sync_insert)


@app.post("/memory")
async def create_memory(req: MemoryCreateRequest) -> dict[str, Any]:
    await _init_db()
    if req.type not in {"task", "preference", "conversation", "shortcut", "fact"}:
        raise HTTPException(status_code=422, detail="invalid type")
    memory_id = str(uuid.uuid4())
    embedding = _embedding_bytes(req.content)
    await _insert_memory_row(
        memory_id,
        req.user_id,
        req.persona_id,
        req.type,
        req.content,
        req.tags,
        max(0.0, min(1.0, req.importance)),
        embedding,
    )
    return {"id": memory_id, "created_at": _now_iso()}


@app.get("/memory/search")
async def search_memory(
    q: str = "",
    user_id: str = "default",
    top_k: int = 10,
    type: str | None = None,
) -> dict[str, Any]:
    await _init_db()

    query_vec: np.ndarray | None = None
    if _EMBED_MODEL is not None and np is not None and _is_query_mode(q):
        query_vec = np.asarray(_EMBED_MODEL.encode(q), dtype=np.float32)

    sql, params = _build_memory_query_sql(q, user_id, top_k, type)

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            results = [_row_to_memory_result(row, query_vec) for row in rows]
            _sort_by_score_if_needed(results, query_vec)
            await _increment_access_counts_async(db, results)
            await db.commit()

        return {"results": results}

    def _sync_search() -> list[dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, params).fetchall()
            out = [_row_to_memory_result(row, query_vec) for row in rows]
            _sort_by_score_if_needed(out, query_vec)
            _increment_access_counts_sync(conn, out)
            conn.commit()
            return out
        finally:
            conn.close()

    import asyncio

    return {"results": await asyncio.to_thread(_sync_search)}


@app.get("/memory/{memory_id}")
async def get_memory(memory_id: str) -> dict[str, Any]:
    await _init_db()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, user_id, type, content, tags, importance, access_count, created_at, updated_at FROM memories WHERE id = ?",
                (memory_id,),
            )
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=_MEMORY_NOT_FOUND)
        return {**dict(row), "tags": json.loads(row["tags"] or "[]")}

    def _sync_get() -> dict[str, Any] | None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT id, user_id, type, content, tags, importance, access_count, created_at, updated_at FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    import asyncio

    row = await asyncio.to_thread(_sync_get)
    if not row:
        raise HTTPException(status_code=404, detail=_MEMORY_NOT_FOUND)
    row["tags"] = json.loads(row["tags"] or "[]")
    return row


@app.patch("/memory/{memory_id}")
async def patch_memory(memory_id: str, req: MemoryPatchRequest) -> dict[str, Any]:
    await _init_db()

    updates: list[str] = []
    params: list[Any] = []

    if req.content is not None:
        updates.append("content = ?")
        params.append(req.content)
        updates.append("embedding = ?")
        params.append(_embedding_bytes(req.content))
    if req.tags is not None:
        updates.append("tags = ?")
        params.append(json.dumps(req.tags))
    if req.importance is not None:
        updates.append("importance = ?")
        params.append(max(0.0, min(1.0, req.importance)))

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(memory_id)

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(f"UPDATE memories SET {', '.join(updates)} WHERE id = ?", tuple(params))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=_MEMORY_NOT_FOUND)
            await db.execute(_FTS_REBUILD_SQL)
            await db.commit()
        return {"ok": True}

    def _sync_patch() -> bool:
        conn = sqlite3.connect(DB_PATH)
        try:
            cur = conn.cursor()
            cur.execute(f"UPDATE memories SET {', '.join(updates)} WHERE id = ?", tuple(params))
            if cur.rowcount == 0:
                return False
            cur.execute(_FTS_REBUILD_SQL)
            conn.commit()
            return True
        finally:
            conn.close()

    import asyncio

    ok = await asyncio.to_thread(_sync_patch)
    if not ok:
        raise HTTPException(status_code=404, detail=_MEMORY_NOT_FOUND)
    return {"ok": True}


@app.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str) -> dict[str, Any]:
    await _init_db()

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT rowid FROM memories WHERE id = ?", (memory_id,))
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=_MEMORY_NOT_FOUND)
            await db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            await db.execute(_FTS_REBUILD_SQL)
            await db.commit()
        return {"ok": True}

    def _sync_delete() -> bool:
        conn = sqlite3.connect(DB_PATH)
        try:
            cur = conn.cursor()
            row = cur.execute("SELECT rowid FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if not row:
                return False
            cur.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            cur.execute(_FTS_REBUILD_SQL)
            conn.commit()
            return True
        finally:
            conn.close()

    import asyncio

    ok = await asyncio.to_thread(_sync_delete)
    if not ok:
        raise HTTPException(status_code=404, detail=_MEMORY_NOT_FOUND)
    return {"ok": True}


@app.post("/memory/ingest-task")
async def ingest_task(req: IngestTaskRequest) -> dict[str, Any]:
    summary = (
        f"Task: {req.task_description} | Result: {req.result} | "
        f"Steps: {req.steps_taken} | Duration: {req.duration_s:.1f}s"
    )
    importance = min(1.0, req.steps_taken / 20.0 + 0.3)
    payload = MemoryCreateRequest(type="task", content=summary, tags=["task", req.result], importance=importance)
    created = await create_memory(payload)

    async def _notify_ingest() -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as nc:
                await nc.post(f"{NOTIFICATION_BUS_URL}/notify", json={
                    "type": "memory_ingested",
                    "title": "Memory ingested",
                    "body": summary[:80],
                    "source": "memory-service",
                    "severity": "info",
                })
        except Exception:
            pass

    notify_task = asyncio.create_task(_notify_ingest())
    _BACKGROUND_TASKS.add(notify_task)
    notify_task.add_done_callback(_BACKGROUND_TASKS.discard)
    return {"id": created["id"]}


@app.post("/session/start")
async def session_start(req: SessionStartRequest) -> dict[str, Any]:
    await _init_db()
    session_id = str(uuid.uuid4())
    now = _now_iso()

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO sessions (id, user_id, started_at, ended_at, summary, task_count) VALUES (?, ?, ?, NULL, NULL, 0)",
                (session_id, req.user_id, now),
            )
            await db.commit()
        return {"session_id": session_id}

    def _sync_start() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                "INSERT INTO sessions (id, user_id, started_at, ended_at, summary, task_count) VALUES (?, ?, ?, NULL, NULL, 0)",
                (session_id, req.user_id, now),
            )
            conn.commit()
        finally:
            conn.close()

    import asyncio

    await asyncio.to_thread(_sync_start)
    return {"session_id": session_id}


@app.post("/session/end")
async def session_end(req: SessionEndRequest) -> dict[str, Any]:
    await _init_db()
    now = _now_iso()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "UPDATE sessions SET ended_at = ?, summary = COALESCE(?, summary), task_count = (SELECT COUNT(*) FROM memories WHERE type='task' AND created_at >= sessions.started_at) WHERE id = ?",
                (now, req.summary, req.session_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="session not found")
            await db.commit()
        return {"ok": True}

    def _sync_end() -> bool:
        conn = sqlite3.connect(DB_PATH)
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE sessions SET ended_at = ?, summary = COALESCE(?, summary), task_count = (SELECT COUNT(*) FROM memories WHERE type='task' AND created_at >= sessions.started_at) WHERE id = ?",
                (now, req.summary, req.session_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    import asyncio

    ok = await asyncio.to_thread(_sync_end)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}


@app.get("/session/list")
async def session_list(user_id: str = "default", limit: int = 20) -> dict[str, Any]:
    await _init_db()
    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, user_id, started_at, ended_at, summary, task_count FROM sessions WHERE user_id = ? ORDER BY started_at DESC LIMIT ?",
                (user_id, limit),
            )
            rows = await cur.fetchall()
        return {"sessions": [dict(r) for r in rows]}

    def _sync_list() -> list[dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT id, user_id, started_at, ended_at, summary, task_count FROM sessions WHERE user_id = ? ORDER BY started_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    import asyncio

    return {"sessions": await asyncio.to_thread(_sync_list)}


@app.get("/context/build")
async def context_build(q: str, user_id: str = "default", max_tokens: int = 1500) -> dict[str, Any]:
    search = await search_memory(q=q, user_id=user_id, top_k=20, type=None)
    lines = ["## User Memory Context"]
    for item in search["results"]:
        tags = ", ".join(item.get("tags", []))
        tail = f" [tags: {tags}]" if tags else ""
        lines.append(f"- ({item['type']}) {item['content']}{tail}")
    context = "\n".join(lines)
    if len(context) > max_tokens:
        context = context[:max_tokens]
    return {"context": context}


@app.get("/memories/by-persona/{persona_id}")
async def memories_by_persona(persona_id: str, limit: int = Query(500, ge=1, le=5000)) -> dict[str, Any]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT id, user_id, persona_id, type, content, tags, importance, access_count, created_at, updated_at
            FROM memories
            WHERE persona_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (persona_id, limit),
        )
        rows = await cur.fetchall()
        await cur.close()

    memories = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item.get("tags") or "[]")
        memories.append(item)
    return {"memories": memories, "total": len(memories)}


@app.get("/memories/topics/{persona_id}")
async def memories_topics(persona_id: str) -> dict[str, Any]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT tags, created_at
            FROM memories
            WHERE persona_id = ?
            ORDER BY created_at DESC
            """,
            (persona_id,),
        )
        rows = await cur.fetchall()
        await cur.close()

    topic_counts: dict[str, int] = {}
    last_seen: dict[str, str] = {}
    for row in rows:
        created_at = str(row["created_at"])
        tags = json.loads(row["tags"] or "[]")
        for tag in tags:
            topic = str(tag).strip().lower()
            if not topic:
                continue
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
            if topic not in last_seen or created_at > last_seen[topic]:
                last_seen[topic] = created_at

    ordered = sorted(topic_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    return {
        "topics": [
            {"topic": topic, "count": count, "last_seen": last_seen.get(topic)}
            for topic, count in ordered
        ]
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    await _init_db()
    return {"status": "ok"}
