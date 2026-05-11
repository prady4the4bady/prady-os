from __future__ import annotations

import pytest

from alert_engine import AlertEngine


def _engine() -> AlertEngine:
    return AlertEngine(notify_url='http://notification-bus:8007', audit_url='http://audit-log:8006')


def test_cpu_critical(mock_critical_snapshot):
    e = _engine()
    alerts = e.evaluate(mock_critical_snapshot)
    assert any(a.component == 'cpu' and a.severity == 'critical' for a in alerts)


def test_cpu_warning(mock_snapshot):
    s = mock_snapshot
    s.cpu.temp_c = 80.0
    e = _engine()
    alerts = e.evaluate(s)
    assert any(a.component == 'cpu' and a.severity == 'warning' for a in alerts)


def test_cpu_no_alert(mock_snapshot):
    s = mock_snapshot
    s.cpu.temp_c = 60.0
    e = _engine()
    alerts = e.evaluate(s)
    assert not any(a.component == 'cpu' for a in alerts)


def test_memory_high_alert(mock_snapshot):
    s = mock_snapshot
    s.memory.pressure = 'high'
    e = _engine()
    alerts = e.evaluate(s)
    assert any(a.component == 'memory' for a in alerts)


def test_disk_failing_alert(mock_snapshot):
    s = mock_snapshot
    s.disks[0].smart_status = 'failing'
    s.disks[0].reallocated_sectors = 10
    e = _engine()
    alerts = e.evaluate(s)
    assert any(a.component == 'disk' and a.severity == 'critical' for a in alerts)


def test_disk_pct_warning(mock_snapshot):
    s = mock_snapshot
    s.disks[0].pct = 95.0
    e = _engine()
    alerts = e.evaluate(s)
    assert any(a.component == 'disk' and a.severity == 'warning' for a in alerts)


def test_battery_critical(mock_snapshot):
    s = mock_snapshot
    s.battery.pct = 8.0
    s.battery.status = 'discharging'
    e = _engine()
    alerts = e.evaluate(s)
    assert any(a.component == 'battery' and a.severity == 'critical' for a in alerts)


def test_battery_warning(mock_snapshot):
    s = mock_snapshot
    s.battery.pct = 15.0
    s.battery.status = 'discharging'
    e = _engine()
    alerts = e.evaluate(s)
    assert any(a.component == 'battery' and a.severity == 'warning' for a in alerts)


def test_anomaly_warning(mock_snapshot):
    s = mock_snapshot
    s.anomaly_detected = True
    s.anomaly_score = 0.1
    e = _engine()
    alerts = e.evaluate(s)
    assert any(a.component == 'system' for a in alerts)


def test_dismiss_known(mock_snapshot):
    s = mock_snapshot
    s.cpu.temp_c = 80.0
    e = _engine()
    alerts = e.evaluate(s)
    assert e.dismiss(alerts[0].alert_id) is True


def test_dismiss_unknown():
    e = _engine()
    assert e.dismiss('unknown') is False


def test_same_rule_increments_count(mock_snapshot):
    s = mock_snapshot
    s.cpu.temp_c = 80.0
    e = _engine()
    first = e.evaluate(s)
    second = e.evaluate(s)
    assert len(first) == 1
    assert len(second) == 0
    active = e.get_active_alerts()[0]
    assert active.count == 2
