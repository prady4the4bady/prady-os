"""Runtime hardware inventory and scoring."""

from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Any

import psutil


class HardwareProfiler:
    def __init__(self, dmi_root: Path = Path("/sys/class/dmi/id")) -> None:
        self.dmi_root = dmi_root

    async def profile(self) -> dict[str, Any]:
        cpu = self._cpu_profile()
        memory = self._memory_profile()
        disks = self._disk_profile()
        gpu = await self._gpu_profile()
        network = self._network_profile()
        bios = self._bios_profile()

        hardware_score = self._hardware_score(cpu, memory, disks)

        return {
            "cpu": cpu,
            "memory": memory,
            "disks": disks,
            "gpu": gpu,
            "network": network,
            "bios": bios,
            "hardware_score": round(hardware_score, 3),
        }

    def _cpu_profile(self) -> dict[str, Any]:
        model = "unknown"
        cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1
        freq = psutil.cpu_freq()
        freq_mhz = float(freq.current) if freq else 0.0

        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            text = cpuinfo.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r"model name\s*:\s*(.+)", text)
            if match:
                model = match.group(1).strip()

        temp_c: float | None = None
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                first_bucket = next(iter(temps.values()))
                if first_bucket:
                    temp_c = float(first_bucket[0].current)
        except Exception:
            temp_c = None

        return {
            "model": model,
            "cores": int(cores),
            "freq_mhz": round(freq_mhz, 2),
            "temp_c": temp_c,
        }

    def _memory_profile(self) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        sm = psutil.swap_memory()
        return {
            "total_mb": int(vm.total / 1024 / 1024),
            "available_mb": int(vm.available / 1024 / 1024),
            "swap_mb": int(sm.total / 1024 / 1024),
        }

    def _disk_profile(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for part in psutil.disk_partitions(all=False):
            dev = part.device
            if not dev or dev in seen:
                continue
            seen.add(dev)
            try:
                usage = psutil.disk_usage(part.mountpoint)
                health_pct = max(0, 100 - int(usage.percent))
                size_gb = round(usage.total / 1024 / 1024 / 1024, 2)
            except Exception:
                health_pct = 50
                size_gb = 0.0

            items.append(
                {
                    "device": dev,
                    "model": "unknown",
                    "size_gb": size_gb,
                    "smart_status": "unknown",
                    "health_pct": health_pct,
                }
            )
        return items

    async def _gpu_profile(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._gpu_profile_sync)

    def _gpu_profile_sync(self) -> dict[str, Any]:
        vendor = "unknown"
        model = "unknown"
        try:
            res = subprocess.run(
                ["lspci"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
            for line in res.stdout.splitlines():
                low = line.lower()
                if "vga" in low or "3d controller" in low:
                    model = line.split(":", 2)[-1].strip()
                    if "nvidia" in low:
                        vendor = "nvidia"
                    elif "amd" in low or "advanced micro devices" in low:
                        vendor = "amd"
                    elif "intel" in low:
                        vendor = "intel"
                    break
        except Exception:
            pass

        return {"vendor": vendor, "model": model, "vram_mb": None}

    def _network_profile(self) -> list[dict[str, Any]]:
        stats = psutil.net_if_stats()
        out: list[dict[str, Any]] = []
        for iface, st in stats.items():
            out.append(
                {
                    "iface": iface,
                    "speed_mbps": int(st.speed) if st.speed is not None else 0,
                    "link_up": bool(st.isup),
                }
            )
        return out

    def _bios_profile(self) -> dict[str, Any]:
        def read(name: str) -> str:
            p = self.dmi_root / name
            if p.exists():
                return p.read_text(encoding="utf-8", errors="ignore").strip()
            return "unknown"

        return {
            "vendor": read("bios_vendor"),
            "version": read("bios_version"),
            "date": read("bios_date"),
            "uefi": Path("/sys/firmware/efi").exists(),
            "secure_boot": (Path("/sys/firmware/efi/efivars").exists()),
        }

    def _hardware_score(
        self,
        cpu: dict[str, Any],
        memory: dict[str, Any],
        disks: list[dict[str, Any]],
    ) -> float:
        ram_total = memory.get("total_mb", 0)
        ram_score = min(1.0, max(0.0, ram_total / 16384.0))

        avg_disk_health = 0.5
        if disks:
            avg_disk_health = sum(d.get("health_pct", 50) for d in disks) / (100.0 * len(disks))

        cores = cpu.get("cores", 1)
        cpu_score = min(1.0, max(0.0, float(cores) / 16.0))

        return (ram_score * 0.3) + (avg_disk_health * 0.4) + (cpu_score * 0.3)
