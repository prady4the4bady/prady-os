from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from alert_engine import Alert
from sensor_reader import HardwareSnapshot

DB_PATH = '/data/hardware_intel/metrics.db'


class MetricsDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        await self._conn.execute('PRAGMA journal_mode=WAL')
        await self._conn.execute('PRAGMA foreign_keys=ON')
        await self._conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS hardware_snapshots (
              snapshot_id TEXT PRIMARY KEY,
              ts TEXT NOT NULL,
              cpu_temp_c REAL,
              cpu_usage_pct REAL,
              cpu_freq_mhz REAL,
              cpu_throttled INTEGER,
              mem_total_mb INTEGER,
              mem_used_mb INTEGER,
              mem_available_mb INTEGER,
              mem_pressure TEXT,
              disk_data TEXT,
              battery_pct REAL,
              battery_status TEXT,
              net_data TEXT,
              gpu_temp_c REAL,
              gpu_usage_pct REAL,
              health_score REAL,
              anomaly_score REAL,
              anomaly_detected INTEGER
            );

            CREATE TABLE IF NOT EXISTS alerts (
              alert_id TEXT PRIMARY KEY,
              severity TEXT NOT NULL,
              component TEXT NOT NULL,
              message TEXT NOT NULL,
              first_seen TEXT NOT NULL,
              last_seen TEXT NOT NULL,
              count INTEGER DEFAULT 1,
              resolved INTEGER DEFAULT 0
            );
            '''
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def store_snapshot(self, snapshot: HardwareSnapshot) -> str:
        assert self._conn is not None
        snapshot_id = str(uuid.uuid4())
        await self._conn.execute(
            '''
            INSERT INTO hardware_snapshots (
              snapshot_id, ts, cpu_temp_c, cpu_usage_pct, cpu_freq_mhz,
              cpu_throttled, mem_total_mb, mem_used_mb, mem_available_mb,
              mem_pressure, disk_data, battery_pct, battery_status, net_data,
              gpu_temp_c, gpu_usage_pct, health_score, anomaly_score, anomaly_detected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                snapshot_id,
                snapshot.ts,
                snapshot.cpu.temp_c,
                snapshot.cpu.usage_pct,
                snapshot.cpu.freq_mhz,
                int(snapshot.cpu.throttled),
                snapshot.memory.total_mb,
                snapshot.memory.used_mb,
                snapshot.memory.available_mb,
                snapshot.memory.pressure,
                json.dumps([d.__dict__ for d in snapshot.disks]),
                snapshot.battery.pct,
                snapshot.battery.status,
                json.dumps([n.__dict__ for n in snapshot.network]),
                snapshot.gpu.temp_c,
                snapshot.gpu.usage_pct,
                snapshot.health_score,
                snapshot.anomaly_score,
                int(snapshot.anomaly_detected),
            ),
        )
        await self._conn.commit()
        return snapshot_id

    async def get_history(self, metric: str, hours: int = 24) -> list[dict[str, Any]]:
        assert self._conn is not None
        if metric not in {'cpu_temp', 'memory_used', 'disk_pct', 'battery_pct'}:
            raise ValueError('invalid metric')

        if metric == 'disk_pct':
            cur = await self._conn.execute(
                "SELECT ts, disk_data FROM hardware_snapshots WHERE ts >= datetime('now', ?) ORDER BY ts ASC",
                (f'-{hours} hours',),
            )
            rows = await cur.fetchall()
            out: list[dict[str, Any]] = []
            for ts, disk_json in rows:
                max_pct = 0.0
                try:
                    disks = json.loads(disk_json or '[]')
                    max_pct = max((float(d.get('pct', 0.0)) for d in disks), default=0.0)
                except Exception:
                    max_pct = 0.0
                out.append({'ts': ts, 'value': max_pct})
            return out

        column_map = {
            'cpu_temp': 'cpu_temp_c',
            'memory_used': 'mem_used_mb',
            'battery_pct': 'battery_pct',
        }
        col = column_map[metric]
        cur = await self._conn.execute(
            f"SELECT ts, {col} FROM hardware_snapshots WHERE ts >= datetime('now', ?) ORDER BY ts ASC",
            (f'-{hours} hours',),
        )
        rows = await cur.fetchall()
        return [{'ts': r[0], 'value': float(r[1]) if r[1] is not None else 0.0} for r in rows]

    async def get_snapshots_since(self, hours: int) -> list[dict[str, Any]]:
        assert self._conn is not None
        self._conn.row_factory = aiosqlite.Row
        cur = await self._conn.execute(
            "SELECT * FROM hardware_snapshots WHERE ts >= datetime('now', ?) ORDER BY ts ASC",
            (f'-{hours} hours',),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def store_alert(self, alert: Alert) -> None:
        assert self._conn is not None
        await self._conn.execute(
            '''
            INSERT OR REPLACE INTO alerts
            (alert_id, severity, component, message, first_seen, last_seen, count, resolved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                alert.alert_id,
                alert.severity,
                alert.component,
                alert.message,
                alert.first_seen,
                alert.last_seen,
                alert.count,
                int(alert.resolved),
            ),
        )
        await self._conn.commit()

    async def update_alert(self, alert: Alert) -> None:
        assert self._conn is not None
        await self._conn.execute(
            'UPDATE alerts SET last_seen = ?, count = ?, resolved = ? WHERE alert_id = ?',
            (alert.last_seen, alert.count, int(alert.resolved), alert.alert_id),
        )
        await self._conn.commit()

    async def get_active_alerts(self) -> list[dict[str, Any]]:
        assert self._conn is not None
        self._conn.row_factory = aiosqlite.Row
        cur = await self._conn.execute('SELECT * FROM alerts WHERE resolved = 0 ORDER BY first_seen DESC')
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def dismiss_alert(self, alert_id: str) -> bool:
        assert self._conn is not None
        cur = await self._conn.execute('UPDATE alerts SET resolved = 1 WHERE alert_id = ?', (alert_id,))
        await self._conn.commit()
        return cur.rowcount > 0

    async def get_alert_count(self) -> int:
        assert self._conn is not None
        cur = await self._conn.execute('SELECT COUNT(*) FROM alerts WHERE resolved = 0')
        row = await cur.fetchone()
        return int(row[0]) if row else 0
