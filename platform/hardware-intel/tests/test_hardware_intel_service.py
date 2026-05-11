from __future__ import annotations

import asyncio

import pytest


def test_current_has_all_keys(test_client):
    r = test_client.get('/hardware/current')
    assert r.status_code == 200
    body = r.json()
    for key in ['cpu', 'memory', 'disks', 'battery', 'network', 'gpu', 'health_score', 'anomaly_score', 'anomaly_detected']:
        assert key in body


def test_current_health_score_range(test_client):
    r = test_client.get('/hardware/current')
    hs = r.json()['health_score']
    assert 0.0 <= hs <= 1.0


def test_current_anomaly_bool(test_client):
    r = test_client.get('/hardware/current')
    assert isinstance(r.json()['anomaly_detected'], bool)


def test_history_cpu_temp(test_client):
    test_client.get('/hardware/current')
    r = test_client.get('/hardware/history?metric=cpu_temp&hours=24')
    assert r.status_code == 200
    assert isinstance(r.json()['points'], list)


def test_history_invalid_metric_422(test_client):
    r = test_client.get('/hardware/history?metric=invalid&hours=24')
    assert r.status_code == 422


def test_alerts_empty_or_list(test_client):
    r = test_client.get('/hardware/alerts')
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_dismiss_valid_id_200(test_client):
    # generate an alert by monkeying current with high cpu
    import hardware_intel_service as svc
    s = test_client.get('/hardware/current').json()
    s['cpu']['temp_c'] = 92.0
    # cannot directly inject snapshot through API; use engine state
    from sensor_reader import HardwareSnapshot, CPUMetrics, MemoryMetrics, DiskMetrics, BatteryMetrics, NetworkMetrics, GPUMetrics
    snap = HardwareSnapshot(
        cpu=CPUMetrics(temp_c=92.0, usage_pct=30, freq_mhz=3000, cores=8, throttled=False),
        memory=MemoryMetrics(total_mb=10000, used_mb=8000, available_mb=2000, swap_used_mb=0, pressure='low'),
        disks=[DiskMetrics(device='/dev/sda', mount='/', total_gb=100, used_gb=50, pct=50, smart_status='ok', temp_c=30, reallocated_sectors=0)],
        battery=BatteryMetrics(present=False, pct=None, status='unknown', time_remaining_min=None, health_pct=None),
        network=[NetworkMetrics(iface='eth0', bytes_sent_ps=0, bytes_recv_ps=0, latency_ms=1, link_up=True, speed_mbps=1000)],
        gpu=GPUMetrics(present=False, vendor=None, model=None, temp_c=None, usage_pct=None, vram_used_mb=None),
        ts='now', health_score=0.7, anomaly_score=0.9, anomaly_detected=False,
    )
    new_alerts = svc.app.state.alert_engine.evaluate(snap)
    assert new_alerts
    for a in new_alerts:
        asyncio.run(svc.app.state.metrics_db.store_alert(a))
    alert_id = new_alerts[0].alert_id
    r = test_client.post(f'/hardware/alerts/{alert_id}/dismiss')
    assert r.status_code == 200


def test_dismiss_unknown_404(test_client):
    r = test_client.post('/hardware/alerts/unknown-id/dismiss')
    assert r.status_code == 404


def test_baseline_endpoint(test_client):
    r = test_client.get('/hardware/baseline')
    assert r.status_code == 200
    assert isinstance(r.json()['samples_trained'], int)


def test_baseline_train_complete(test_client):
    # prime with snapshots
    for _ in range(12):
        test_client.get('/hardware/current')
    r = test_client.post('/hardware/baseline/train')
    assert r.status_code == 200
    assert r.json()['status'] == 'complete'


def test_health_ok(test_client):
    r = test_client.get('/health')
    assert r.status_code == 200
    j = r.json()
    assert j['status'] == 'ok'
    assert j['service'] == 'hardware-intel'


def test_current_cached_hits_sensor_once(monkeypatch, test_client):
    import hardware_intel_service as svc

    calls = {'n': 0}
    original_read_all = svc.app.state.reader.read_all

    async def fake_read_all():
        calls['n'] += 1
        return await original_read_all()

    monkeypatch.setattr(svc.app.state.reader, 'read_all', fake_read_all)

    r1 = test_client.get('/hardware/current')
    assert r1.status_code == 200
    r2 = test_client.get('/hardware/current')
    assert r2.status_code == 200
    assert calls['n'] == 1
