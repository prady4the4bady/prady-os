"""Screen agent for GUI automation with Wayland/X11 and cross-platform fallbacks."""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.agents.base import BaseAgent

try:
    import pyautogui
except Exception:  # pragma: no cover - optional dependency at runtime
    pyautogui = None  # type: ignore[assignment]

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency at runtime
    pytesseract = None  # type: ignore[assignment]

try:
    from PIL import Image, ImageGrab
except Exception:  # pragma: no cover - optional dependency at runtime
    Image = None  # type: ignore[assignment]
    ImageGrab = None  # type: ignore[assignment]


_MUTATING_ACTIONS = {"move_cursor", "click", "type_text", "scroll", "key_press"}
_PYAUTO_UNAVAILABLE = "pyautogui is unavailable"


class ScreenAgent(BaseAgent):
    agent_type = "screen"

    def __init__(
        self,
        backend: str = "auto",
        ocr_enabled: bool = True,
        screenshot_dir: str | Path = "/tmp/kryos-screenshots",
    ) -> None:
        self._backend = backend
        self._ocr_enabled = ocr_enabled
        self._screenshot_dir = Path(screenshot_dir)
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _has_wayland(env: Optional[Dict[str, str]] = None) -> bool:
        env_map = env or {}
        return bool(env_map.get("WAYLAND_DISPLAY"))

    @staticmethod
    def _has_x11(env: Optional[Dict[str, str]] = None) -> bool:
        env_map = env or {}
        return bool(env_map.get("DISPLAY"))

    @staticmethod
    def _command_exists(name: str) -> bool:
        return shutil.which(name) is not None

    def _detect_backend(self, env: Optional[Dict[str, str]] = None) -> str:
        env_map = env or dict(os.environ)
        preferred = self._backend.lower()

        if preferred != "auto":
            return preferred

        if self._has_wayland(env_map) and self._command_exists("ydotool"):
            return "ydotool"
        if self._has_x11(env_map) and self._command_exists("xdotool"):
            return "xdotool"
        return "pyautogui"

    async def _run_command(self, *args: str) -> Tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode or 0, out.decode("utf-8", errors="ignore"), err.decode("utf-8", errors="ignore")

    async def move_cursor(self, x: int, y: int) -> Dict[str, Any]:
        backend = self._detect_backend()
        if backend == "ydotool":
            rc, _out, err = await self._run_command("ydotool", "mousemove", "--absolute", str(x), str(y))
            return {"status": "ok" if rc == 0 else "error", "backend": backend, "x": x, "y": y, "error": err or None}
        if backend == "xdotool":
            rc, _out, err = await self._run_command("xdotool", "mousemove", str(x), str(y))
            return {"status": "ok" if rc == 0 else "error", "backend": backend, "x": x, "y": y, "error": err or None}

        if pyautogui is None:
            return {"status": "error", "backend": backend, "error": _PYAUTO_UNAVAILABLE}
        await asyncio.to_thread(pyautogui.moveTo, x, y)
        return {"status": "ok", "backend": backend, "x": x, "y": y}

    async def click(self, button: str = "left", clicks: int = 1) -> Dict[str, Any]:
        backend = self._detect_backend()
        x11_button_map = {"left": "1", "middle": "2", "right": "3"}
        ydotool_button_map = {"left": "0xC0", "middle": "0xC1", "right": "0xC2"}

        if backend == "ydotool":
            btn = ydotool_button_map.get(button, "0xC0")
            for _ in range(max(1, clicks)):
                rc, _out, err = await self._run_command("ydotool", "click", btn)
                if rc != 0:
                    return {"status": "error", "backend": backend, "button": button, "error": err or None}
            return {"status": "ok", "backend": backend, "button": button, "clicks": clicks}

        if backend == "xdotool":
            btn = x11_button_map.get(button, "1")
            rc, _out, err = await self._run_command("xdotool", "click", "--repeat", str(max(1, clicks)), btn)
            return {"status": "ok" if rc == 0 else "error", "backend": backend, "button": button, "clicks": clicks, "error": err or None}

        if pyautogui is None:
            return {"status": "error", "backend": backend, "error": _PYAUTO_UNAVAILABLE}
        await asyncio.to_thread(pyautogui.click, button=button, clicks=max(1, clicks))
        return {"status": "ok", "backend": backend, "button": button, "clicks": clicks}

    async def type_text(self, text: str, interval: float = 0.01) -> Dict[str, Any]:
        backend = self._detect_backend()
        if backend == "ydotool":
            rc, _out, err = await self._run_command("ydotool", "type", text)
            return {"status": "ok" if rc == 0 else "error", "backend": backend, "typed_chars": len(text), "error": err or None}
        if backend == "xdotool":
            rc, _out, err = await self._run_command("xdotool", "type", "--delay", str(int(interval * 1000)), text)
            return {"status": "ok" if rc == 0 else "error", "backend": backend, "typed_chars": len(text), "error": err or None}

        if pyautogui is None:
            return {"status": "error", "backend": backend, "error": _PYAUTO_UNAVAILABLE}
        await asyncio.to_thread(pyautogui.write, text, interval=interval)
        return {"status": "ok", "backend": backend, "typed_chars": len(text)}

    async def _scroll_with_ydotool(self, amount: int, backend: str) -> Dict[str, Any]:
        wheel_btn = "0xC3" if amount > 0 else "0xC4"
        for _ in range(abs(amount)):
            rc, _out, err = await self._run_command("ydotool", "click", wheel_btn)
            if rc != 0:
                return {"status": "error", "backend": backend, "amount": amount, "error": err or None}
        return {"status": "ok", "backend": backend, "amount": amount}

    async def _scroll_with_xdotool(self, amount: int, backend: str) -> Dict[str, Any]:
        btn = "4" if amount > 0 else "5"
        rc, _out, err = await self._run_command("xdotool", "click", "--repeat", str(max(1, abs(amount))), btn)
        return {"status": "ok" if rc == 0 else "error", "backend": backend, "amount": amount, "error": err or None}

    async def scroll(self, amount: int) -> Dict[str, Any]:
        backend = self._detect_backend()
        if backend == "ydotool":
            return await self._scroll_with_ydotool(amount, backend)

        if backend == "xdotool":
            return await self._scroll_with_xdotool(amount, backend)

        if pyautogui is None:
            return {"status": "error", "backend": backend, "error": _PYAUTO_UNAVAILABLE}
        await asyncio.to_thread(pyautogui.scroll, amount)
        return {"status": "ok", "backend": backend, "amount": amount}

    async def key_press(self, key: str) -> Dict[str, Any]:
        backend = self._detect_backend()
        if backend == "ydotool":
            rc, _out, err = await self._run_command("ydotool", "key", key)
            return {"status": "ok" if rc == 0 else "error", "backend": backend, "key": key, "error": err or None}
        if backend == "xdotool":
            rc, _out, err = await self._run_command("xdotool", "key", key)
            return {"status": "ok" if rc == 0 else "error", "backend": backend, "key": key, "error": err or None}

        if pyautogui is None:
            return {"status": "error", "backend": backend, "error": _PYAUTO_UNAVAILABLE}
        await asyncio.to_thread(pyautogui.press, key)
        return {"status": "ok", "backend": backend, "key": key}

    def _resolve_screenshot_path(self, path: Optional[str]) -> Path:
        if path:
            screenshot_path = Path(path)
            if not screenshot_path.is_absolute():
                screenshot_path = self._screenshot_dir / screenshot_path
        else:
            screenshot_path = self._screenshot_dir / f"screen-{int(time.time() * 1000)}.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        return screenshot_path

    async def screenshot(self, path: Optional[str] = None) -> Dict[str, Any]:
        backend = self._detect_backend()
        target = self._resolve_screenshot_path(path)

        if backend == "ydotool" and self._command_exists("grim"):
            rc, _out, err = await self._run_command("grim", str(target))
            return {"status": "ok" if rc == 0 else "error", "backend": backend, "path": str(target), "error": err or None}

        if backend == "xdotool" and self._command_exists("scrot"):
            rc, _out, err = await self._run_command("scrot", str(target))
            return {"status": "ok" if rc == 0 else "error", "backend": backend, "path": str(target), "error": err or None}

        try:
            if pyautogui is not None:
                await asyncio.to_thread(pyautogui.screenshot, str(target))
                return {"status": "ok", "backend": "pyautogui", "path": str(target)}
            if ImageGrab is not None:
                image = await asyncio.to_thread(ImageGrab.grab)
                await asyncio.to_thread(image.save, str(target))
                return {"status": "ok", "backend": "pillow", "path": str(target)}
        except Exception as exc:
            return {"status": "error", "backend": backend, "path": str(target), "error": str(exc)}

        return {"status": "error", "backend": backend, "path": str(target), "error": "no screenshot backend available"}

    async def ocr_region(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self._ocr_enabled:
            return {"status": "error", "error": "ocr is disabled"}
        if pytesseract is None or Image is None:
            return {"status": "error", "error": "ocr dependencies unavailable"}

        screenshot_path: Optional[Path] = Path(path) if path else None
        if screenshot_path is None:
            capture = await self.screenshot()
            if capture.get("status") != "ok":
                return {"status": "error", "error": f"screenshot failed: {capture.get('error')}"}
            screenshot_path = Path(str(capture.get("path")))

        try:
            image = await asyncio.to_thread(Image.open, screenshot_path)
            if all(v is not None for v in (x, y, width, height)):
                left = int(x or 0)
                top = int(y or 0)
                right = left + int(width or 0)
                bottom = top + int(height or 0)
                image = await asyncio.to_thread(image.crop, (left, top, right, bottom))
            text = await asyncio.to_thread(pytesseract.image_to_string, image)
            return {
                "status": "ok",
                "path": str(screenshot_path),
                "text": text.strip(),
                "region": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                },
            }
        except Exception as exc:
            return {"status": "error", "path": str(screenshot_path), "error": str(exc)}

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        handlers = {
            "move_cursor": lambda: self.move_cursor(int(params.get("x", 0)), int(params.get("y", 0))),
            "click": lambda: self.click(str(params.get("button", "left")), int(params.get("clicks", 1))),
            "type_text": lambda: self.type_text(str(params.get("text", "")), float(params.get("interval", 0.01))),
            "screenshot": lambda: self.screenshot(params.get("path")),
            "ocr_region": lambda: self.ocr_region(
                params.get("x"),
                params.get("y"),
                params.get("width"),
                params.get("height"),
                params.get("path"),
            ),
            "extract_text": lambda: self.ocr_region(
                params.get("x"),
                params.get("y"),
                params.get("width"),
                params.get("height"),
                params.get("path"),
            ),
            "scroll": lambda: self.scroll(int(params.get("amount", 1))),
            "key_press": lambda: self.key_press(str(params.get("key", "enter"))),
        }
        handler = handlers.get(action)
        if not handler:
            return {"status": "unsupported", "action": action}
        return await handler()

    def requires_approval(self, action: str, policy: str) -> bool:
        if policy in ("require_approval_for_screen", "strict"):
            return action in _MUTATING_ACTIONS
        return False
