from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).resolve().parents[1]


def pytest_configure() -> None:
    service_dir = str(SERVICE_DIR)
    if service_dir not in sys.path:
        sys.path.insert(0, service_dir)


@pytest.fixture
def mock_snapshot() -> Any:
    from sensor_reader import (
        BatteryMetrics,
        CPUMetrics,
        DiskMetrics,
        GPUMetrics,
        HardwareSnapshot,
        MemoryMetrics,
        NetworkMetrics,
    )

    return HardwareSnapshot(
        cpu=CPUMetrics(temp_c=55.0, usage_pct=30.0, freq_mhz=3200.0, cores=8, throttled=False),
        memory=MemoryMetrics(total_mb=16384, used_mb=8192, available_mb=8192, swap_used_mb=0, pressure='low'),
        disks=[DiskMetrics(device='/dev/sda', mount='/', total_gb=500.0, used_gb=200.0, pct=40.0, smart_status='ok', temp_c=35.0, reallocated_sectors=0)],
        battery=BatteryMetrics(present=True, pct=80.0, status='discharging', time_remaining_min=240, health_pct=95.0),
        network=[NetworkMetrics(iface='eth0', bytes_sent_ps=1024.0, bytes_recv_ps=2048.0, latency_ms=12.0, link_up=True, speed_mbps=1000)],
        gpu=GPUMetrics(present=False, vendor=None, model=None, temp_c=None, usage_pct=None, vram_used_mb=None),
        ts=datetime.now(timezone.utc).isoformat(),
        health_score=0.85,
        anomaly_score=0.75,
        anomaly_detected=False,
    )


@pytest.fixture
def mock_critical_snapshot(mock_snapshot: Any) -> Any:
    s = mock_snapshot
    s.cpu.temp_c = 92.0
    s.memory.pressure = 'high'
    s.memory.available_mb = 512
    s.disks[0].smart_status = 'failing'
    s.disks[0].reallocated_sectors = 10
    s.disks[0].pct = 95.0
    s.battery.pct = 8.0
    s.battery.status = 'discharging'
    s.anomaly_detected = True
    s.anomaly_score = 0.15
    return s


@pytest.fixture
async def db(tmp_path: Path):
    from metrics_db import MetricsDB

    d = MetricsDB(db_path=str(tmp_path / 'test_metrics.db'))
    await d.init()
    yield d
    await d.close()


@pytest.fixture
def test_client(tmp_path: Path):
    import hardware_intel_service as svc

    svc.DATA_DIR = tmp_path / 'hardware_intel'
    svc.DB_PATH = str(svc.DATA_DIR / 'metrics.db')
    with TestClient(svc.app) as client:
        yield client
