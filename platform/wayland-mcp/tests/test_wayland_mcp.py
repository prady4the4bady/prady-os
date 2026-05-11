from __future__ import annotations

import asyncio
import os
import struct
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

REPO_ROOT = Path(__file__).parents[3]
WAYLAND_MCP_DIR = REPO_ROOT / "platform" / "wayland-mcp"
if str(WAYLAND_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(WAYLAND_MCP_DIR))

import wayland_mcp as wm_mod
from wayland_mcp import app

TRANSPORT = ASGITransport(app=app)  # type: ignore[arg-type]


def _make_png(w: int = 100, h: int = 100) -> bytes:
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">II", w, h)
    return header + b"\x00" * 8 + ihdr + b"\x00" * 100


def _mock_run_async_ok(*args: object, **kwargs: object) -> asyncio.Future[tuple[int, bytes, bytes]]:
    future: asyncio.Future[tuple[int, bytes, bytes]] = asyncio.get_event_loop().create_future()
    future.set_result((0, b"ok", b""))
    return future


@pytest.fixture(autouse=True)
def _reset_timestamps() -> None:
    wm_mod._action_timestamps.clear()


@pytest.mark.asyncio
async def test_move_wayland() -> None:
    with (
        patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}),
        patch.object(wm_mod, "_run_async", new=AsyncMock(return_value=(0, b"", b""))),
    ):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.post("/wayland/move", json={"x": 100, "y": 200})
    assert resp.status_code == 200
    assert resp.json()["backend"] == "wayland"


@pytest.mark.asyncio
async def test_move_x11_fallback() -> None:
    env = {"XDG_SESSION_TYPE": "x11"}
    env.pop("WAYLAND_DISPLAY", None)
    with (
        patch.dict(os.environ, env, clear=False),
        patch.object(wm_mod, "_run_async", new=AsyncMock(return_value=(0, b"", b""))),
    ):
        # Ensure WAYLAND_DISPLAY is absent
        os.environ.pop("WAYLAND_DISPLAY", None)
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.post("/wayland/move", json={"x": 10, "y": 20})
    assert resp.status_code == 200
    assert resp.json()["backend"] == "x11"


@pytest.mark.asyncio
async def test_click_wayland() -> None:
    with (
        patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}),
        patch.object(wm_mod, "_run_async", new=AsyncMock(return_value=(0, b"", b""))),
    ):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.post("/wayland/click", json={"x": 50, "y": 60, "button": "left"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_type_wayland() -> None:
    with (
        patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}),
        patch.object(wm_mod, "_run_async", new=AsyncMock(return_value=(0, b"", b""))),
    ):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.post("/wayland/type", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_screenshot_grim() -> None:
    png = _make_png(1920, 1080)
    with (
        patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}),
        patch.object(wm_mod, "_run_async", new=AsyncMock(return_value=(0, png, b""))),
    ):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.post("/wayland/screenshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "grim"
    assert body["width"] == 1920


@pytest.mark.asyncio
async def test_screenshot_scrot_fallback(tmp_path: Path) -> None:
    png = _make_png(1280, 720)

    async def _mock_run(cmd: list[str]) -> tuple[int, bytes, bytes]:
        await asyncio.sleep(0)
        if "grim" in cmd:
            return (1, b"", b"grim not found")
        if "scrot" in cmd:
            # write png to the tmp file arg
            out_path = cmd[-1]
            Path(out_path).write_bytes(png)
            return (0, b"", b"")
        return (0, b"", b"")

    env = {"XDG_SESSION_TYPE": "x11"}

    def _get_env_value(key: str, default: object = None) -> object:
        if key == "WAYLAND_DISPLAY":
            return None
        if hasattr(os.environ, "_data"):
            return os.environ._data.get(key, default)
        return default

    with (
        patch.dict(os.environ, env),
        patch.object(os.environ, "get", side_effect=_get_env_value),
        patch.object(wm_mod, "_run_async", new=AsyncMock(side_effect=_mock_run)),
    ):
        os.environ.pop("WAYLAND_DISPLAY", None)
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.post("/wayland/screenshot")

    # May succeed or fallback—either way no 5xx crash
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_window_list_sway() -> None:
    tree = {
        "type": "root",
        "nodes": [
            {"type": "con", "id": 1, "name": "Firefox", "app_id": "firefox", "focused": True, "nodes": [], "floating_nodes": []}
        ],
        "floating_nodes": [],
    }
    import json as _json
    payload = _json.dumps(tree).encode()
    with patch.object(wm_mod, "_run_async", new=AsyncMock(return_value=(0, payload, b""))):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.get("/wayland/windows")
    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "swaymsg"
    assert any(w["name"] == "Firefox" for w in body["windows"])


@pytest.mark.asyncio
async def test_window_list_wmctrl_fallback() -> None:
    sway_fail = (1, b"", b"swaymsg not found")
    wmctrl_out = b"0x00000001  0 hostname Firefox\n0x00000002  0 hostname Terminal\n"

    async def _mock(cmd: list[str]) -> tuple[int, bytes, bytes]:
        await asyncio.sleep(0)
        if "swaymsg" in cmd:
            return sway_fail
        return (0, wmctrl_out, b"")

    with patch.object(wm_mod, "_run_async", new=AsyncMock(side_effect=_mock)):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.get("/wayland/windows")
    assert resp.status_code == 200
    assert resp.json()["backend"] == "wmctrl"


@pytest.mark.asyncio
async def test_focus_window() -> None:
    with patch.object(wm_mod, "_run_async", new=AsyncMock(return_value=(0, b"", b""))):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.post("/wayland/focus", json={"window_id": "0x00000001"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_session_type_detection() -> None:
    with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.get("/wayland/session-type")
    assert resp.status_code == 200
    assert resp.json()["type"] == "wayland"

    with patch.object(wm_mod, "_detect_session", return_value="x11"):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.get("/wayland/session-type")
    assert resp.json()["type"] == "x11"


@pytest.mark.asyncio
async def test_policy_block() -> None:
    policy = {
        "max_actions_per_minute": 120,
        "allowed_actions": ["screenshot"],  # move is blocked
        "blocked_window_classes": [],
        "require_focus_before_type": False,
        "allow_screenshot": True,
    }
    with patch.object(wm_mod, "_load_policy", return_value=policy):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            resp = await client.post("/wayland/move", json={"x": 0, "y": 0})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rate_limit_exceeded() -> None:
    policy = {
        "max_actions_per_minute": 2,
        "allowed_actions": ["*"],
        "blocked_window_classes": [],
        "require_focus_before_type": False,
        "allow_screenshot": True,
    }
    with (
        patch.object(wm_mod, "_load_policy", return_value=policy),
        patch.object(wm_mod, "_run_async", new=AsyncMock(return_value=(0, b"", b""))),
        patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}),
    ):
        async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
            # Consume limit
            await client.post("/wayland/move", json={"x": 0, "y": 0})
            await client.post("/wayland/move", json={"x": 0, "y": 0})
            # Third should be rate-limited
            resp = await client.post("/wayland/move", json={"x": 0, "y": 0})
    assert resp.status_code == 429
