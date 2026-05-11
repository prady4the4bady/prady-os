from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query

from alert_engine import Alert, AlertEngine
from anomaly_detector import AnomalyDetector
from metrics_db import MetricsDB
from sensor_reader import (
    BatteryMetrics,
    CPUMetrics,
    DiskMetrics,
    GPUMetrics,
    HardwareSnapshot,
    MemoryMetrics,
    NetworkMetrics,
    SensorReader,
)

VERSION = '1.0.0'
SERVICE_NAME = 'hardware-intel'

DATA_DIR = Path(os.environ.get('DATA_DIR', '/data/hardware_intel'))
DB_PATH = str(DATA_DIR / 'metrics.db')
AUDIT_LOG_URL = os.environ.get('AUDIT_LOG_URL', 'http://audit-log:8006')
NOTIFICATION_BUS_URL = os.environ.get('NOTIFICATION_BUS_URL', 'http://notification-bus:8007')
SENSOR_POLL_INTERVAL = int(os.environ.get('SENSOR_POLL_INTERVAL', '30'))
ANOMALY_THRESHOLD = float(os.environ.get('ANOMALY_THRESHOLD', '0.3'))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_from_row(row: dict[str, Any]) -> HardwareSnapshot:
    import json

    disks_raw = json.loads(row.get('disk_data') or '[]')
    net_raw = json.loads(row.get('net_data') or '[]')

    return HardwareSnapshot(
        cpu=CPUMetrics(
            temp_c=row.get('cpu_temp_c'),
            usage_pct=float(row.get('cpu_usage_pct') or 0.0),
            freq_mhz=float(row.get('cpu_freq_mhz') or 0.0),
            cores=1,
            throttled=bool(row.get('cpu_throttled') or 0),
        ),
        memory=MemoryMetrics(
            total_mb=int(row.get('mem_total_mb') or 1),
            used_mb=int(row.get('mem_used_mb') or 0),
            available_mb=int(row.get('mem_available_mb') or 1),
            swap_used_mb=0,
            pressure=row.get('mem_pressure') or 'low',
        ),
        disks=[DiskMetrics(**d) for d in disks_raw],
        battery=BatteryMetrics(
            present=row.get('battery_pct') is not None,
            pct=float(row.get('battery_pct')) if row.get('battery_pct') is not None else None,
            status=row.get('battery_status') or 'unknown',
            time_remaining_min=None,
            health_pct=None,
        ),
        network=[NetworkMetrics(**n) for n in net_raw],
        gpu=GPUMetrics(
            present=row.get('gpu_temp_c') is not None or row.get('gpu_usage_pct') is not None,
            vendor=None,
            model=None,
            temp_c=float(row.get('gpu_temp_c')) if row.get('gpu_temp_c') is not None else None,
            usage_pct=float(row.get('gpu_usage_pct')) if row.get('gpu_usage_pct') is not None else None,
            vram_used_mb=None,
        ),
        ts=row.get('ts') or _iso_now(),
        health_score=float(row.get('health_score') or 0.0),
        anomaly_score=float(row.get('anomaly_score') or 0.5),
        anomaly_detected=bool(row.get('anomaly_detected') or 0),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    app.state.detector = AnomalyDetector()
    app.state.detector.load()
    app.state.metrics_db = MetricsDB(db_path=DB_PATH)
    await app.state.metrics_db.init()
    app.state.alert_engine = AlertEngine(notify_url=NOTIFICATION_BUS_URL, audit_url=AUDIT_LOG_URL)
    app.state.reader = SensorReader(anomaly_detector=app.state.detector)
    app.state.cache_snapshot: dict[str, Any] | None = None
    app.state.cache_ts = 0.0
    app.state.poll_task = asyncio.create_task(_poll_loop(app))

    yield

    app.state.poll_task.cancel()
    await app.state.metrics_db.close()


app = FastAPI(title='Kryos Hardware Intel', version=VERSION, lifespan=lifespan)


async def _persist_alerts(app: FastAPI, alerts: list[Alert]) -> None:
    for a in alerts:
        await app.state.metrics_db.store_alert(a)
        await app.state.alert_engine.post_to_notify(a)
        await app.state.alert_engine.post_to_audit(a)


async def _capture_snapshot(app: FastAPI) -> HardwareSnapshot:
    snapshot = await app.state.reader.read_all()
    if snapshot.anomaly_score < ANOMALY_THRESHOLD:
        snapshot.anomaly_detected = True
    await app.state.metrics_db.store_snapshot(snapshot)

    new_alerts = app.state.alert_engine.evaluate(snapshot)
    await _persist_alerts(app, new_alerts)

    # sync active alert counters into DB
    for active in app.state.alert_engine.get_active_alerts():
        await app.state.metrics_db.update_alert(active)

    app.state.cache_snapshot = asdict(snapshot)
    app.state.cache_ts = asyncio.get_event_loop().time()
    return snapshot


async def _poll_loop(app: FastAPI) -> None:
    while True:
        try:
            await _capture_snapshot(app)
        except Exception:
            pass
        await asyncio.sleep(max(5, SENSOR_POLL_INTERVAL))


@app.get('/hardware/current')
async def hardware_current() -> dict[str, Any]:
    now = asyncio.get_event_loop().time()
    if app.state.cache_snapshot is not None and (now - app.state.cache_ts) <= 5.0:
        return app.state.cache_snapshot

    snapshot = await _capture_snapshot(app)
    return asdict(snapshot)


@app.get('/hardware/history')
async def hardware_history(
    metric: Literal['cpu_temp', 'memory_used', 'disk_pct', 'battery_pct'],
    hours: int = Query(default=24, ge=1, le=168),
) -> dict[str, Any]:
    points = await app.state.metrics_db.get_history(metric=metric, hours=hours)
    return {'metric': metric, 'points': points}


@app.get('/hardware/alerts')
async def hardware_alerts() -> list[dict[str, Any]]:
    rows = await app.state.metrics_db.get_active_alerts()
    return [
        {
            'alert_id': r['alert_id'],
            'severity': r['severity'],
            'component': r['component'],
            'message': r['message'],
            'first_seen': r['first_seen'],
            'last_seen': r['last_seen'],
            'count': r['count'],
        }
        for r in rows
    ]


@app.post('/hardware/alerts/{alert_id}/dismiss')
async def hardware_alert_dismiss(alert_id: str) -> dict[str, bool]:
    dismissed = await app.state.metrics_db.dismiss_alert(alert_id)
    if dismissed:
        app.state.alert_engine.dismiss(alert_id)
        return {'dismissed': True}
    raise HTTPException(status_code=404, detail='alert not found')


@app.get('/hardware/baseline')
async def hardware_baseline() -> dict[str, Any]:
    return {
        'samples_trained': int(app.state.detector.samples_trained),
        'last_trained_ts': app.state.detector.last_trained_ts,
        'contamination': app.state.detector.contamination,
        'features_used': ['cpu_temp_c', 'cpu_usage_pct', 'mem_used_pct', 'disk_pct_max', 'battery_pct', 'net_bytes_recv_ps_total'],
    }


@app.post('/hardware/baseline/train')
async def hardware_baseline_train() -> dict[str, Any]:
    rows = await app.state.metrics_db.get_snapshots_since(hours=24 * 7)
    snapshots = [_snapshot_from_row(r) for r in rows]
    result = app.state.detector.train(snapshots)
    return {
        'job_id': str(uuid.uuid4()),
        'samples_used': result.samples,
        'status': 'complete',
    }


@app.get('/health')
async def health() -> dict[str, str]:
    return {'status': 'ok', 'service': SERVICE_NAME, 'version': VERSION}
