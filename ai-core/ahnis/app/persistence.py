"""SQLite-backed persistence for Ahnis memory entries.

Writes are synchronous to both in-memory cache and SQLite.
On startup, entries are restored into the memory cache.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("AHNIS_DB_PATH", "/data/ahnis.db")


class AhnisStore:
    """Thread-safe SQLite store for Ahnis memory entries."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._available = False
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    def _init_schema(self) -> None:
        try:
            with self._lock:
                c = self._conn()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS memory_entries (
                        id TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        timestamp TEXT NOT NULL DEFAULT '',
                        relevance REAL NOT NULL DEFAULT 0.0,
                        embedding_json TEXT,
                        embedding_backend TEXT NOT NULL DEFAULT ''
                    )
                """)
                c.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memory_category
                    ON memory_entries(category)
                """)
                self._conn().commit()
                self._available = True
        except Exception as exc:
            logger.warning("AhnisStore schema init failed: %s", exc)
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def db_path(self) -> str:
        return self._db_path

    def save_entry(self, entry: dict[str, Any]) -> None:
        if not self._available:
            return
        try:
            with self._lock:
                emb_json = json.dumps(entry.get("embedding")) if entry.get("embedding") else None
                meta_json = json.dumps(entry.get("metadata", {}))
                self._conn().execute(
                    """INSERT OR REPLACE INTO memory_entries
                       (id, category, content, metadata_json, timestamp, relevance, embedding_json, embedding_backend)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry["id"], entry["category"], entry["content"],
                        meta_json, entry.get("timestamp", ""),
                        entry.get("relevance", 0.0), emb_json,
                        entry.get("embedding_backend", ""),
                    ),
                )
                self._conn().commit()
        except Exception as exc:
            logger.warning("AhnisStore save_entry failed: %s", exc)

    def delete_entry(self, entry_id: str) -> bool:
        if not self._available:
            return False
        try:
            with self._lock:
                c = self._conn().execute("DELETE FROM memory_entries WHERE id = ?", (entry_id,))
                deleted = c.rowcount > 0
                self._conn().commit()
                return deleted
        except Exception as exc:
            logger.warning("AhnisStore delete_entry failed: %s", exc)
            return False

    def list_entries(self, category: str | None = None, limit: int = 10000) -> list[dict[str, Any]]:
        if not self._available:
            return []
        try:
            with self._lock:
                if category:
                    rows = self._conn().execute(
                        "SELECT * FROM memory_entries WHERE category = ? ORDER BY timestamp ASC LIMIT ?",
                        (category, limit),
                    ).fetchall()
                else:
                    rows = self._conn().execute(
                        "SELECT * FROM memory_entries ORDER BY timestamp ASC LIMIT ?",
                        (limit,),
                    ).fetchall()
            result = []
            for r in rows:
                entry = {
                    "id": r["id"],
                    "category": r["category"],
                    "content": r["content"],
                    "metadata": json.loads(r["metadata_json"]) if r["metadata_json"] else {},
                    "timestamp": r["timestamp"],
                    "relevance": r["relevance"],
                    "embedding_backend": r["embedding_backend"],
                }
                if r["embedding_json"]:
                    entry["embedding"] = json.loads(r["embedding_json"])
                else:
                    entry["embedding"] = None
                result.append(entry)
            return result
        except Exception as exc:
            logger.warning("AhnisStore list_entries failed: %s", exc)
            return []

    def restore_entries(self) -> dict[str, list[dict[str, Any]]]:
        """Restore all entries from SQLite into in-memory category buckets."""
        if not self._available:
            return {}
        all_entries = self.list_entries()
        store: dict[str, list[dict[str, Any]]] = {}
        for entry in all_entries:
            cat = entry["category"]
            if cat not in store:
                store[cat] = []
            store[cat].append(entry)
        count = len(all_entries)
        logger.info("AhnisStore restored %d entries from %s", count, self._db_path)
        return store

    def persisted_count(self) -> int:
        if not self._available:
            return 0
        try:
            with self._lock:
                row = self._conn().execute("SELECT COUNT(*) AS cnt FROM memory_entries").fetchone()
                return row["cnt"] if row else 0
        except Exception:
            return 0

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
