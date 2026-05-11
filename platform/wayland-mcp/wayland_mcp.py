from __future__ import annotations

import asyncio
import base64
import fnmatch
import json
import os
import struct
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

app = FastAPI(title="Kryos Wayland MCP", version="1.0.0")

DEFAULT_POLICY_PATH = _ROOT / "vyrex" / "policies" / "wayland_policy.yaml"
_action_timestamps: deque[float] = deque()


# ── models ────────────────────────────────────────────────────────────────────

class MoveRequest(BaseModel):
    x: int
    y: int


class ClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"


class TypeRequest(BaseModel):
    text: str


class FocusRequest(BaseModel):
    window_id: str


# ── policy / rate limit ───────────────────────────────────────────────────────

def _policy_path() -> Path:
    configured = os.environ.get("WAYLAND_POLICY_PATH")
    return Path(configured) if configured else DEFAULT_POLICY_PATH


def _load_policy() -> dict[str, Any]:
    path = _policy_path()
    if not path.exists():
        return {
            "max_actions_per_minute": 120,
            "allowed_actions": ["*"],
            "blocked_window_classes": [],
            "require_focus_before_type": False,
            "allow_screenshot": True,
        }
    with open(path, encoding="utf-8") as fh:
        policy = yaml.safe_load(fh) or {}
    policy.setdefault("max_actions_per_minute", 120)
    policy.setdefault("allowed_actions", ["*"])
    policy.setdefault("blocked_window_classes", [])
    policy.setdefault("require_focus_before_type", False)
    policy.setdefault("allow_screenshot", True)
    return policy


def _prune_old(now: Optional[float] = None) -> None:
    cutoff = (now or time.time()) - 60.0
    while _action_timestamps and _action_timestamps[0] < cutoff:
        _action_timestamps.popleft()


def _assert_policy(action: str) -> dict[str, Any]:
    policy = _load_policy()
    allowed = policy.get("allowed_actions", ["*"])
    if not any(fnmatch.fnmatch(action, pat) for pat in allowed):
        raise HTTPException(status_code=403, detail=f"action not allowed by policy: {action}")
    if action == "screenshot" and not bool(policy.get("allow_screenshot", True)):
        raise HTTPException(status_code=403, detail="screenshots disabled by policy")
    now = time.time()
    _prune_old(now)
    limit = int(policy.get("max_actions_per_minute", 120))
    if len(_action_timestamps) >= limit:
        raise HTTPException(status_code=429, detail="wayland rate limit exceeded")
    _action_timestamps.append(now)
    return policy


# ── session detection ─────────────────────────────────────────────────────────

def _detect_session() -> str:
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    xdg = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if xdg == "x11":
        return "x11"
    if xdg == "wayland":
        return "wayland"
    return "unknown"


# ── subprocess helpers ────────────────────────────────────────────────────────

def _run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(cmd, check=True, capture_output=True, **kwargs)


async def _run_async(cmd: list[str]) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (proc.returncode or 0), stdout, stderr


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    return 0, 0


def _screenshot_response(data: bytes, backend: str) -> dict[str, Any]:
    width, height = _png_dimensions(data)
    return {
        "image": base64.b64encode(data).decode("ascii"),
        "width": width,
        "height": height,
        "backend": backend,
    }


async def _try_grim_screenshot() -> dict[str, Any] | None:
    try:
        code, stdout, _ = await _run_async(["grim", "-", "-t", "png"])
    except Exception:
        return None
    if code != 0 or not stdout:
        return None
    return _screenshot_response(stdout, "grim")


# ── wayland endpoints ─────────────────────────────────────────────────────────

@app.post("/wayland/move")
async def move(req: MoveRequest) -> dict[str, Any]:
    _assert_policy("move")
    session = _detect_session()
    if session == "wayland":
        try:
            await _run_async(["ydotool", "mousemove", "--absolute", str(req.x), str(req.y)])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"ydotool failed: {exc}") from exc
    else:
        try:
            await _run_async(["xdotool", "mousemove", str(req.x), str(req.y)])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"xdotool fallback failed: {exc}") from exc
    return {"ok": True, "backend": "wayland" if session == "wayland" else "x11"}


@app.post("/wayland/click")
async def click(req: ClickRequest) -> dict[str, Any]:
    _assert_policy("click")
    session = _detect_session()
    button_map = {"left": "0", "middle": "1", "right": "2"}
    if req.button not in button_map:
        raise HTTPException(status_code=400, detail=f"unsupported button: {req.button}")
    if session == "wayland":
        try:
            await _run_async(["ydotool", "mousemove", "--absolute", str(req.x), str(req.y)])
            await _run_async(["ydotool", "click", button_map[req.button]])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"ydotool click failed: {exc}") from exc
    else:
        xbtn = {"left": "1", "middle": "2", "right": "3"}[req.button]
        try:
            await _run_async(["xdotool", "mousemove", str(req.x), str(req.y)])
            await _run_async(["xdotool", "click", xbtn])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"xdotool click failed: {exc}") from exc
    return {"ok": True, "backend": "wayland" if session == "wayland" else "x11"}


@app.post("/wayland/type")
async def type_text(req: TypeRequest) -> dict[str, Any]:
    _assert_policy("type")
    session = _detect_session()
    if session == "wayland":
        try:
            await _run_async(["ydotool", "type", req.text])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"ydotool type failed: {exc}") from exc
    else:
        try:
            await _run_async(["xdotool", "type", "--delay", "1", req.text])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"xdotool type failed: {exc}") from exc
    return {"ok": True, "backend": "wayland" if session == "wayland" else "x11"}


@app.post("/wayland/screenshot")
async def screenshot() -> dict[str, Any]:
    _assert_policy("screenshot")
    session = _detect_session()

    if session == "wayland":
        grim_result = await _try_grim_screenshot()
        if grim_result is not None:
            return grim_result

    # scrot fallback
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        code, _, _ = await _run_async(["scrot", "-z", path])
        if code != 0:
            raise HTTPException(status_code=500, detail="screenshot failed: grim and scrot both unavailable")
        data = Path(path).read_bytes()
        return _screenshot_response(data, "scrot")
    finally:
        if os.path.exists(path):
            os.unlink(path)


@app.get("/wayland/windows")
async def list_windows() -> dict[str, Any]:
    _assert_policy("windows")
    # Try swaymsg first
    try:
        code, stdout, _ = await _run_async(["swaymsg", "-t", "get_tree"])
        if code == 0:
            tree = json.loads(stdout.decode("utf-8", errors="replace"))
            windows = _extract_sway_windows(tree)
            return {"windows": windows, "backend": "swaymsg"}
    except Exception:
        pass

    # wmctrl fallback
    try:
        code, stdout, _ = await _run_async(["wmctrl", "-l"])
        if code == 0:
            windows = _parse_wmctrl(stdout.decode("utf-8", errors="replace"))
            return {"windows": windows, "backend": "wmctrl"}
    except Exception:
        pass

    return {"windows": [], "backend": "unavailable"}


def _extract_sway_windows(node: dict[str, Any]) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    if node.get("type") == "con" and node.get("name"):
        windows.append({
            "id": str(node.get("id", "")),
            "name": node.get("name", ""),
            "app_id": node.get("app_id") or node.get("window_properties", {}).get("class", ""),
            "focused": bool(node.get("focused", False)),
        })
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        windows.extend(_extract_sway_windows(child))
    return windows


def _parse_wmctrl(output: str) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 5:
            windows.append({"id": parts[0], "name": parts[4].strip(), "app_id": "", "focused": False})
    return windows


@app.post("/wayland/focus")
async def focus_window(req: FocusRequest) -> dict[str, Any]:
    _assert_policy("focus")
    try:
        code, _, _ = await _run_async(["swaymsg", f"[id={req.window_id}] focus"])
        if code == 0:
            return {"ok": True, "backend": "swaymsg"}
    except Exception:
        pass
    try:
        await _run_async(["wmctrl", "-ia", req.window_id])
        return {"ok": True, "backend": "wmctrl"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"focus failed: {exc}") from exc


@app.get("/wayland/session-type")
def session_type() -> dict[str, str]:
    return {"type": _detect_session()}
