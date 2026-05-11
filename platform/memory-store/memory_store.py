"""MemoryStore — async SQLite-backed persistent agent memory with FTS5 search."""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(
    os.getenv(
        "MEMORY_DB_PATH",
        str(Path(__file__).resolve().parent / "data" / "memory.db"),
    )
)
MAX_DB_SIZE_MB = 100
PRUNE_BATCH = 200


@dataclass
class MemoryEntry:
    id: str
    agent_id: str
    content: str
    tags: List[str]
    embedding: Optional[List[float]]
    created_at: float
    access_count: int

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tags"] = self.tags
        return d


_INIT_SQL = [
    """CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        content TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '[]',
        embedding TEXT,
        created_at REAL NOT NULL,
        access_count INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
        USING fts5(id UNINDEXED, content, tags, content=memories, content_rowid=rowid)""",
    """CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts(rowid, id, content, tags)
        VALUES (new.rowid, new.id, new.content, new.tags);
    END""",
    """CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts, rowid, id, content, tags)
        VALUES ('delete', old.rowid, old.id, old.content, old.tags);
    END""",
    "CREATE INDEX IF NOT EXISTS idx_agent ON memories(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_access ON memories(access_count)",
]


async def _init_db(conn: aiosqlite.Connection) -> None:
    for stmt in _INIT_SQL:
        await conn.execute(stmt)
    await conn.commit()


class MemoryStore:
    """Async SQLite memory store with FTS5 full-text search."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    async def store(self, agent_id: str, content: str, tags: Optional[List[str]] = None) -> MemoryEntry:
        if tags is None:
            tags = []
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            content=content,
            tags=tags,
            embedding=None,
            created_at=time.time(),
            access_count=0,
        )
        async with aiosqlite.connect(str(self._db_path)) as conn:
            await _init_db(conn)
            await conn.execute(
                "INSERT INTO memories (id, agent_id, content, tags, embedding, created_at, access_count)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.id,
                    entry.agent_id,
                    entry.content,
                    json.dumps(entry.tags),
                    None,
                    entry.created_at,
                    0,
                ),
            )
            await conn.commit()
        await self._maybe_prune()
        return entry

    async def search(self, agent_id: str, query: str, top_k: int = 10) -> List[MemoryEntry]:
        results: List[MemoryEntry] = []
        async with aiosqlite.connect(str(self._db_path)) as conn:
            await _init_db(conn)
            try:
                safe_q = query.replace('"', '""')
                cursor = await conn.execute(
                    """SELECT m.id, m.agent_id, m.content, m.tags, m.embedding,
                              m.created_at, m.access_count
                       FROM memories m
                       JOIN memories_fts ON memories_fts.id = m.id
                       WHERE memories_fts MATCH ? AND m.agent_id = ?
                       ORDER BY rank
                       LIMIT ?""",
                    (safe_q, agent_id, top_k),
                )
            except Exception:
                cursor = await conn.execute(
                    """SELECT id, agent_id, content, tags, embedding,
                              created_at, access_count
                       FROM memories
                       WHERE agent_id = ? AND (content LIKE ? OR tags LIKE ?)
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (agent_id, f"%{query}%", f"%{query}%", top_k),
                )
            rows = await cursor.fetchall()
            ids_found: List[str] = []
            for row in rows:
                e = MemoryEntry(
                    id=row[0],
                    agent_id=row[1],
                    content=row[2],
                    tags=json.loads(row[3]) if row[3] else [],
                    embedding=json.loads(row[4]) if row[4] else None,
                    created_at=row[5],
                    access_count=row[6] + 1,
                )
                results.append(e)
                ids_found.append(row[0])
            for mid in ids_found:
                await conn.execute(
                    "UPDATE memories SET access_count = access_count + 1 WHERE id = ?",
                    (mid,),
                )
            await conn.commit()
        return results

    async def delete(self, memory_id: str) -> bool:
        async with aiosqlite.connect(str(self._db_path)) as conn:
            await _init_db(conn)
            cursor = await conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            await conn.commit()
            return cursor.rowcount > 0

    async def stats(self) -> Dict[str, Any]:
        db_size_mb = 0.0
        if self._db_path.exists():
            db_size_mb = round(self._db_path.stat().st_size / (1024 * 1024), 4)
        async with aiosqlite.connect(str(self._db_path)) as conn:
            await _init_db(conn)
            cur = await conn.execute("SELECT COUNT(*) FROM memories")
            row = await cur.fetchone()
            total = row[0] if row else 0
            cur2 = await conn.execute("SELECT DISTINCT agent_id FROM memories")
            agents = [r[0] for r in await cur2.fetchall()]
        return {"total_entries": total, "db_size_mb": db_size_mb, "agents": agents}

    async def _maybe_prune(self) -> None:
        if not self._db_path.exists():
            return
        size_mb = self._db_path.stat().st_size / (1024 * 1024)
        if size_mb < MAX_DB_SIZE_MB:
            return
        logger.info("MemoryStore prune: %.1f MB > %d MB limit", size_mb, MAX_DB_SIZE_MB)
        async with aiosqlite.connect(str(self._db_path)) as conn:
            await conn.execute(
                """DELETE FROM memories WHERE id IN (
                    SELECT id FROM memories ORDER BY access_count ASC, created_at ASC LIMIT ?
                )""",
                (PRUNE_BATCH,),
            )
            await conn.commit()
