from __future__ import annotations

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


@dataclass
class CPUMetrics:
    temp_c: float | None
    usage_pct: float
    freq_mhz: float
    cores: int
    throttled: bool


@dataclass
class MemoryMetrics:
    total_mb: int
    used_mb: int
    available_mb: int
    swap_used_mb: int
    pressure: str


@dataclass
class DiskMetrics:
    device: str
    mount: str
    total_gb: float
    used_gb: float
    pct: float
    smart_status: str
    temp_c: float | None
    reallocated_sectors: int


@dataclass
class BatteryMetrics:
    present: bool
    pct: float | None
    status: str
    time_remaining_min: int | None
    health_pct: float | None


@dataclass
class NetworkMetrics:
    iface: str
    bytes_sent_ps: float
    bytes_recv_ps: float
    latency_ms: float | None
    link_up: bool
    speed_mbps: int


@dataclass
class GPUMetrics:
    present: bool
    vendor: str | None
    model: str | None
    temp_c: float | None
    usage_pct: float | None
    vram_used_mb: float | None


@dataclass
class HardwareSnapshot:
    cpu: CPUMetrics
    memory: MemoryMetrics
    disks: list[DiskMetrics]
    battery: BatteryMetrics
    network: list[NetworkMetrics]
    gpu: GPUMetrics
    ts: str
    health_score: float
    anomaly_score: float
    anomaly_detected: bool


class SensorReader:
    def __init__(self, anomaly_detector: Any | None = None) -> None:
        self._anomaly_detector = anomaly_detector
        self._prev_net: dict[str, tuple[int, int, float]] = {}

    async def read_cpu(self) -> CPUMetrics:
        def _read() -> CPUMetrics:
            temp = self._read_cpu_temp()
            usage = float(psutil.cpu_percent(interval=0.1))
            freq = psutil.cpu_freq()
            freq_mhz = float(freq.current) if freq else 0.0
            cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1
            throttled = self._is_throttled()
            return CPUMetrics(temp_c=temp, usage_pct=usage, freq_mhz=freq_mhz, cores=int(cores), throttled=throttled)

        try:
            return await asyncio.to_thread(_read)
        except Exception:
            return CPUMetrics(temp_c=40.0, usage_pct=0.0, freq_mhz=0.0, cores=1, throttled=False)

    def _read_cpu_temp(self) -> float:
        try:
            temps: list[float] = []
            for p in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
                val = p.read_text(encoding='utf-8', errors='ignore').strip()
                if val:
                    temps.append(float(val) / 1000.0)
            if temps:
                return round(sum(temps) / len(temps), 2)
        except Exception:
            pass
        return 40.0

    def _is_throttled(self) -> bool:
        cur = Path('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq')
        maxp = Path('/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq')
        try:
            if cur.exists() and maxp.exists():
                cur_v = float(cur.read_text(encoding='utf-8').strip())
                max_v = max(float(maxp.read_text(encoding='utf-8').strip()), 1.0)
                return cur_v < (max_v * 0.9)
        except Exception:
            pass
        return False

    async def read_memory(self) -> MemoryMetrics:
        try:
            vm = psutil.virtual_memory()
            sm = psutil.swap_memory()
            total_mb = int(vm.total / 1024 / 1024)
            used_mb = int(vm.used / 1024 / 1024)
            available_mb = int(vm.available / 1024 / 1024)
            swap_used_mb = int(sm.used / 1024 / 1024)
            if available_mb < int(total_mb * 0.10):
                pressure = 'high'
            elif available_mb < int(total_mb * 0.25):
                pressure = 'medium'
            else:
                pressure = 'low'
            return MemoryMetrics(total_mb=total_mb, used_mb=used_mb, available_mb=available_mb, swap_used_mb=swap_used_mb, pressure=pressure)
        except Exception:
            return MemoryMetrics(total_mb=1, used_mb=0, available_mb=1, swap_used_mb=0, pressure='low')

    async def read_disks(self) -> list[DiskMetrics]:
        out: list[DiskMetrics] = []
        seen: set[str] = set()
        try:
            parts = psutil.disk_partitions(all=False)
        except Exception:
            return out

        for part in parts:
            dev = part.device
            if not dev:
                continue
            base = re.sub(r'\d+$', '', dev)
            if base in seen:
                continue
            seen.add(base)

            try:
                usage = psutil.disk_usage(part.mountpoint)
                total_gb = round(usage.total / 1024 / 1024 / 1024, 2)
                used_gb = round(usage.used / 1024 / 1024 / 1024, 2)
                pct = float(usage.percent)
            except Exception:
                total_gb = 0.0
                used_gb = 0.0
                pct = 0.0

            smart_status, temp_c, realloc = self._read_smart(base)
            out.append(DiskMetrics(device=base, mount=part.mountpoint, total_gb=total_gb, used_gb=used_gb, pct=pct, smart_status=smart_status, temp_c=temp_c, reallocated_sectors=realloc))

        return out

    def _read_smart(self, device: str) -> tuple[str, float | None, int]:
        try:
            res = subprocess.run(['smartctl', '-A', device], capture_output=True, text=True, check=False, timeout=2)
        except FileNotFoundError:
            return ('unknown', None, 0)
        except Exception:
            return ('unknown', None, 0)

        text = res.stdout or ''
        realloc = 0
        temp_c: float | None = None

        for line in text.splitlines():
            if 'Reallocated_Sector_Ct' in line:
                m = re.search(r'(\d+)\s*$', line.strip())
                if m:
                    realloc = int(m.group(1))
            if 'Temperature_Celsius' in line:
                m = re.search(r'(\d+)\s*$', line.strip())
                if m:
                    temp_c = float(m.group(1))

        if realloc > 5:
            status = 'failing'
        elif realloc > 0:
            status = 'warning'
        else:
            status = 'ok'

        return (status, temp_c, realloc)

    async def read_battery(self) -> BatteryMetrics:
        try:
            b = psutil.sensors_battery()
        except Exception:
            b = None

        if b is None:
            return BatteryMetrics(present=False, pct=None, status='unknown', time_remaining_min=None, health_pct=None)

        status = 'unknown'
        if b.power_plugged and b.percent >= 99:
            status = 'full'
        elif b.power_plugged:
            status = 'charging'
        else:
            status = 'discharging'

        secs = b.secsleft
        mins: int | None
        if secs is None or secs < 0:
            mins = None
        else:
            mins = int(secs / 60)

        health: float | None = None
        cap = Path('/sys/class/power_supply/BAT0/capacity')
        try:
            if cap.exists():
                health = float(cap.read_text(encoding='utf-8').strip())
        except Exception:
            health = None

        return BatteryMetrics(present=True, pct=float(b.percent), status=status, time_remaining_min=mins, health_pct=health)

    async def read_network(self) -> list[NetworkMetrics]:
        now = asyncio.get_event_loop().time()
        stats = psutil.net_if_stats()
        counters = psutil.net_io_counters(pernic=True)
        latency = self._ping_latency()

        results: list[NetworkMetrics] = []
        for iface, st in stats.items():
            if iface.lower().startswith('lo'):
                continue
            c = counters.get(iface)
            if c is None:
                continue

            prev = self._prev_net.get(iface)
            if prev is None:
                sent_ps = 0.0
                recv_ps = 0.0
            else:
                prev_sent, prev_recv, prev_ts = prev
                dt = max(now - prev_ts, 0.001)
                sent_ps = max(0.0, (c.bytes_sent - prev_sent) / dt)
                recv_ps = max(0.0, (c.bytes_recv - prev_recv) / dt)

            self._prev_net[iface] = (int(c.bytes_sent), int(c.bytes_recv), now)
            results.append(NetworkMetrics(iface=iface, bytes_sent_ps=sent_ps, bytes_recv_ps=recv_ps, latency_ms=latency, link_up=bool(st.isup), speed_mbps=int(st.speed) if st.speed else 0))

        return results

    def _ping_latency(self) -> float | None:
        try:
            res = subprocess.run(['ping', '-c', '1', '-W', '1', '8.8.8.8'], capture_output=True, text=True, check=False, timeout=2)
            m = re.search(r'time=([0-9.]+)\s*ms', res.stdout or '')
            if m:
                return float(m.group(1))
        except Exception:
            return None
        return None

    async def read_gpu(self) -> GPUMetrics:
        try:
            res = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,temperature.gpu,utilization.gpu,memory.used', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
            line = (res.stdout or '').strip().splitlines()[0] if (res.stdout or '').strip() else ''
            if line:
                parts = [p.strip() for p in line.split(',')]
                return GPUMetrics(
                    present=True,
                    vendor='nvidia',
                    model=parts[0] if len(parts) > 0 else 'unknown',
                    temp_c=float(parts[1]) if len(parts) > 1 and parts[1] else None,
                    usage_pct=float(parts[2]) if len(parts) > 2 and parts[2] else None,
                    vram_used_mb=float(parts[3]) if len(parts) > 3 and parts[3] else None,
                )
        except Exception:
            pass

        amd_state = Path('/sys/class/drm/card0/device/power_state')
        if amd_state.exists():
            return GPUMetrics(present=True, vendor='amd', model='card0', temp_c=None, usage_pct=None, vram_used_mb=None)

        return GPUMetrics(present=False, vendor=None, model=None, temp_c=None, usage_pct=None, vram_used_mb=None)

    async def read_all(self) -> HardwareSnapshot:
        cpu, mem, disks, battery, network, gpu = await asyncio.gather(
            self.read_cpu(),
            self.read_memory(),
            self.read_disks(),
            self.read_battery(),
            self.read_network(),
            self.read_gpu(),
        )

        cpu_score = max(0.0, 1.0 - (((cpu.temp_c or 60.0) - 60.0) / 40.0)) * 0.25
        mem_score = (mem.available_mb / max(mem.total_mb, 1)) * 0.25
        if disks:
            ok_count = sum(1 for d in disks if d.smart_status == 'ok')
            disk_score = (ok_count / max(len(disks), 1)) * 0.30
        else:
            disk_score = 1.0 * 0.30
        battery_score = ((battery.pct or 100.0) / 100.0 if battery.present else 1.0) * 0.20
        health_score = min(1.0, max(0.0, cpu_score + mem_score + disk_score + battery_score))

        snapshot = HardwareSnapshot(
            cpu=cpu,
            memory=mem,
            disks=disks,
            battery=battery,
            network=network,
            gpu=gpu,
            ts=datetime.now(timezone.utc).isoformat(),
            health_score=health_score,
            anomaly_score=0.5,
            anomaly_detected=False,
        )

        if self._anomaly_detector is not None:
            try:
                result = self._anomaly_detector.predict(snapshot)
                snapshot.anomaly_score = float(result.score)
                snapshot.anomaly_detected = bool(result.anomaly_detected)
            except Exception:
                pass

        return snapshot
