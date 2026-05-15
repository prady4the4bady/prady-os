"""SQLite persistence for Neila retry queue and scheduled actions.

Replaces the previous in-memory-only storage so that pending retries and
schedules survive process restarts.  Backoff counters and states are
preserved in the database.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from app.models import RetryEntry, RetryState, ScheduledAction

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("NEILA_DB_PATH", "/data/neila.db")


class NeilaStore:
    """Thread-safe SQLite store for retry queue and scheduled actions."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
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
        with self._lock:
            c = self._conn()
            c.execute("""
                CREATE TABLE IF NOT EXISTS retry_queue (
                    id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_ts TEXT NOT NULL DEFAULT '',
                    next_attempt_ts TEXT NOT NULL DEFAULT ''
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_actions (
                    id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    due_ts TEXT NOT NULL DEFAULT '',
                    trigger_ts TEXT NOT NULL DEFAULT '',
                    completed INTEGER NOT NULL DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS followup_candidates (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'neila',
                    title TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL DEFAULT 'info',
                    created_ts TEXT NOT NULL DEFAULT '',
                    processed INTEGER NOT NULL DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS digest_candidates (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'neila',
                    summary TEXT NOT NULL DEFAULT '',
                    cycle INTEGER NOT NULL DEFAULT 0,
                    created_ts TEXT NOT NULL DEFAULT '',
                    processed INTEGER NOT NULL DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS deadletters (
                    id TEXT PRIMARY KEY,
                    source_retry_id TEXT NOT NULL DEFAULT '',
                    task_type TEXT NOT NULL DEFAULT '',
                    target_url TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    last_error TEXT NOT NULL DEFAULT '',
                    failed_at TEXT NOT NULL DEFAULT '',
                    replay_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            self._conn().commit()

    # --- Retry queue ---

    def enqueue(self, entry: RetryEntry) -> None:
        with self._lock:
            self._conn().execute(
                """INSERT OR REPLACE INTO retry_queue
                   (id, task_type, target_url, payload, max_retries, attempt,
                    state, last_error, created_ts, next_attempt_ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.id, entry.task_type, entry.target_url,
                    json.dumps(entry.payload), entry.max_retries, entry.attempt,
                    entry.state.value, entry.last_error, entry.created_ts,
                    entry.next_attempt_ts,
                ),
            )
            self._conn().commit()

    def dequeue(self, entry_id: str) -> None:
        with self._lock:
            self._conn().execute("DELETE FROM retry_queue WHERE id = ?", (entry_id,))
            self._conn().commit()

    def update(self, entry: RetryEntry) -> None:
        self.enqueue(entry)

    def list_pending(self) -> list[RetryEntry]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM retry_queue ORDER BY created_ts ASC"
            ).fetchall()
        result = []
        for r in rows:
            result.append(RetryEntry(
                id=r["id"],
                task_type=r["task_type"],
                target_url=r["target_url"],
                payload=json.loads(r["payload"]) if r["payload"] else {},
                max_retries=r["max_retries"],
                attempt=r["attempt"],
                state=RetryState(r["state"]),
                last_error=r["last_error"],
                created_ts=r["created_ts"],
                next_attempt_ts=r["next_attempt_ts"],
            ))
        return result

    def clear_retries(self) -> None:
        with self._lock:
            self._conn().execute("DELETE FROM retry_queue")
            self._conn().commit()

    def retry_count(self) -> int:
        with self._lock:
            row = self._conn().execute("SELECT COUNT(*) AS cnt FROM retry_queue").fetchone()
            return row["cnt"] if row else 0

    # --- Scheduled actions ---

    def add_schedule(self, action: ScheduledAction) -> None:
        with self._lock:
            self._conn().execute(
                """INSERT OR REPLACE INTO scheduled_actions
                   (id, action_type, target_url, payload, due_ts, trigger_ts, completed)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    action.id, action.action_type, action.target_url,
                    json.dumps(action.payload), action.due_ts,
                    action.trigger_ts, 1 if action.completed else 0,
                ),
            )
            self._conn().commit()

    def update_schedule(self, action: ScheduledAction) -> None:
        self.add_schedule(action)

    def list_pending_schedules(self) -> list[ScheduledAction]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM scheduled_actions WHERE completed = 0 ORDER BY due_ts ASC"
            ).fetchall()
        result = []
        for r in rows:
            result.append(ScheduledAction(
                id=r["id"],
                action_type=r["action_type"],
                target_url=r["target_url"],
                payload=json.loads(r["payload"]) if r["payload"] else {},
                due_ts=r["due_ts"],
                trigger_ts=r["trigger_ts"],
                completed=bool(r["completed"]),
            ))
        return result

    def clear_schedules(self) -> None:
        with self._lock:
            self._conn().execute("DELETE FROM scheduled_actions")
            self._conn().commit()

    def scheduled_count(self) -> int:
        with self._lock:
            row = self._conn().execute(
                "SELECT COUNT(*) AS cnt FROM scheduled_actions WHERE completed = 0"
            ).fetchone()
            return row["cnt"] if row else 0

    # --- Follow-up candidates ---

    def add_followup(self, source: str, title: str, body: str, severity: str = "info") -> str:
        import uuid
        fid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn().execute(
                """INSERT INTO followup_candidates
                   (id, source, title, body, severity, created_ts, processed)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (fid, source, title, body, severity, now),
            )
            self._conn().commit()
        return fid

    def list_followups(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM followup_candidates ORDER BY created_ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_followup_processed(self, fid: str) -> None:
        with self._lock:
            self._conn().execute(
                "UPDATE followup_candidates SET processed = 1 WHERE id = ?",
                (fid,),
            )
            self._conn().commit()

    # --- Digest candidates ---

    def add_digest(self, source: str, summary: str, cycle: int) -> str:
        import uuid
        did = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn().execute(
                """INSERT INTO digest_candidates
                   (id, source, summary, cycle, created_ts, processed)
                   VALUES (?, ?, ?, ?, ?, 0)""",
                (did, source, summary, cycle, now),
            )
            self._conn().commit()
        return did

    def list_digests(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM digest_candidates ORDER BY created_ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Dead-letter queue ---

    def add_deadletter(self, source_retry_id: str, task_type: str, target_url: str, payload: dict[str, Any], last_error: str) -> str:
        import uuid
        did = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn().execute(
                """INSERT INTO deadletters
                   (id, source_retry_id, task_type, target_url, payload_json, last_error, failed_at, replay_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                (did, source_retry_id, task_type, target_url, json.dumps(payload), last_error, now),
            )
            self._conn().commit()
        return did

    def list_deadletters(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM deadletters ORDER BY failed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_deadletter(self, deadletter_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM deadletters WHERE id = ?", (deadletter_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_deadletter(self, deadletter_id: str) -> bool:
        with self._lock:
            c = self._conn().execute("DELETE FROM deadletters WHERE id = ?", (deadletter_id,))
            deleted = c.rowcount > 0
            self._conn().commit()
            return deleted

    def increment_replay(self, deadletter_id: str) -> None:
        with self._lock:
            self._conn().execute(
                "UPDATE deadletters SET replay_count = replay_count + 1 WHERE id = ?",
                (deadletter_id,),
            )
            self._conn().commit()

    def deadletter_count(self) -> int:
        with self._lock:
            row = self._conn().execute("SELECT COUNT(*) AS cnt FROM deadletters").fetchone()
            return row["cnt"] if row else 0

    def last_deadletter_ts(self) -> str:
        with self._lock:
            row = self._conn().execute(
                "SELECT failed_at FROM deadletters ORDER BY failed_at DESC LIMIT 1"
            ).fetchone()
            return row["failed_at"] if row else ""

    def clear_deadletters(self) -> None:
        with self._lock:
            self._conn().execute("DELETE FROM deadletters")
            self._conn().commit()

    # --- Restore ---

    def restore(self) -> tuple[list[RetryEntry], list[ScheduledAction]]:
        retries = self.list_pending()
        schedules = self.list_pending_schedules()
        logger.info(
            "NeilaStore restored: %d retries, %d pending schedules",
            len(retries), len(schedules),
        )
        return retries, schedules

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
