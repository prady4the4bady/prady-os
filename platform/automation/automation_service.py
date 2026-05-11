from __future__ import annotations

import base64
import fnmatch
import io
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
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

app = FastAPI(title="Kryos Automation Service", version="1.0.0")

DEFAULT_POLICY_PATH = _ROOT / "vyrex" / "policies" / "screen_control.yaml"
_action_timestamps: deque[float] = deque()


class MouseMoveRequest(BaseModel):
    x: int
    y: int


class MouseClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"


class MouseScrollRequest(BaseModel):
    x: int
    y: int
    dx: int = 0
    dy: int = 0


class KeyboardTypeRequest(BaseModel):
    text: str


class KeyboardHotkeyRequest(BaseModel):
    keys: list[str]


class KeyboardKeyRequest(BaseModel):
    key: str


class VisionVerifyRequest(BaseModel):
    screenshot_b64: str
    expected_state_description: str


_reference_hash: list[float] | None = None


def _policy_path() -> Path:
    configured = os.environ.get("VYREX_POLICY_PATH")
    return Path(configured) if configured else DEFAULT_POLICY_PATH


def _load_policy() -> dict[str, Any]:
    path = _policy_path()
    if not path.exists():
        return {
            "allowed_apps": ["*"],
            "max_actions_per_minute": 120,
            "screenshot_allowed": True,
            "block_sensitive_windows": [],
        }
    with open(path, encoding="utf-8") as handle:
        policy = yaml.safe_load(handle) or {}
    policy.setdefault("allowed_apps", ["*"])
    policy.setdefault("max_actions_per_minute", 120)
    policy.setdefault("screenshot_allowed", True)
    policy.setdefault("block_sensitive_windows", [])
    return policy


def _prune_old_actions(now: Optional[float] = None) -> None:
    cutoff = (now or time.time()) - 60.0
    while _action_timestamps and _action_timestamps[0] < cutoff:
        _action_timestamps.popleft()


def _record_action_or_raise(limit: int) -> None:
    now = time.time()
    _prune_old_actions(now)
    if len(_action_timestamps) >= limit:
        raise HTTPException(status_code=429, detail="automation rate limit exceeded")
    _action_timestamps.append(now)


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def _run_first_available(commands: list[list[str]]) -> subprocess.CompletedProcess[str]:
    last_error: Exception | None = None
    for command in commands:
        try:
            return _run_command(command)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"automation backend command failed: {last_error}") from last_error


def _get_pyautogui() -> Any:
    import pyautogui

    pyautogui.FAILSAFE = False
    return pyautogui


def _capture_windows_image() -> Any:
    from PIL import ImageGrab

    return ImageGrab.grab()


def _active_window_title_linux() -> str:
    try:
        result = _run_command(["xdotool", "getactivewindow", "getwindowname"])
        return result.stdout.strip() or "Unknown"
    except Exception:
        return "Unknown"


def _get_active_window_title() -> str:
    if os.name == "nt":
        return os.environ.get("KRYOS_ACTIVE_WINDOW", "Desktop")
    return _active_window_title_linux()


def _assert_policy(operation: str) -> dict[str, Any]:
    policy = _load_policy()
    title = _get_active_window_title()
    lowered = title.lower()

    for pattern in policy.get("block_sensitive_windows", []):
        if fnmatch.fnmatch(lowered, pattern.lower()):
            raise HTTPException(status_code=403, detail=f"blocked sensitive window: {title}")

    allowed_apps = policy.get("allowed_apps", ["*"])
    if not any(fnmatch.fnmatch(title, pattern) for pattern in allowed_apps):
        raise HTTPException(status_code=403, detail=f"window not allowed by policy: {title}")

    if operation == "screenshot" and not bool(policy.get("screenshot_allowed", True)):
        raise HTTPException(status_code=403, detail="screenshots disabled by policy")

    _record_action_or_raise(int(policy.get("max_actions_per_minute", 120)))
    return policy


def _screen_info_linux() -> dict[str, Any]:
    try:
        result = _run_command(["xdotool", "getdisplaygeometry"])
        width, height = result.stdout.strip().split()
        return {"width": int(width), "height": int(height), "scale": 1.0}
    except Exception:
        return {"width": 1920, "height": 1080, "scale": 1.0}


def _screen_info_windows() -> dict[str, Any]:
    pyautogui = _get_pyautogui()
    width, height = pyautogui.size()
    return {"width": int(width), "height": int(height), "scale": 1.0}


def _get_screen_info() -> dict[str, Any]:
    if os.name == "nt":
        return _screen_info_windows()
    return _screen_info_linux()


def _encode_image(image: Any) -> tuple[str, int, int]:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    width, height = image.size
    return encoded, int(width), int(height)


def _read_png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("invalid PNG screenshot data")
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _hash_grid_from_b64(screenshot_b64: str) -> list[float]:
    raw = base64.b64decode(screenshot_b64.encode("ascii"))
    if not raw:
        return [0.0] * 64
    chunk_size = max(1, len(raw) // 64)
    values: list[float] = []
    for idx in range(64):
        start = idx * chunk_size
        end = len(raw) if idx == 63 else min(len(raw), start + chunk_size)
        chunk = raw[start:end]
        if not chunk:
            values.append(0.0)
        else:
            values.append(sum(chunk) / len(chunk))
    return values


async def _verify_with_ollama(screenshot_b64: str, expected_desc: str) -> tuple[bool, float]:
    import httpx as _httpx

    model = os.environ.get("VISION_VERIFY_MODEL", "llava")
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    _vyrex = os.environ.get("VYREX_PROXY_URL", "")
    _infer_base = _vyrex if _vyrex else ollama_url
    _gen_path = "/proxy/generate" if _vyrex else "/api/generate"
    prompt = f"Does this screenshot show: {expected_desc}? Answer only YES or NO."

    async with _httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"{_infer_base}{_gen_path}",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "images": [screenshot_b64],
            },
        )
    response.raise_for_status()
    payload = response.json()
    text = str(payload.get("response", "")).strip().upper()
    yes = text.startswith("YES")
    no = text.startswith("NO")
    if yes:
        return True, 0.95
    if no:
        return False, 0.95
    return False, 0.5


def _take_screenshot_windows() -> dict[str, Any]:
    image = _capture_windows_image()
    encoded, width, height = _encode_image(image)
    return {"image": encoded, "width": width, "height": height}


def _take_screenshot_linux() -> dict[str, Any]:
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        _run_command(["scrot", "-z", path])
        data = Path(path).read_bytes()
        width, height = _read_png_size(data)
        encoded = base64.b64encode(data).decode("ascii")
        return {"image": encoded, "width": width, "height": height}
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _move_mouse(x: int, y: int) -> None:
    if os.name == "nt":
        _get_pyautogui().moveTo(x, y)
        return
    _run_first_available(
        [
            ["ydotool", "mousemove", "--absolute", str(x), str(y)],
            ["xdotool", "mousemove", str(x), str(y)],
        ]
    )


def _click_mouse(x: int, y: int, button: str) -> None:
    button_map = {"left": "1", "middle": "2", "right": "3"}
    if button not in button_map:
        raise HTTPException(status_code=400, detail=f"unsupported button: {button}")
    if os.name == "nt":
        _get_pyautogui().click(x=x, y=y, button=button)
        return
    _run_first_available(
        [
            ["ydotool", "mousemove", "--absolute", str(x), str(y)],
            ["xdotool", "mousemove", str(x), str(y)],
        ]
    )
    _run_first_available(
        [
            ["ydotool", "click", button_map[button]],
            ["xdotool", "click", button_map[button]],
        ]
    )


def _scroll_mouse(x: int, y: int, dx: int, dy: int) -> None:
    if os.name == "nt":
        pyautogui = _get_pyautogui()
        pyautogui.moveTo(x, y)
        if dy:
            pyautogui.scroll(dy)
        if dx:
            pyautogui.hscroll(dx)
        return

    _run_first_available(
        [
            ["ydotool", "mousemove", "--absolute", str(x), str(y)],
            ["xdotool", "mousemove", str(x), str(y)],
        ]
    )
    horizontal_button = "7" if dx > 0 else "6"
    vertical_button = "4" if dy > 0 else "5"
    for _ in range(abs(dy)):
        _run_first_available([["xdotool", "click", vertical_button]])
    for _ in range(abs(dx)):
        _run_first_available([["xdotool", "click", horizontal_button]])


def _type_text(text: str) -> None:
    if os.name == "nt":
        _get_pyautogui().write(text)
        return
    _run_first_available(
        [
            ["ydotool", "type", text],
            ["xdotool", "type", "--delay", "1", text],
        ]
    )


def _hotkey(keys: list[str]) -> None:
    if os.name == "nt":
        _get_pyautogui().hotkey(*keys)
        return
    _run_first_available(
        [
            ["ydotool", "key", *keys],
            ["xdotool", "key", "+".join(keys)],
        ]
    )


def _keydown(key: str) -> None:
    if os.name == "nt":
        _get_pyautogui().keyDown(key)
        return
    _run_first_available(
        [
            ["ydotool", "keydown", key],
            ["xdotool", "keydown", key],
        ]
    )


def _keyup(key: str) -> None:
    if os.name == "nt":
        _get_pyautogui().keyUp(key)
        return
    _run_first_available(
        [
            ["ydotool", "keyup", key],
            ["xdotool", "keyup", key],
        ]
    )


@app.post("/automation/screenshot")
def screenshot() -> dict[str, Any]:
    _assert_policy("screenshot")
    if os.name == "nt":
        return _take_screenshot_windows()
    return _take_screenshot_linux()


@app.post("/automation/mouse/move")
def mouse_move(req: MouseMoveRequest) -> dict[str, Any]:
    _assert_policy("mouse_move")
    _move_mouse(req.x, req.y)
    return {"ok": True}


@app.post("/automation/mouse/click")
def mouse_click(req: MouseClickRequest) -> dict[str, Any]:
    _assert_policy("mouse_click")
    _click_mouse(req.x, req.y, req.button)
    return {"ok": True}


@app.post("/automation/mouse/scroll")
def mouse_scroll(req: MouseScrollRequest) -> dict[str, Any]:
    _assert_policy("mouse_scroll")
    _scroll_mouse(req.x, req.y, req.dx, req.dy)
    return {"ok": True}


@app.post("/automation/keyboard/type")
def keyboard_type(req: KeyboardTypeRequest) -> dict[str, Any]:
    _assert_policy("keyboard_type")
    _type_text(req.text)
    return {"ok": True}


@app.post("/automation/keyboard/hotkey")
def keyboard_hotkey(req: KeyboardHotkeyRequest) -> dict[str, Any]:
    _assert_policy("keyboard_hotkey")
    _hotkey(req.keys)
    return {"ok": True}


@app.post("/automation/keyboard/keydown")
def keyboard_keydown(req: KeyboardKeyRequest) -> dict[str, Any]:
    _assert_policy("keyboard_keydown")
    _keydown(req.key)
    return {"ok": True}


@app.post("/automation/keyboard/keyup")
def keyboard_keyup(req: KeyboardKeyRequest) -> dict[str, Any]:
    _assert_policy("keyboard_keyup")
    _keyup(req.key)
    return {"ok": True}


@app.get("/automation/screen/info")
def screen_info() -> dict[str, Any]:
    return _get_screen_info()


@app.get("/automation/stats")
def stats() -> dict[str, Any]:
    policy = _load_policy()
    _prune_old_actions()
    return {
        "actions_last_minute": len(_action_timestamps),
        "rate_limit": int(policy.get("max_actions_per_minute", 120)),
    }


@app.post("/automation/vision-verify")
async def vision_verify(req: VisionVerifyRequest) -> dict[str, Any]:
    global _reference_hash

    _assert_policy("vision_verify")

    try:
        verified, confidence = await _verify_with_ollama(req.screenshot_b64, req.expected_state_description)
        return {"verified": verified, "confidence": confidence, "diff_regions": []}
    except Exception:
        current_hash = _hash_grid_from_b64(req.screenshot_b64)
        if _reference_hash is None:
            _reference_hash = current_hash
            return {"verified": True, "confidence": 1.0, "diff_regions": []}

        similarity = _cosine_similarity(_reference_hash, current_hash)
        diff_regions: list[dict[str, Any]] = []
        for idx, (a, b) in enumerate(zip(_reference_hash, current_hash)):
            delta = abs(a - b)
            if delta > 20:
                diff_regions.append({"row": idx // 8, "col": idx % 8, "delta": round(delta, 2)})
        return {
            "verified": similarity > 0.92,
            "confidence": round(similarity, 4),
            "diff_regions": diff_regions,
        }


# ── input router ──────────────────────────────────────────────────────────────

class RouteInputRequest(BaseModel):
    action_type: str  # move | click | type
    x: Optional[int] = None
    y: Optional[int] = None
    button: str = "left"
    text: Optional[str] = None


def _wayland_payload(req: RouteInputRequest) -> dict[str, Any]:
    if req.action_type == "type":
        return {"text": req.text or ""}
    payload: dict[str, Any] = {"x": req.x or 0, "y": req.y or 0}
    if req.action_type == "click":
        payload["button"] = req.button
    return payload


async def _route_wayland_input(req: RouteInputRequest) -> dict[str, Any]:
    wayland_url = os.environ.get("WAYLAND_MCP_URL", "http://wayland-mcp:8103")
    payload = _wayland_payload(req)
    try:
        import httpx as _httpx

        async with _httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{wayland_url}/wayland/{req.action_type}", json=payload)
        return resp.json() if resp.is_success else {"error": f"HTTP {resp.status_code}"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"wayland-mcp unreachable: {exc}") from exc


def _route_x11_input(req: RouteInputRequest) -> dict[str, Any]:
    if req.action_type == "move" and req.x is not None and req.y is not None:
        _run_command(["xdotool", "mousemove", str(req.x), str(req.y)])
        return {"ok": True}
    if req.action_type == "click" and req.x is not None and req.y is not None:
        btn_map = {"left": "1", "middle": "2", "right": "3"}
        btn = btn_map.get(req.button, "1")
        _run_command(["xdotool", "mousemove", str(req.x), str(req.y)])
        _run_command(["xdotool", "click", btn])
        return {"ok": True}
    if req.action_type == "type" and req.text is not None:
        _run_command(["xdotool", "type", "--delay", "1", req.text])
        return {"ok": True}
    raise HTTPException(status_code=400, detail=f"unsupported action_type for x11: {req.action_type}")


@app.post("/automation/route-input")
async def route_input(req: RouteInputRequest) -> dict[str, Any]:
    _assert_policy("route_input")
    t_start = time.time()
    wayland_display = os.environ.get("WAYLAND_DISPLAY")

    if wayland_display:
        result = await _route_wayland_input(req)

        latency_ms = round((time.time() - t_start) * 1000, 2)
        return {"backend": "wayland", "result": result, "latency_ms": latency_ms}

    try:
        result = _route_x11_input(req)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"xdotool failed: {exc}") from exc

    latency_ms = round((time.time() - t_start) * 1000, 2)
    return {"backend": "x11", "result": result, "latency_ms": latency_ms}
