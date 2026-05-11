"""SQLite persistence for BIOS AI stage 2."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BrainDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS boot_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    repairs_made INTEGER NOT NULL,
                    boot_time_ms INTEGER NOT NULL,
                    hardware_score REAL NOT NULL,
                    stage1_ran INTEGER NOT NULL,
                    stage2_complete INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS repairs (
                    item_id TEXT PRIMARY KEY,
                    scan_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    path TEXT NOT NULL,
                    issue_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    zone TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approved INTEGER,
                    message TEXT
                );

                CREATE TABLE IF NOT EXISTS scans (
                    scan_id TEXT PRIMARY KEY,
                    ts TEXT NOT NULL,
                    status TEXT NOT NULL,
                    issues_found INTEGER NOT NULL DEFAULT 0,
                    issues_fixed INTEGER NOT NULL DEFAULT 0,
                    issues_pending_approval INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS hardware_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )
            await db.commit()

    async def add_boot_history(
        self,
        *,
        decision: str,
        repairs_made: int,
        boot_time_ms: int,
        hardware_score: float,
        stage1_ran: bool,
        stage2_complete: bool,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO boot_history
                (ts, decision, repairs_made, boot_time_ms, hardware_score, stage1_ran, stage2_complete)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now(),
                    decision,
                    repairs_made,
                    boot_time_ms,
                    float(hardware_score),
                    int(stage1_ran),
                    int(stage2_complete),
                ),
            )
            await db.commit()

    async def list_boot_history(self, limit: int = 30) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT ts, decision, repairs_made, boot_time_ms, hardware_score
                FROM boot_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cur.fetchall()
            await cur.close()
        return [dict(r) for r in rows]

    async def save_hardware_snapshot(self, payload: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO hardware_snapshots (ts, payload_json) VALUES (?, ?)",
                (_utc_now(), json.dumps(payload)),
            )
            await db.commit()

    async def create_scan(self, scan_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO scans (scan_id, ts, status) VALUES (?, ?, 'running')",
                (scan_id, _utc_now()),
            )
            await db.commit()

    async def set_scan_status(
        self,
        scan_id: str,
        *,
        status: str,
        issues_found: int | None = None,
        issues_fixed: int | None = None,
        issues_pending_approval: int | None = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE scans
                SET status = ?,
                    issues_found = COALESCE(?, issues_found),
                    issues_fixed = COALESCE(?, issues_fixed),
                    issues_pending_approval = COALESCE(?, issues_pending_approval)
                WHERE scan_id = ?
                """,
                (status, issues_found, issues_fixed, issues_pending_approval, scan_id),
            )
            await db.commit()

    async def get_scan(self, scan_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM scans WHERE scan_id = ?", (scan_id,))
            row = await cur.fetchone()
            await cur.close()
        return dict(row) if row else None

    async def add_repair_item(
        self,
        *,
        item_id: str,
        scan_id: str,
        path: str,
        issue_type: str,
        action: str,
        zone: str,
        status: str,
        approved: bool | None,
        message: str = "",
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO repairs
                (item_id, scan_id, ts, path, issue_type, action, zone, status, approved, message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    scan_id,
                    _utc_now(),
                    path,
                    issue_type,
                    action,
                    zone,
                    status,
                    None if approved is None else int(approved),
                    message,
                ),
            )
            await db.commit()

    async def update_repair_item(
        self,
        item_id: str,
        *,
        status: str,
        approved: bool | None = None,
        message: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE repairs
                SET status = ?,
                    approved = COALESCE(?, approved),
                    message = COALESCE(?, message)
                WHERE item_id = ?
                """,
                (status, None if approved is None else int(approved), message, item_id),
            )
            await db.commit()

    async def get_repair_item(self, item_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM repairs WHERE item_id = ?", (item_id,))
            row = await cur.fetchone()
            await cur.close()
        if not row:
            return None
        item = dict(row)
        if item["approved"] is not None:
            item["approved"] = bool(item["approved"])
        return item

    async def list_scan_items(self, scan_id: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT item_id, path, issue_type, action, zone, status, approved, message FROM repairs WHERE scan_id = ?",
                (scan_id,),
            )
            rows = await cur.fetchall()
            await cur.close()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if item["approved"] is not None:
                item["approved"] = bool(item["approved"])
            out.append(item)
        return out


def serialize(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    raise TypeError("Unsupported value for serialization")
