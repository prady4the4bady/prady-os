from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SlotManager:
    def __init__(
        self,
        db_path: str | Path,
        grubenv_path: str | Path = "/tmp/grubenv",
    ) -> None:
        self.db_path = Path(db_path)
        self.grubenv_path = Path(grubenv_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS ota_state (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            active_slot TEXT NOT NULL,
            standby_slot TEXT NOT NULL,
            active_version TEXT NOT NULL,
            standby_version TEXT,
            boot_fail_count INTEGER NOT NULL,
            state TEXT NOT NULL,
            last_update_ts TEXT,
            last_check_ts TEXT,
            update_history TEXT NOT NULL
        );
        """

        with self._connect() as conn:
            conn.execute(ddl)
            existing = conn.execute("SELECT singleton_id FROM ota_state WHERE singleton_id = 1").fetchone()
            if not existing:
                conn.execute(
                    """
                    INSERT INTO ota_state (
                        singleton_id, active_slot, standby_slot, active_version,
                        standby_version, boot_fail_count, state, last_update_ts,
                        last_check_ts, update_history
                    ) VALUES (1, 'a', 'b', '1.0.0', NULL, 0, 'IDLE', ?, NULL, '[]')
                    """,
                    (self._now_iso(),),
                )
            conn.commit()

    def _write_grubenv(self, slot: str) -> None:
        self.grubenv_path.parent.mkdir(parents=True, exist_ok=True)
        self.grubenv_path.write_text(f"next_entry=kryos_slot_{slot}\n", encoding="utf-8")

    def _append_history(self, status: str, version: str, slot: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT update_history FROM ota_state WHERE singleton_id = 1").fetchone()
            history = json.loads(row["update_history"] if row else "[]")
            history.append({
                "version": version,
                "ts": self._now_iso(),
                "status": status,
                "slot": slot,
            })
            conn.execute(
                "UPDATE ota_state SET update_history = ?, last_update_ts = ? WHERE singleton_id = 1",
                (json.dumps(history), self._now_iso()),
            )
            conn.commit()

    def set_state(self, state: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE ota_state SET state = ? WHERE singleton_id = 1", (state,))
            conn.commit()

    def set_last_check(self, timestamp: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE ota_state SET last_check_ts = ? WHERE singleton_id = 1", (timestamp,))
            conn.commit()

    def set_standby_version(self, version: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE ota_state SET standby_version = ? WHERE singleton_id = 1", (version,))
            conn.commit()

    def mark_committed(self, version: str) -> dict[str, Any]:
        state = self.get_state()
        next_slot = state["standby_slot"]
        self._write_grubenv(next_slot)
        with self._connect() as conn:
            conn.execute(
                "UPDATE ota_state SET standby_version = ?, state = 'COMMITTED', last_update_ts = ? WHERE singleton_id = 1",
                (version, self._now_iso()),
            )
            conn.commit()
        self._append_history("committed", version, next_slot)
        return self.get_state()

    def get_state(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ota_state WHERE singleton_id = 1").fetchone()
            if row is None:
                raise RuntimeError("ota_state not initialized")
            data = dict(row)
            data["update_history"] = json.loads(data.get("update_history") or "[]")
            return data

    def switch_slot(self) -> dict[str, Any]:
        state = self.get_state()
        new_active = state["standby_slot"]
        new_standby = state["active_slot"]
        new_active_version = state.get("standby_version") or state["active_version"]
        new_standby_version = state["active_version"]

        self._write_grubenv(new_active)

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE ota_state
                SET active_slot = ?, standby_slot = ?, active_version = ?, standby_version = ?,
                    boot_fail_count = 0, state = 'REBOOTING', last_update_ts = ?
                WHERE singleton_id = 1
                """,
                (new_active, new_standby, new_active_version, new_standby_version, self._now_iso()),
            )
            conn.commit()

        self._append_history("switched", str(new_active_version), new_active)
        return self.get_state()

    def rollback(self) -> dict[str, Any]:
        state = self.get_state()
        rolled = False

        if state["active_slot"] != "a":
            self.switch_slot()
            rolled = True

        with self._connect() as conn:
            conn.execute(
                "UPDATE ota_state SET state = 'IDLE', boot_fail_count = 0, last_update_ts = ? WHERE singleton_id = 1",
                (self._now_iso(),),
            )
            conn.commit()

        updated = self.get_state()
        self._write_grubenv(updated["active_slot"])
        if rolled:
            self._append_history("rolled_back", updated["active_version"], updated["active_slot"])
        return updated

    def record_boot_health(self, success: bool) -> dict[str, Any]:
        state = self.get_state()
        fail_count = int(state["boot_fail_count"])

        if success:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE ota_state SET boot_fail_count = 0, state = 'IDLE', last_check_ts = ? WHERE singleton_id = 1",
                    (self._now_iso(),),
                )
                conn.commit()
            return {**self.get_state(), "rolled_back": False}

        fail_count += 1
        with self._connect() as conn:
            conn.execute(
                "UPDATE ota_state SET boot_fail_count = ?, last_check_ts = ? WHERE singleton_id = 1",
                (fail_count, self._now_iso()),
            )
            conn.commit()

        if fail_count >= 3:
            rolled = self.rollback()
            return {**rolled, "rolled_back": True}

        return {**self.get_state(), "rolled_back": False}
