"""InputController — mouse, keyboard, and screen control with audit logging."""
from __future__ import annotations

import io
import json
import logging
import os
import platform
import struct
import subprocess
import time
import zlib
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH = Path("platform/audit/input_events.jsonl")
_IS_LINUX = platform.system() == "Linux"


def _write_audit(action: str, params: dict, agent_id: str) -> None:  # type: ignore[type-arg]
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": time.time(),
        "action": action,
        "params": params,
        "agent_id": agent_id,
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _try_pyautogui():  # type: ignore[return]
    try:
        import pyautogui  # type: ignore[import-untyped]
        pyautogui.FAILSAFE = False
        return pyautogui
    except Exception:
        return None


def _xdotool(*args: str) -> bool:
    """Run xdotool command, returns True on success."""
    try:
        result = subprocess.run(["xdotool", *args], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _make_minimal_png() -> bytes:
    """Return a 1×1 black PNG for fallback screenshots."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFF_FFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    iend = chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


class InputController:
    """Full desktop input control: mouse, keyboard, screenshot with audit log."""

    def __init__(self, agent_id: str = "input-controller") -> None:
        self._agent_id = agent_id
        self._pyautogui = _try_pyautogui()

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def move_mouse(self, x: int, y: int, duration: float = 0.3) -> None:
        _write_audit("move_mouse", {"x": x, "y": y, "duration": duration}, self._agent_id)
        pag = self._pyautogui
        if pag:
            pag.moveTo(x, y, duration=duration)
        elif _IS_LINUX:
            _xdotool("mousemove", str(x), str(y))

    def click(self, x: int, y: int, button: str = "left") -> None:
        _write_audit("click", {"x": x, "y": y, "button": button}, self._agent_id)
        pag = self._pyautogui
        if pag:
            pag.click(x, y, button=button)
        elif _IS_LINUX:
            btn_map = {"left": "1", "middle": "2", "right": "3"}
            _xdotool("mousemove", str(x), str(y))
            _xdotool("click", btn_map.get(button, "1"))

    def double_click(self, x: int, y: int) -> None:
        _write_audit("double_click", {"x": x, "y": y}, self._agent_id)
        pag = self._pyautogui
        if pag:
            pag.doubleClick(x, y)
        elif _IS_LINUX:
            _xdotool("mousemove", str(x), str(y))
            _xdotool("click", "--repeat", "2", "1")

    def right_click(self, x: int, y: int) -> None:
        _write_audit("right_click", {"x": x, "y": y}, self._agent_id)
        pag = self._pyautogui
        if pag:
            pag.rightClick(x, y)
        elif _IS_LINUX:
            _xdotool("mousemove", str(x), str(y))
            _xdotool("click", "3")

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> None:
        _write_audit("drag", {"x1": x1, "y1": y1, "x2": x2, "y2": y2}, self._agent_id)
        pag = self._pyautogui
        if pag:
            pag.moveTo(x1, y1)
            pag.dragTo(x2, y2, duration=duration, button="left")
        elif _IS_LINUX:
            _xdotool("mousemove", str(x1), str(y1))
            _xdotool("mousedown", "1")
            _xdotool("mousemove", str(x2), str(y2))
            _xdotool("mouseup", "1")

    def scroll(self, x: int, y: int, clicks: int) -> None:
        _write_audit("scroll", {"x": x, "y": y, "clicks": clicks}, self._agent_id)
        pag = self._pyautogui
        if pag:
            pag.moveTo(x, y)
            pag.scroll(clicks)
        elif _IS_LINUX:
            _xdotool("mousemove", str(x), str(y))
            btn = "4" if clicks > 0 else "5"
            for _ in range(abs(clicks)):
                _xdotool("click", btn)

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def type_text(self, text: str, interval: float = 0.05) -> None:
        _write_audit("type_text", {"text": text[:50], "interval": interval}, self._agent_id)
        pag = self._pyautogui
        if pag:
            pag.typewrite(text, interval=interval)
        elif _IS_LINUX:
            _xdotool("type", "--delay", str(int(interval * 1000)), text)

    def hotkey(self, *keys: str) -> None:
        _write_audit("hotkey", {"keys": list(keys)}, self._agent_id)
        pag = self._pyautogui
        if pag:
            pag.hotkey(*keys)
        elif _IS_LINUX:
            _xdotool("key", "+".join(keys))

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------

    def screenshot(self) -> bytes:
        """Capture screen and return PNG bytes."""
        _write_audit("screenshot", {}, self._agent_id)
        try:
            import mss  # type: ignore[import-untyped]
            from PIL import Image  # type: ignore[import-untyped]
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                shot = sct.grab(monitor)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
        except Exception as exc:
            logger.warning("screenshot failed: %s", exc)
            return _make_minimal_png()
