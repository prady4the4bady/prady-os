from __future__ import annotations

import asyncio
import base64
import io
import os
import subprocess
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    import mss
    from mss import tools as mss_tools
except Exception:  # pragma: no cover - optional import fallback
    mss = None
    mss_tools = None

try:
    import pyautogui

    pyautogui.FAILSAFE = False
except Exception:  # pragma: no cover - optional import fallback
    pyautogui = None

try:
    import pytesseract
except Exception:  # pragma: no cover - optional import fallback
    pytesseract = None

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional import fallback
    Image = None


SAFE_MODE = os.environ.get("SAFE_MODE", "true").lower() == "true"
WAYLAND_ACTIVE = bool(os.environ.get("WAYLAND_DISPLAY"))
CONFIRM_TTL_SECONDS = 5
_PYAUTOGUI_UNAVAILABLE = "pyautogui unavailable"
DESTRUCTIVE_HOTKEYS = {
    frozenset(("ctrl", "alt", "del")),
    frozenset(("alt", "f4")),
    frozenset(("super", "l")),
}


@dataclass
class FoundElement:
    x: int
    y: int
    w: int
    h: int
    confidence: float


class ScreenshotRequest(BaseModel):
    x: int | None = None
    y: int | None = None
    w: int | None = None
    h: int | None = None


class MoveRequest(BaseModel):
    x: int
    y: int
    duration_ms: int = 0


class ClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"
    double: bool = False


class DragRequest(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    duration_ms: int = 200


class KeyboardTypeRequest(BaseModel):
    text: str
    delay_ms_between_chars: int = 0


class HotkeyRequest(BaseModel):
    keys: list[str]


class KeyRequest(BaseModel):
    key: str


class OCRRegionRequest(BaseModel):
    x: int
    y: int
    w: int
    h: int


class ElementFindRequest(BaseModel):
    description: str


class MacroStopRequest(BaseModel):
    macro_id: str


class MacroReplayRequest(BaseModel):
    macro_id: str
    actions: list[dict[str, Any]] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    token: str


app = FastAPI(title="Kryos Computer Use Service", version="1.0.0")

_confirm_tokens: dict[str, float] = {}
_macro_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
_active_macro_id: str | None = None
_is_replaying = False


def _cleanup_confirm_tokens() -> None:
    now = time.time()
    expired = [token for token, expiry in _confirm_tokens.items() if expiry < now]
    for token in expired:
        _confirm_tokens.pop(token, None)


def _run_cmd(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _ydotool_click_code(button: str) -> str:
    return {"left": "0xC0", "middle": "0xC1", "right": "0xC2"}.get(button, "0xC0")


def _xdotool_click_code(button: str) -> str:
    return {"left": "1", "middle": "2", "right": "3"}.get(button, "1")


def _handle_move(backend: str, payload: dict[str, Any]) -> None:
    if backend == "wayland":
        _run_cmd(["ydotool", "mousemove", str(payload["x"]), str(payload["y"])])
        return
    _run_cmd(["xdotool", "mousemove", str(payload["x"]), str(payload["y"])])


def _handle_click(backend: str, payload: dict[str, Any]) -> None:
    _handle_move(backend, payload)
    if backend == "wayland":
        button_code = _ydotool_click_code(payload.get("button", "left"))
        _run_cmd(["ydotool", "click", button_code])
        if payload.get("double"):
            _run_cmd(["ydotool", "click", button_code])
        return
    button_code = _xdotool_click_code(payload.get("button", "left"))
    _run_cmd(["xdotool", "click", button_code])
    if payload.get("double"):
        _run_cmd(["xdotool", "click", button_code])


def _handle_drag(backend: str, payload: dict[str, Any]) -> None:
    if backend == "wayland":
        _run_cmd(["ydotool", "mousemove", str(payload["x1"]), str(payload["y1"])])
        _run_cmd(["ydotool", "mousedown", "0xC0"])
        _run_cmd(["ydotool", "mousemove", str(payload["x2"]), str(payload["y2"])])
        _run_cmd(["ydotool", "mouseup", "0xC0"])
        return
    _run_cmd(["xdotool", "mousemove", str(payload["x1"]), str(payload["y1"])])
    _run_cmd(["xdotool", "mousedown", "1"])
    _run_cmd(["xdotool", "mousemove", str(payload["x2"]), str(payload["y2"])])
    _run_cmd(["xdotool", "mouseup", "1"])


def _handle_type(backend: str, payload: dict[str, Any]) -> None:
    if backend == "wayland":
        _run_cmd(["ydotool", "type", payload["text"]])
        return
    _run_cmd(["xdotool", "type", "--", payload["text"]])


def _handle_key(backend: str, payload: dict[str, Any]) -> None:
    tool = "ydotool" if backend == "wayland" else "xdotool"
    _run_cmd([tool, "key", payload["key"]])


def _handle_hotkey(backend: str, payload: dict[str, Any]) -> None:
    tool = "ydotool" if backend == "wayland" else "xdotool"
    _run_cmd([tool, "key", "+".join(payload["keys"])])


_INPUT_HANDLERS = {
    "move": _handle_move,
    "click": _handle_click,
    "drag": _handle_drag,
    "type": _handle_type,
    "key": _handle_key,
    "hotkey": _handle_hotkey,
}


def _run_input_fallback(action: str, payload: dict[str, Any]) -> None:
    backend = "wayland" if WAYLAND_ACTIVE else "x11"
    handler = _INPUT_HANDLERS.get(action)
    if handler is None:
        return
    handler(backend, payload)


def _record_action(action: str, payload: dict[str, Any]) -> None:
    if _active_macro_id and not _is_replaying:
        _macro_store[_active_macro_id].append({"action": action, "params": payload, "timestamp": time.time()})


def _flash_red_border() -> None:
    if not SAFE_MODE:
        return

    def _draw() -> None:
        try:
            import tkinter as tk

            root = tk.Tk()
            root.attributes("-topmost", True)
            root.attributes("-alpha", 0.25)
            root.overrideredirect(True)
            root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")
            frame = tk.Frame(root, bg="red", highlightthickness=8, highlightbackground="red")
            frame.pack(fill="both", expand=True)
            root.after(250, root.destroy)
            root.mainloop()
        except Exception:
            time.sleep(0.25)

    threading.Thread(target=_draw, daemon=True).start()


def _to_png_b64(shot: Any) -> str:
    if mss_tools is not None:
        png_bytes = mss_tools.to_png(shot.rgb, shot.size)
        return base64.b64encode(png_bytes).decode("utf-8")

    if Image is not None:
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    # Last-resort fallback for constrained test/runtime environments.
    return base64.b64encode(shot.rgb).decode("utf-8")


def _capture_shot(req: ScreenshotRequest) -> Any:
    if mss is None:
        raise HTTPException(status_code=500, detail="mss not available")

    with mss.mss() as sct:
        if all(v is not None for v in (req.x, req.y, req.w, req.h)):
            monitor = {"left": req.x, "top": req.y, "width": req.w, "height": req.h}
        else:
            monitor = sct.monitors[0]

        return sct.grab(monitor)


def _shot_to_ocr_image(shot: Any) -> Any:
    if Image is not None:
        return Image.frombytes("RGB", shot.size, shot.rgb)
    return shot.rgb


def _execute_action(action: str, params: dict[str, Any]) -> None:
    if action == "mouse_move":
        _handle_move(MoveRequest(**params))
    elif action == "mouse_click":
        _handle_click(ClickRequest(**params))
    elif action == "mouse_drag":
        _handle_drag(DragRequest(**params))
    elif action == "keyboard_type":
        _handle_keyboard_type(KeyboardTypeRequest(**params))
    elif action == "keyboard_hotkey":
        _handle_keyboard_hotkey(HotkeyRequest(**params))
    elif action == "keyboard_key":
        _handle_keyboard_key(KeyRequest(**params))


def _is_destructive(keys: list[str]) -> bool:
    normalized = frozenset(k.lower().strip() for k in keys)
    return normalized in DESTRUCTIVE_HOTKEYS


def _require_confirmation_if_needed(keys: list[str]) -> None:
    if not SAFE_MODE or not _is_destructive(keys):
        return

    _cleanup_confirm_tokens()
    now = time.time()
    for token, expiry in _confirm_tokens.copy().items():
        if expiry >= now:
            _confirm_tokens.pop(token, None)
            return

    token = str(uuid.uuid4())
    _confirm_tokens[token] = time.time() + CONFIRM_TTL_SECONDS
    raise HTTPException(
        status_code=403,
        detail={
            "message": "destructive hotkey requires confirmation",
            "confirm_token": token,
            "expires_in_seconds": CONFIRM_TTL_SECONDS,
        },
    )


def _handle_move(req: MoveRequest) -> dict[str, Any]:
    duration = max(req.duration_ms, 0) / 1000.0
    payload = req.model_dump()
    try:
        if pyautogui is None:
            raise RuntimeError(_PYAUTOGUI_UNAVAILABLE)
        pyautogui.moveTo(req.x, req.y, duration=duration)
    except Exception:
        _run_input_fallback("move", payload)

    _record_action("mouse_move", payload)
    return {"ok": True}


def _handle_click(req: ClickRequest) -> dict[str, Any]:
    payload = req.model_dump()
    _flash_red_border()
    try:
        if pyautogui is None:
            raise RuntimeError(_PYAUTOGUI_UNAVAILABLE)
        pyautogui.moveTo(req.x, req.y, duration=0)
        pyautogui.click(x=req.x, y=req.y, button=req.button, clicks=2 if req.double else 1)
    except Exception:
        _run_input_fallback("click", payload)

    _record_action("mouse_click", payload)
    return {"ok": True}


def _handle_drag(req: DragRequest) -> dict[str, Any]:
    duration = max(req.duration_ms, 0) / 1000.0
    payload = req.model_dump()
    try:
        if pyautogui is None:
            raise RuntimeError(_PYAUTOGUI_UNAVAILABLE)
        pyautogui.moveTo(req.x1, req.y1)
        pyautogui.dragTo(req.x2, req.y2, duration=duration, button="left")
    except Exception:
        _run_input_fallback("drag", payload)

    _record_action("mouse_drag", payload)
    return {"ok": True}


def _handle_keyboard_type(req: KeyboardTypeRequest) -> dict[str, Any]:
    payload = req.model_dump()
    interval = max(req.delay_ms_between_chars, 0) / 1000.0
    try:
        if pyautogui is None:
            raise RuntimeError(_PYAUTOGUI_UNAVAILABLE)
        pyautogui.write(req.text, interval=interval)
    except Exception:
        _run_input_fallback("type", payload)

    _record_action("keyboard_type", payload)
    return {"ok": True}


def _handle_keyboard_hotkey(req: HotkeyRequest) -> dict[str, Any]:
    payload = req.model_dump()
    _require_confirmation_if_needed(req.keys)
    try:
        if pyautogui is None:
            raise RuntimeError(_PYAUTOGUI_UNAVAILABLE)
        pyautogui.hotkey(*req.keys)
    except Exception:
        _run_input_fallback("hotkey", payload)

    _record_action("keyboard_hotkey", payload)
    return {"ok": True}


def _handle_keyboard_key(req: KeyRequest) -> dict[str, Any]:
    payload = req.model_dump()
    try:
        if pyautogui is None:
            raise RuntimeError(_PYAUTOGUI_UNAVAILABLE)
        pyautogui.press(req.key)
    except Exception:
        _run_input_fallback("key", payload)

    _record_action("keyboard_key", payload)
    return {"ok": True}


@app.get("/screenshot")
@app.post("/screenshot")
async def screenshot(req: ScreenshotRequest | None = None) -> dict[str, Any]:
    req = req or ScreenshotRequest()
    shot = _capture_shot(req)
    png_b64 = _to_png_b64(shot)
    return {
        "ok": True,
        "encoding": "base64",
        "mime": "image/png",
        "image_b64": png_b64,
        "width": int(shot.size[0]),
        "height": int(shot.size[1]),
    }


@app.post("/mouse/move")
async def mouse_move(req: MoveRequest) -> dict[str, Any]:
    return _handle_move(req)


@app.post("/mouse/click")
async def mouse_click(req: ClickRequest) -> dict[str, Any]:
    return _handle_click(req)


@app.post("/mouse/drag")
async def mouse_drag(req: DragRequest) -> dict[str, Any]:
    return _handle_drag(req)


@app.post("/keyboard/type")
async def keyboard_type(req: KeyboardTypeRequest) -> dict[str, Any]:
    return _handle_keyboard_type(req)


@app.post("/keyboard/hotkey")
async def keyboard_hotkey(req: HotkeyRequest) -> dict[str, Any]:
    return _handle_keyboard_hotkey(req)


@app.post("/keyboard/key")
async def keyboard_key(req: KeyRequest) -> dict[str, Any]:
    return _handle_keyboard_key(req)


@app.post("/ocr/region")
async def ocr_region(req: OCRRegionRequest) -> dict[str, Any]:
    if pytesseract is None:
        raise HTTPException(status_code=500, detail="pytesseract not available")
    shot = _capture_shot(ScreenshotRequest(x=req.x, y=req.y, w=req.w, h=req.h))
    image = _shot_to_ocr_image(shot)
    text = pytesseract.image_to_string(image)
    return {"ok": True, "text": text.strip()}


@app.post("/element/find")
async def element_find(req: ElementFindRequest) -> dict[str, Any]:
    if pytesseract is None:
        return {"ok": True, "elements": []}

    shot = _capture_shot(ScreenshotRequest())
    image = _shot_to_ocr_image(shot)
    elements: list[FoundElement] = []

    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        query = req.description.lower().strip()
        for idx, txt in enumerate(data.get("text", [])):
            if not txt:
                continue
            if query in txt.lower():
                elements.append(
                    FoundElement(
                        x=int(data["left"][idx]),
                        y=int(data["top"][idx]),
                        w=int(data["width"][idx]),
                        h=int(data["height"][idx]),
                        confidence=max(0.0, min(1.0, float(data["conf"][idx]) / 100.0)),
                    )
                )
    except Exception:
        pass

    return {"ok": True, "elements": [asdict(e) for e in elements]}


@app.post("/macro/record")
async def macro_record() -> dict[str, Any]:
    global _active_macro_id
    macro_id = str(uuid.uuid4())
    _macro_store[macro_id] = []
    _active_macro_id = macro_id
    return {"ok": True, "macro_id": macro_id}


@app.post("/macro/stop")
async def macro_stop(req: MacroStopRequest) -> dict[str, Any]:
    global _active_macro_id
    actions = _macro_store.get(req.macro_id, [])
    if _active_macro_id == req.macro_id:
        _active_macro_id = None
    return {"ok": True, "macro_id": req.macro_id, "actions": actions}


@app.post("/macro/replay")
async def macro_replay(req: MacroReplayRequest) -> dict[str, Any]:
    global _is_replaying

    actions = req.actions if req.actions else _macro_store.get(req.macro_id, [])
    if not actions:
        return {"ok": True, "macro_id": req.macro_id, "replayed": 0}

    replayed = 0
    _is_replaying = True
    try:
        for item in actions:
            action_name = item.get("action")
            params = item.get("params", {})
            if action_name:
                _execute_action(action_name, params)
                replayed += 1
    finally:
        _is_replaying = False

    return {"ok": True, "macro_id": req.macro_id, "replayed": replayed}


@app.post("/confirm")
async def confirm(req: ConfirmRequest) -> dict[str, Any]:
    _cleanup_confirm_tokens()
    expiry = _confirm_tokens.get(req.token)
    if not expiry:
        raise HTTPException(status_code=404, detail="confirmation token not found")
    if expiry < time.time():
        _confirm_tokens.pop(req.token, None)
        raise HTTPException(status_code=410, detail="confirmation token expired")

    _confirm_tokens[req.token] = time.time() + CONFIRM_TTL_SECONDS
    return {"ok": True, "token": req.token, "valid_for_seconds": CONFIRM_TTL_SECONDS}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "safe_mode": SAFE_MODE,
        "wayland": WAYLAND_ACTIVE,
        "recording": _active_macro_id is not None,
        "macros": len(_macro_store),
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8106)
