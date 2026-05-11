"""Tests for ProcessManager."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from process_manager import MIN_KILL_PID, ProcessInfo, ProcessManager


# ---------------------------------------------------------------------------
# launch_app
# ---------------------------------------------------------------------------

def test_launch_app_uses_registry(monkeypatch):
    """launch_app resolves registered names and launches via subprocess."""
    mock_popen = MagicMock()
    mock_popen.pid = 12345

    with patch("process_manager.subprocess.Popen", return_value=mock_popen), \
         patch("process_manager.os.path.isfile", return_value=True), \
         patch("process_manager.shutil.which", return_value=None):
        mgr = ProcessManager()
        handle = mgr.launch_app("firefox")

    assert handle.pid == 12345
    assert handle.name == "firefox"
    assert handle.binary == "/usr/bin/firefox"


def test_launch_app_raises_on_denied_binary():
    """launch_app raises PermissionError for denied binary paths."""
    mgr = ProcessManager()
    with patch("process_manager._resolve_binary", return_value="/usr/bin/sudo"), \
         patch("process_manager.os.path.isfile", return_value=True):
        with pytest.raises(PermissionError, match="denied by policy"):
            mgr.launch_app("sudo")


def test_launch_app_raises_on_unknown_binary():
    """launch_app raises ValueError when binary cannot be resolved."""
    mgr = ProcessManager()
    with patch("process_manager._resolve_binary", return_value=None):
        with pytest.raises(ValueError, match="Cannot find binary"):
            mgr.launch_app("nonexistent_app_xyz")


# ---------------------------------------------------------------------------
# list_processes
# ---------------------------------------------------------------------------

def test_list_processes(monkeypatch):
    """list_processes returns ProcessInfo objects sorted by CPU."""
    mem_info = SimpleNamespace(rss=50 * 1024 * 1024)
    fake_procs = [
        SimpleNamespace(
            info={"pid": 1000, "name": "python", "status": "running",
                  "cpu_percent": 12.5, "memory_info": mem_info}
        ),
        SimpleNamespace(
            info={"pid": 2000, "name": "bash", "status": "sleeping",
                  "cpu_percent": 0.1, "memory_info": mem_info}
        ),
    ]

    with patch("process_manager.psutil.process_iter", return_value=fake_procs):
        mgr = ProcessManager()
        result = mgr.list_processes()

    assert len(result) == 2
    assert result[0].pid == 1000  # highest CPU first
    assert result[0].cpu_percent == pytest.approx(12.5)
    assert result[1].pid == 2000


# ---------------------------------------------------------------------------
# kill_process
# ---------------------------------------------------------------------------

def test_kill_process_denies_system_pid():
    """kill_process raises PermissionError for PIDs below MIN_KILL_PID."""
    mgr = ProcessManager()
    with pytest.raises(PermissionError, match="system process"):
        mgr.kill_process(1)

    with pytest.raises(PermissionError, match="system process"):
        mgr.kill_process(MIN_KILL_PID - 1)


def test_kill_process_terminates(monkeypatch):
    """kill_process calls terminate() then wait() on the psutil.Process."""
    import psutil as _psutil

    mock_proc = MagicMock()
    mock_proc.wait.side_effect = None  # Does not raise TimeoutExpired

    with patch("process_manager.psutil.Process", return_value=mock_proc):
        mgr = ProcessManager()
        result = mgr.kill_process(500)

    assert result is True
    mock_proc.terminate.assert_called_once()
    mock_proc.wait.assert_called_once_with(timeout=3)


def test_kill_process_returns_false_when_not_found():
    """kill_process returns False if the process no longer exists."""
    import psutil as _psutil

    with patch("process_manager.psutil.Process", side_effect=_psutil.NoSuchProcess(pid=500)):
        mgr = ProcessManager()
        result = mgr.kill_process(500)

    assert result is False


# ---------------------------------------------------------------------------
# get_open_windows (mocked xdotool)
# ---------------------------------------------------------------------------

def test_get_open_windows_xdotool(monkeypatch):
    """get_open_windows returns WindowInfo objects from xdotool output."""
    import platform as _platform

    # Force Linux so the xdotool path is taken
    monkeypatch.setattr(_platform, "system", lambda: "Linux")

    # Reload the module-level constant
    import process_manager as pm_mod
    monkeypatch.setattr(pm_mod, "_IS_LINUX", True)

    search_result = MagicMock(stdout="12345\n67890\n", returncode=0)
    geo_result = MagicMock(stdout="X=100\nY=200\nWIDTH=800\nHEIGHT=600\n")
    name_result = MagicMock(stdout="Firefox\n")
    pid_result = MagicMock(stdout="9999\n")

    def fake_run(cmd, **_kw):
        if "search" in cmd:
            return search_result
        if "getwindowgeometry" in cmd:
            return geo_result
        if "getwindowname" in cmd:
            return name_result
        if "getwindowpid" in cmd:
            return pid_result
        return MagicMock(stdout="", returncode=0)

    with patch("process_manager.subprocess.run", side_effect=fake_run):
        mgr = ProcessManager()
        windows = mgr.get_open_windows()

    assert len(windows) >= 1
    w = windows[0]
    assert w.title == "Firefox"
    assert w.pid == 9999
    assert w.x == 100
    assert w.width == 800
