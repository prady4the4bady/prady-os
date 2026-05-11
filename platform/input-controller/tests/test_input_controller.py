"""Tests for InputController."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from input_controller import InputController, _make_minimal_png


# ---------------------------------------------------------------------------
# move_mouse
# ---------------------------------------------------------------------------

def test_move_mouse_logs_action(tmp_path, monkeypatch):
    """move_mouse writes an audit record to the log file."""
    import input_controller as ic_mod
    monkeypatch.setattr(ic_mod, "AUDIT_LOG_PATH", tmp_path / "input_events.jsonl")

    mock_pag = MagicMock()

    with patch("input_controller._try_pyautogui", return_value=mock_pag):
        ic = InputController(agent_id="test-agent")
        ic.move_mouse(100, 200, duration=0.1)

    log_path = tmp_path / "input_events.jsonl"
    assert log_path.exists()
    record = json.loads(log_path.read_text())
    assert record["action"] == "move_mouse"
    assert record["params"]["x"] == 100
    assert record["params"]["y"] == 200
    assert record["agent_id"] == "test-agent"
    mock_pag.moveTo.assert_called_once_with(100, 200, duration=0.1)


# ---------------------------------------------------------------------------
# type_text
# ---------------------------------------------------------------------------

def test_type_text_logs_action(tmp_path, monkeypatch):
    """type_text writes an audit record with truncated text."""
    import input_controller as ic_mod
    monkeypatch.setattr(ic_mod, "AUDIT_LOG_PATH", tmp_path / "input_events.jsonl")

    mock_pag = MagicMock()

    with patch("input_controller._try_pyautogui", return_value=mock_pag):
        ic = InputController(agent_id="typer")
        ic.type_text("Hello world", interval=0.02)

    log = json.loads((tmp_path / "input_events.jsonl").read_text())
    assert log["action"] == "type_text"
    assert log["params"]["text"] == "Hello world"
    mock_pag.typewrite.assert_called_once_with("Hello world", interval=0.02)


# ---------------------------------------------------------------------------
# hotkey
# ---------------------------------------------------------------------------

def test_hotkey_executes(tmp_path, monkeypatch):
    """hotkey delegates to pyautogui.hotkey with correct keys."""
    import input_controller as ic_mod
    monkeypatch.setattr(ic_mod, "AUDIT_LOG_PATH", tmp_path / "input_events.jsonl")

    mock_pag = MagicMock()

    with patch("input_controller._try_pyautogui", return_value=mock_pag):
        ic = InputController()
        ic.hotkey("ctrl", "c")

    mock_pag.hotkey.assert_called_once_with("ctrl", "c")
    log = json.loads((tmp_path / "input_events.jsonl").read_text())
    assert log["action"] == "hotkey"
    assert log["params"]["keys"] == ["ctrl", "c"]


# ---------------------------------------------------------------------------
# screenshot
# ---------------------------------------------------------------------------

def test_screenshot_returns_bytes_on_mss_failure(tmp_path, monkeypatch):
    """screenshot returns a minimal valid PNG when mss is unavailable."""
    import input_controller as ic_mod
    monkeypatch.setattr(ic_mod, "AUDIT_LOG_PATH", tmp_path / "input_events.jsonl")

    # Ensure pyautogui and mss are both unavailable
    with patch("input_controller._try_pyautogui", return_value=None):
        ic = InputController()
        # Force mss import to fail
        with patch.dict("sys.modules", {"mss": None, "PIL": None}):
            result = ic.screenshot()

    assert isinstance(result, bytes)
    # All PNG files start with the PNG magic bytes
    assert result[:4] == b"\x89PNG"


def test_make_minimal_png():
    """_make_minimal_png returns valid PNG magic bytes."""
    png = _make_minimal_png()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# click audit
# ---------------------------------------------------------------------------

def test_click_logs_audit(tmp_path, monkeypatch):
    """click writes a properly structured audit entry."""
    import input_controller as ic_mod
    monkeypatch.setattr(ic_mod, "AUDIT_LOG_PATH", tmp_path / "input_events.jsonl")

    mock_pag = MagicMock()
    with patch("input_controller._try_pyautogui", return_value=mock_pag):
        ic = InputController(agent_id="clicker")
        ic.click(50, 75, button="right")

    record = json.loads((tmp_path / "input_events.jsonl").read_text())
    assert record["action"] == "click"
    assert record["params"]["button"] == "right"
    assert record["agent_id"] == "clicker"
