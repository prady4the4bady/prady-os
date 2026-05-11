from __future__ import annotations

from pathlib import Path

import pytest

from hardware_profiler import HardwareProfiler


@pytest.mark.asyncio
async def test_profile_returns_expected_keys(monkeypatch):
    profiler = HardwareProfiler()

    monkeypatch.setattr(profiler, "_cpu_profile", lambda: {"model": "x", "cores": 8, "freq_mhz": 3000, "temp_c": 45.0})
    monkeypatch.setattr(profiler, "_memory_profile", lambda: {"total_mb": 8192, "available_mb": 4096, "swap_mb": 2048})
    monkeypatch.setattr(profiler, "_disk_profile", lambda: [{"device": "/dev/sda", "model": "x", "size_gb": 256, "smart_status": "ok", "health_pct": 90}])

    async def fake_gpu():
        return {"vendor": "nvidia", "model": "rtx", "vram_mb": 8192}

    monkeypatch.setattr(profiler, "_gpu_profile", fake_gpu)
    monkeypatch.setattr(profiler, "_network_profile", lambda: [{"iface": "eth0", "speed_mbps": 1000, "link_up": True}])
    monkeypatch.setattr(profiler, "_bios_profile", lambda: {"vendor": "x", "version": "1", "date": "2025", "uefi": True, "secure_boot": True})

    hw = await profiler.profile()

    assert "cpu" in hw
    assert "memory" in hw
    assert "disks" in hw
    assert "gpu" in hw
    assert "network" in hw
    assert "bios" in hw
    assert 0.0 <= hw["hardware_score"] <= 1.0


def test_hardware_score_bounds():
    profiler = HardwareProfiler()
    score = profiler._hardware_score(
        {"cores": 16},
        {"total_mb": 32768},
        [{"health_pct": 100}],
    )
    assert 0.0 <= score <= 1.0
