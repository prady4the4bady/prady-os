from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

DB_PATH = "/data/sdk_registry/registry.db"


class RegistryDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS installed_apps (
              app_id TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              version TEXT NOT NULL,
              author TEXT NOT NULL,
              description TEXT,
              license TEXT,
              permissions TEXT,
              capabilities TEXT,
              manifest_json TEXT,
              status TEXT DEFAULT 'stopped',
              container_id TEXT,
              installed_ts TEXT NOT NULL,
              last_active_ts TEXT
            );
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def register_app(self, manifest: dict[str, Any]) -> str:
        assert self._conn is not None
        app_id = f"{manifest['name']}-{uuid.uuid4().hex[:8]}"
        now = "datetime('now')"
        await self._conn.execute(
            """
            INSERT INTO installed_apps
            (app_id, display_name, version, author, description, license, permissions, capabilities, manifest_json, status, container_id, installed_ts, last_active_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'stopped', NULL, datetime('now'), NULL)
            """,
            (
                app_id,
                manifest["display_name"],
                manifest["version"],
                manifest["author"],
                manifest.get("description"),
                manifest.get("license"),
                json.dumps(manifest.get("permissions", [])),
                json.dumps(manifest.get("capabilities", [])),
                json.dumps(manifest),
            ),
        )
        await self._conn.commit()
        return app_id

    async def get_app(self, app_id: str) -> dict[str, Any] | None:
        assert self._conn is not None
        self._conn.row_factory = aiosqlite.Row
        cur = await self._conn.execute("SELECT * FROM installed_apps WHERE app_id = ?", (app_id,))
        row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    async def get_all_apps(self) -> list[dict[str, Any]]:
        assert self._conn is not None
        self._conn.row_factory = aiosqlite.Row
        cur = await self._conn.execute("SELECT * FROM installed_apps ORDER BY installed_ts DESC")
        rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def get_apps_by_capability(self, capability: str) -> list[dict[str, Any]]:
        assert self._conn is not None
        self._conn.row_factory = aiosqlite.Row
        cur = await self._conn.execute(
            """
            SELECT DISTINCT installed_apps.*
            FROM installed_apps, json_each(installed_apps.capabilities)
            WHERE json_each.value = ?
            ORDER BY installed_apps.installed_ts DESC
            """,
            (capability,),
        )
        rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def update_status(self, app_id: str, status: str, container_id: str | None) -> None:
        assert self._conn is not None
        await self._conn.execute(
            "UPDATE installed_apps SET status = ?, container_id = ? WHERE app_id = ?",
            (status, container_id, app_id),
        )
        await self._conn.commit()

    async def update_last_active(self, app_id: str) -> None:
        assert self._conn is not None
        await self._conn.execute("UPDATE installed_apps SET last_active_ts = datetime('now') WHERE app_id = ?", (app_id,))
        await self._conn.commit()

    async def remove_app(self, app_id: str) -> bool:
        assert self._conn is not None
        cur = await self._conn.execute("DELETE FROM installed_apps WHERE app_id = ?", (app_id,))
        await self._conn.commit()
        return cur.rowcount > 0

    async def get_installed_count(self) -> int:
        assert self._conn is not None
        cur = await self._conn.execute("SELECT COUNT(*) FROM installed_apps")
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def get_running_count(self) -> int:
        assert self._conn is not None
        cur = await self._conn.execute("SELECT COUNT(*) FROM installed_apps WHERE status = 'running'")
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    def _row_to_dict(self, row: aiosqlite.Row) -> dict[str, Any]:
        data = dict(row)
        for key in ("permissions", "capabilities", "manifest_json"):
            if key in data and data[key] is not None:
                data[key] = json.loads(data[key]) if key != "manifest_json" else json.loads(data[key])
        return data
