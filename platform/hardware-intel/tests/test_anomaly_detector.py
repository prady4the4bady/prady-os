from __future__ import annotations

from datetime import datetime, timezone

import pytest

from anomaly_detector import AnomalyDetector
from sensor_reader import (
    BatteryMetrics,
    CPUMetrics,
    DiskMetrics,
    GPUMetrics,
    HardwareSnapshot,
    MemoryMetrics,
    NetworkMetrics,
)


def _snap(cpu_temp: float = 55.0, mem_used: int = 4000) -> HardwareSnapshot:
    return HardwareSnapshot(
        cpu=CPUMetrics(temp_c=cpu_temp, usage_pct=30.0, freq_mhz=3000.0, cores=8, throttled=False),
        memory=MemoryMetrics(total_mb=8000, used_mb=mem_used, available_mb=max(1, 8000 - mem_used), swap_used_mb=0, pressure='low'),
        disks=[DiskMetrics(device='/dev/sda', mount='/', total_gb=100, used_gb=50, pct=50.0, smart_status='ok', temp_c=30.0, reallocated_sectors=0)],
        battery=BatteryMetrics(present=True, pct=80.0, status='discharging', time_remaining_min=120, health_pct=90.0),
        network=[NetworkMetrics(iface='eth0', bytes_sent_ps=1000.0, bytes_recv_ps=2000.0, latency_ms=12.0, link_up=True, speed_mbps=1000)],
        gpu=GPUMetrics(present=False, vendor=None, model=None, temp_c=None, usage_pct=None, vram_used_mb=None),
        ts=datetime.now(timezone.utc).isoformat(),
        health_score=0.9,
        anomaly_score=0.9,
        anomaly_detected=False,
    )


def test_train_fails_with_insufficient(tmp_path):
    d = AnomalyDetector(model_path=str(tmp_path / 'm.pkl'), scaler_path=str(tmp_path / 's.pkl'))
    r = d.train([_snap() for _ in range(5)])
    assert r.success is False


def test_train_succeeds_with_enough(tmp_path):
    d = AnomalyDetector(model_path=str(tmp_path / 'm.pkl'), scaler_path=str(tmp_path / 's.pkl'))
    r = d.train([_snap(cpu_temp=50 + i * 0.1, mem_used=3000 + i) for i in range(12)])
    assert r.success is True


def test_predict_before_training_default(tmp_path):
    d = AnomalyDetector(model_path=str(tmp_path / 'm.pkl'), scaler_path=str(tmp_path / 's.pkl'))
    p = d.predict(_snap())
    assert p.anomaly_detected is False


def test_predict_after_training_bounds(tmp_path):
    d = AnomalyDetector(model_path=str(tmp_path / 'm.pkl'), scaler_path=str(tmp_path / 's.pkl'))
    d.train([_snap(cpu_temp=45 + i, mem_used=3000 + i * 10) for i in range(15)])
    p = d.predict(_snap())
    assert 0.0 <= p.score <= 1.0


def test_normal_snapshot_not_anomalous(tmp_path):
    d = AnomalyDetector(model_path=str(tmp_path / 'm.pkl'), scaler_path=str(tmp_path / 's.pkl'))
    d.train([_snap(cpu_temp=50 + i * 0.1, mem_used=3500 + i) for i in range(20)])
    p = d.predict(_snap(cpu_temp=52, mem_used=3600))
    assert 0.0 <= p.score <= 1.0


def test_anomalous_snapshot_low_score(tmp_path):
    d = AnomalyDetector(model_path=str(tmp_path / 'm.pkl'), scaler_path=str(tmp_path / 's.pkl'))
    d.train([_snap(cpu_temp=50 + i * 0.1, mem_used=3500 + i) for i in range(20)])
    p = d.predict(_snap(cpu_temp=100, mem_used=7920))
    assert p.score < 0.3


def test_load_false_when_missing(tmp_path):
    d = AnomalyDetector(model_path=str(tmp_path / 'missing-m.pkl'), scaler_path=str(tmp_path / 'missing-s.pkl'))
    assert d.load() is False


def test_extract_features_shape(tmp_path):
    d = AnomalyDetector(model_path=str(tmp_path / 'm.pkl'), scaler_path=str(tmp_path / 's.pkl'))
    arr = d._extract_features(_snap())
    assert arr.shape == (1, 6)
