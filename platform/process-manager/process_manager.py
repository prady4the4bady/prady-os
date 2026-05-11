"""ProcessManager — launch, list, kill, and inspect desktop processes and windows."""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)

_IS_LINUX = platform.system() == "Linux"

APP_REGISTRY: Dict[str, str] = {
    "firefox": "/usr/bin/firefox",
    "chrome": "/usr/bin/google-chrome",
    "chromium": "/usr/bin/chromium",
    "terminal": "/usr/bin/xterm",
    "gnome-terminal": "/usr/bin/gnome-terminal",
    "konsole": "/usr/bin/konsole",
    "alacritty": "/usr/bin/alacritty",
    "kitty": "/usr/bin/kitty",
    "foot": "/usr/bin/foot",
    "vscode": "/usr/bin/code",
    "code": "/usr/bin/code",
    "nautilus": "/usr/bin/nautilus",
    "thunar": "/usr/bin/thunar",
    "kate": "/usr/bin/kate",
    "gedit": "/usr/bin/gedit",
    "gimp": "/usr/bin/gimp",
    "vlc": "/usr/bin/vlc",
    "mpv": "/usr/bin/mpv",
    "libreoffice": "/usr/bin/libreoffice",
    "inkscape": "/usr/bin/inkscape",
    "discord": "/usr/bin/discord",
    "obs": "/usr/bin/obs",
    "hyprland": "/usr/bin/Hyprland",
}

# Binaries blocked from launching
_DENIED_PREFIXES = ("/sbin/", "/usr/sbin/", "/usr/bin/sudo", "/usr/bin/su", "/bin/rm")
# System PIDs protected from kill
MIN_KILL_PID = 100


@dataclass
class ProcessHandle:
    pid: int
    name: str
    binary: str
    args: List[str]
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WindowInfo:
    pid: int
    title: str
    x: int
    y: int
    width: int
    height: int
    focused: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _is_denied(binary: str) -> bool:
    for prefix in _DENIED_PREFIXES:
        if binary.startswith(prefix):
            return True
    return False


def _resolve_binary(app_name: str) -> Optional[str]:
    if os.path.isabs(app_name) and os.path.isfile(app_name):
        return app_name
    lower = app_name.lower()
    if lower in APP_REGISTRY:
        reg = APP_REGISTRY[lower]
        if os.path.isfile(reg):
            return reg
    found = shutil.which(app_name)
    return found or None


class ProcessManager:
    """Launch, list, kill, and query windows on the desktop."""

    def launch_app(self, app_name: str, args: Optional[List[str]] = None) -> ProcessHandle:
        if args is None:
            args = []
        binary = _resolve_binary(app_name)
        if binary is None:
            raise ValueError(f"Cannot find binary for: {app_name!r}")
        if _is_denied(binary):
            raise PermissionError(f"Launch denied by policy: {binary!r}")
        proc = subprocess.Popen(
            [binary, *args],
            env={**os.environ},
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Launched %s (pid=%d)", binary, proc.pid)
        return ProcessHandle(pid=proc.pid, name=app_name, binary=binary, args=args)

    def list_processes(self) -> List[ProcessInfo]:
        result = []
        for proc in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_info"]):
            try:
                info = proc.info
                mem_info = info.get("memory_info")
                mem_mb = round(mem_info.rss / (1024 * 1024), 2) if mem_info else 0.0
                result.append(
                    ProcessInfo(
                        pid=info["pid"],
                        name=info.get("name", ""),
                        cpu_percent=round(info.get("cpu_percent") or 0.0, 2),
                        memory_mb=mem_mb,
                        status=info.get("status", "unknown"),
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return sorted(result, key=lambda p: p.cpu_percent, reverse=True)

    def kill_process(self, pid: int) -> bool:
        if pid < MIN_KILL_PID:
            raise PermissionError(f"Killing PID {pid} denied (system process)")
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            return True
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied as exc:
            raise PermissionError(f"Access denied for PID {pid}") from exc

    def focus_window(self, pid: int) -> bool:
        if not _IS_LINUX:
            return False
        return _xdotool_focus(pid)

    def get_open_windows(self) -> List[WindowInfo]:
        if not _IS_LINUX:
            return []
        return _get_windows_xdotool()


# ---------------------------------------------------------------------------
# xdotool helpers
# ---------------------------------------------------------------------------

def _xdotool_focus(pid: int) -> bool:
    try:
        r = subprocess.run(
            ["xdotool", "search", "--pid", str(pid), "--onlyvisible"],
            capture_output=True, text=True, timeout=3,
        )
        wids = r.stdout.strip().split()
        if not wids:
            return False
        subprocess.run(["xdotool", "windowactivate", wids[0]], timeout=3)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _get_windows_xdotool() -> List[WindowInfo]:
    windows: List[WindowInfo] = []
    try:
        r = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--name", ""],
            capture_output=True, text=True, timeout=5,
        )
        for wid in r.stdout.strip().split()[:50]:
            try:
                geo_r = subprocess.run(
                    ["xdotool", "getwindowgeometry", "--shell", wid],
                    capture_output=True, text=True, timeout=2,
                )
                name_r = subprocess.run(
                    ["xdotool", "getwindowname", wid],
                    capture_output=True, text=True, timeout=2,
                )
                pid_r = subprocess.run(
                    ["xdotool", "getwindowpid", wid],
                    capture_output=True, text=True, timeout=2,
                )
                geo: dict[str, str] = {}
                for line in geo_r.stdout.splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        geo[key] = value
                pid = int(pid_r.stdout.strip()) if pid_r.stdout.strip().isdigit() else 0
                windows.append(
                    WindowInfo(
                        pid=pid,
                        title=name_r.stdout.strip(),
                        x=int(geo.get("X", 0)),
                        y=int(geo.get("Y", 0)),
                        width=int(geo.get("WIDTH", 100)),
                        height=int(geo.get("HEIGHT", 100)),
                        focused=False,
                    )
                )
            except Exception:
                continue
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return windows
