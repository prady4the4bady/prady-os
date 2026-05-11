from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sensor_reader import SensorReader


@pytest.mark.asyncio
async def test_read_cpu_returns_all_fields(monkeypatch):
    r = SensorReader()
    monkeypatch.setattr('sensor_reader.psutil.cpu_percent', lambda interval=0.1: 25.0)
    monkeypatch.setattr('sensor_reader.psutil.cpu_freq', lambda: SimpleNamespace(current=3000.0))
    monkeypatch.setattr('sensor_reader.psutil.cpu_count', lambda logical=False: 8)
    monkeypatch.setattr(r, '_read_cpu_temp', lambda: 50.0)
    monkeypatch.setattr(r, '_is_throttled', lambda: False)
    cpu = await r.read_cpu()
    assert cpu.temp_c == 50.0
    assert cpu.usage_pct == 25.0
    assert cpu.freq_mhz == 3000.0
    assert cpu.cores == 8


@pytest.mark.asyncio
async def test_read_cpu_temp_default_on_error(monkeypatch):
    r = SensorReader()
    monkeypatch.setattr(r, '_read_cpu_temp', lambda: (_ for _ in ()).throw(RuntimeError('x')))
    cpu = await r.read_cpu()
    assert cpu.temp_c == 40.0


@pytest.mark.asyncio
async def test_memory_pressure_high(monkeypatch):
    r = SensorReader()
    monkeypatch.setattr('sensor_reader.psutil.virtual_memory', lambda: SimpleNamespace(total=1000 * 1024 * 1024, used=950 * 1024 * 1024, available=90 * 1024 * 1024))
    monkeypatch.setattr('sensor_reader.psutil.swap_memory', lambda: SimpleNamespace(used=0))
    m = await r.read_memory()
    assert m.pressure == 'high'


@pytest.mark.asyncio
async def test_memory_pressure_medium(monkeypatch):
    r = SensorReader()
    monkeypatch.setattr('sensor_reader.psutil.virtual_memory', lambda: SimpleNamespace(total=1000 * 1024 * 1024, used=800 * 1024 * 1024, available=200 * 1024 * 1024))
    monkeypatch.setattr('sensor_reader.psutil.swap_memory', lambda: SimpleNamespace(used=0))
    m = await r.read_memory()
    assert m.pressure == 'medium'


@pytest.mark.asyncio
async def test_memory_pressure_low(monkeypatch):
    r = SensorReader()
    monkeypatch.setattr('sensor_reader.psutil.virtual_memory', lambda: SimpleNamespace(total=1000 * 1024 * 1024, used=600 * 1024 * 1024, available=400 * 1024 * 1024))
    monkeypatch.setattr('sensor_reader.psutil.swap_memory', lambda: SimpleNamespace(used=0))
    m = await r.read_memory()
    assert m.pressure == 'low'


@pytest.mark.asyncio
async def test_read_disks_returns_list(monkeypatch):
    r = SensorReader()
    monkeypatch.setattr('sensor_reader.psutil.disk_partitions', lambda all=False: [SimpleNamespace(device='/dev/sda1', mountpoint='/')])
    monkeypatch.setattr('sensor_reader.psutil.disk_usage', lambda m: SimpleNamespace(total=1000, used=100, percent=10))
    monkeypatch.setattr(r, '_read_smart', lambda d: ('ok', 35.0, 0))
    disks = await r.read_disks()
    assert len(disks) == 1


@pytest.mark.asyncio
async def test_read_disks_failing_realloc(monkeypatch):
    r = SensorReader()
    monkeypatch.setattr('sensor_reader.psutil.disk_partitions', lambda all=False: [SimpleNamespace(device='/dev/sda1', mountpoint='/')])
    monkeypatch.setattr('sensor_reader.psutil.disk_usage', lambda m: SimpleNamespace(total=1000, used=100, percent=10))
    monkeypatch.setattr(r, '_read_smart', lambda d: ('failing', 35.0, 6))
    disks = await r.read_disks()
    assert disks[0].smart_status == 'failing'


def test_read_smart_unknown_when_missing(monkeypatch):
    r = SensorReader()
    def boom(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr('sensor_reader.subprocess.run', boom)
    status, _, _ = r._read_smart('/dev/sda')
    assert status == 'unknown'


@pytest.mark.asyncio
async def test_read_battery_absent(monkeypatch):
    r = SensorReader()
    monkeypatch.setattr('sensor_reader.psutil.sensors_battery', lambda: None)
    b = await r.read_battery()
    assert b.present is False


@pytest.mark.asyncio
async def test_read_network_skips_loopback(monkeypatch):
    r = SensorReader()
    monkeypatch.setattr('sensor_reader.psutil.net_if_stats', lambda: {'lo': SimpleNamespace(isup=True, speed=0), 'eth0': SimpleNamespace(isup=True, speed=1000)})
    monkeypatch.setattr('sensor_reader.psutil.net_io_counters', lambda pernic=True: {'lo': SimpleNamespace(bytes_sent=1, bytes_recv=1), 'eth0': SimpleNamespace(bytes_sent=2, bytes_recv=3)})
    monkeypatch.setattr(r, '_ping_latency', lambda: 10.0)
    net = await r.read_network()
    assert all(n.iface != 'lo' for n in net)


@pytest.mark.asyncio
async def test_read_gpu_not_present(monkeypatch):
    r = SensorReader()
    def boom(*args, **kwargs):
        raise RuntimeError('no nvidia')
    monkeypatch.setattr('sensor_reader.subprocess.run', boom)
    monkeypatch.setattr('sensor_reader.Path.exists', lambda self: False)
    gpu = await r.read_gpu()
    assert gpu.present is False


@pytest.mark.asyncio
async def test_read_all_health_score_bounds(monkeypatch):
    r = SensorReader(anomaly_detector=None)
    monkeypatch.setattr(r, 'read_cpu', lambda: asyncio.sleep(0, result=SimpleNamespace(temp_c=55.0, usage_pct=20.0, freq_mhz=3000.0, cores=8, throttled=False)))
    monkeypatch.setattr(r, 'read_memory', lambda: asyncio.sleep(0, result=SimpleNamespace(total_mb=10000, used_mb=5000, available_mb=5000, swap_used_mb=0, pressure='low')))
    monkeypatch.setattr(r, 'read_disks', lambda: asyncio.sleep(0, result=[SimpleNamespace(device='/dev/sda', mount='/', total_gb=100, used_gb=10, pct=10.0, smart_status='ok', temp_c=30.0, reallocated_sectors=0)]))
    monkeypatch.setattr(r, 'read_battery', lambda: asyncio.sleep(0, result=SimpleNamespace(present=True, pct=80.0, status='discharging', time_remaining_min=10, health_pct=90.0)))
    monkeypatch.setattr(r, 'read_network', lambda: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(r, 'read_gpu', lambda: asyncio.sleep(0, result=SimpleNamespace(present=False, vendor=None, model=None, temp_c=None, usage_pct=None, vram_used_mb=None)))
    snap = await r.read_all()
    assert 0.0 <= snap.health_score <= 1.0
