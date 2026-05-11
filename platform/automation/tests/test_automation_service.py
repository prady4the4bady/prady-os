from __future__ import annotations

import asyncio
import base64
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).parents[3]
AUTOMATION_DIR = REPO_ROOT / "platform" / "automation"
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

import automation_service as service

PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn8s3sAAAAASUVORK5CYII="
)


class FakePyAutoGUI:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def move_to(self, x: int, y: int) -> None:
        self.calls.append(("moveTo", x, y))

    def click(self, *, x: int, y: int, button: str) -> None:
        self.calls.append(("click", x, y, button))

    def scroll(self, amount: int) -> None:
        self.calls.append(("scroll", amount))

    def hscroll(self, amount: int) -> None:
        self.calls.append(("hscroll", amount))

    def write(self, text: str) -> None:
        self.calls.append(("write", text))

    def hotkey(self, *keys: str) -> None:
        self.calls.append(("hotkey", *keys))

    def key_down(self, key: str) -> None:
        self.calls.append(("keyDown", key))

    def key_up(self, key: str) -> None:
        self.calls.append(("keyUp", key))

    def size(self) -> tuple[int, int]:
        return (1920, 1080)


@pytest.fixture()
def policy_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "screen_control.yaml"
    path.write_text(
        "name: screen-control\n"
        "version: '1.0'\n"
        "allowed_apps:\n"
        "  - '*'\n"
        "max_actions_per_minute: 120\n"
        "screenshot_allowed: true\n"
        "block_sensitive_windows:\n"
        "  - '*password*'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VYREX_POLICY_PATH", str(path))
    service._action_timestamps.clear()
    return path


@pytest_asyncio.fixture()
async def client(policy_file: Path) -> AsyncClient:
    transport = ASGITransport(app=service.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


class FakeImage:
    def __init__(self, width: int, height: int, payload: bytes) -> None:
        self.size = (width, height)
        self._payload = payload

    def save(self, buffer: Any, format: str = "PNG") -> None:
        buffer.write(self._payload)


@pytest.fixture()
def fake_pyautogui(monkeypatch: pytest.MonkeyPatch) -> FakePyAutoGUI:
    fake = FakePyAutoGUI()
    setattr(fake, "moveTo", fake.move_to)
    setattr(fake, "keyDown", fake.key_down)
    setattr(fake, "keyUp", fake.key_up)
    monkeypatch.setattr(service.os, "name", "nt", raising=False)
    monkeypatch.setattr(service, "_get_pyautogui", lambda: fake)
    monkeypatch.setattr(service, "_get_active_window_title", lambda: "Workspace")
    monkeypatch.setattr(service, "_get_screen_info", lambda: {"width": 1920, "height": 1080, "scale": 1.0})
    return fake


@pytest.mark.asyncio
async def test_screenshot_endpoint_windows(client: AsyncClient, fake_pyautogui: FakePyAutoGUI, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = base64.b64decode(PNG_1X1_BASE64)
    monkeypatch.setattr(service, "_capture_windows_image", lambda: FakeImage(64, 32, payload))
    response = await client.post("/automation/screenshot")
    assert response.status_code == 200
    body = response.json()
    assert body["width"] == 64
    assert body["height"] == 32
    assert body["image"]


@pytest.mark.asyncio
async def test_mouse_endpoints_windows(client: AsyncClient, fake_pyautogui: FakePyAutoGUI) -> None:
    move = await client.post("/automation/mouse/move", json={"x": 10, "y": 20})
    click = await client.post("/automation/mouse/click", json={"x": 10, "y": 20, "button": "left"})
    scroll = await client.post("/automation/mouse/scroll", json={"x": 10, "y": 20, "dx": 1, "dy": 2})
    assert move.status_code == 200
    assert click.status_code == 200
    assert scroll.status_code == 200
    assert ("moveTo", 10, 20) in fake_pyautogui.calls
    assert ("click", 10, 20, "left") in fake_pyautogui.calls
    assert ("scroll", 2) in fake_pyautogui.calls
    assert ("hscroll", 1) in fake_pyautogui.calls


@pytest.mark.asyncio
async def test_keyboard_endpoints_windows(client: AsyncClient, fake_pyautogui: FakePyAutoGUI) -> None:
    typed = await client.post("/automation/keyboard/type", json={"text": "hello"})
    hotkey = await client.post("/automation/keyboard/hotkey", json={"keys": ["ctrl", "c"]})
    keydown = await client.post("/automation/keyboard/keydown", json={"key": "shift"})
    keyup = await client.post("/automation/keyboard/keyup", json={"key": "shift"})
    assert typed.status_code == 200
    assert hotkey.status_code == 200
    assert keydown.status_code == 200
    assert keyup.status_code == 200
    assert ("write", "hello") in fake_pyautogui.calls
    assert ("hotkey", "ctrl", "c") in fake_pyautogui.calls
    assert ("keyDown", "shift") in fake_pyautogui.calls
    assert ("keyUp", "shift") in fake_pyautogui.calls


@pytest.mark.asyncio
async def test_screen_info_and_stats(client: AsyncClient, fake_pyautogui: FakePyAutoGUI) -> None:
    await client.post("/automation/mouse/move", json={"x": 1, "y": 2})
    info = await client.get("/automation/screen/info")
    stats = await client.get("/automation/stats")
    assert info.status_code == 200
    assert info.json() == {"width": 1920, "height": 1080, "scale": 1.0}
    assert stats.status_code == 200
    assert stats.json()["actions_last_minute"] == 1
    assert stats.json()["rate_limit"] == 120


@pytest.mark.asyncio
async def test_rate_limiting(client: AsyncClient, fake_pyautogui: FakePyAutoGUI, policy_file: Path) -> None:
    policy_file.write_text(
        "name: screen-control\n"
        "version: '1.0'\n"
        "allowed_apps:\n"
        "  - '*'\n"
        "max_actions_per_minute: 2\n"
        "screenshot_allowed: true\n"
        "block_sensitive_windows: []\n",
        encoding="utf-8",
    )
    first = await client.post("/automation/mouse/move", json={"x": 1, "y": 1})
    second = await client.post("/automation/mouse/move", json={"x": 2, "y": 2})
    third = await client.post("/automation/mouse/move", json={"x": 3, "y": 3})
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


@pytest.mark.asyncio
async def test_policy_enforcement_blocked_app(client: AsyncClient, fake_pyautogui: FakePyAutoGUI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_get_active_window_title", lambda: "Bitwarden Password Vault")
    response = await client.post("/automation/mouse/move", json={"x": 10, "y": 20})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_linux_screenshot_uses_scrot(client: AsyncClient, policy_file: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service.os, "name", "posix", raising=False)
    monkeypatch.setattr(service, "_get_active_window_title", lambda: "Workspace")

    def fake_run(command: list[str]) -> Any:
        if command[0] == "scrot":
            Path(command[-1]).write_bytes(base64.b64decode(PNG_1X1_BASE64))
        class Result:
            stdout = ""
        return Result()

    monkeypatch.setattr(service, "_run_command", fake_run)
    response = await client.post("/automation/screenshot")
    assert response.status_code == 200
    assert response.json()["width"] == 1
    assert response.json()["height"] == 1


@pytest.mark.asyncio
async def test_linux_mouse_move_uses_xdotool_fallback(client: AsyncClient, policy_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service.os, "name", "posix", raising=False)
    monkeypatch.setattr(service, "_get_active_window_title", lambda: "Workspace")
    calls: list[list[str]] = []

    def fake_run(command: list[str]) -> Any:
        calls.append(command)
        if command[0] == "ydotool":
            raise subprocess.CalledProcessError(1, command)
        class Result:
            stdout = ""
        return Result()

    monkeypatch.setattr(service, "_run_command", fake_run)
    response = await client.post("/automation/mouse/move", json={"x": 5, "y": 6})
    assert response.status_code == 200
    assert calls[0][0] == "ydotool"
    assert calls[1][0] == "xdotool"


@pytest.mark.asyncio
async def test_vision_verify_ollama_available(client: AsyncClient, fake_pyautogui: FakePyAutoGUI, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_ollama(*args: Any, **kwargs: Any) -> tuple[bool, float]:
        await asyncio.sleep(0)
        return (True, 0.97)

    monkeypatch.setattr(service, "_verify_with_ollama", fake_ollama)
    response = await client.post(
        "/automation/vision-verify",
        json={"screenshot_b64": PNG_1X1_BASE64, "expected_state_description": "window is open"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["verified"] is True
    assert payload["confidence"] == pytest.approx(0.97)


@pytest.mark.asyncio
async def test_vision_verify_ollama_unavailable(client: AsyncClient, fake_pyautogui: FakePyAutoGUI, monkeypatch: pytest.MonkeyPatch) -> None:
    service._reference_hash = None

    async def fail_ollama(*args: Any, **kwargs: Any) -> tuple[bool, float]:
        raise RuntimeError("ollama unavailable")

    monkeypatch.setattr(service, "_verify_with_ollama", fail_ollama)

    first = await client.post(
        "/automation/vision-verify",
        json={"screenshot_b64": PNG_1X1_BASE64, "expected_state_description": "state"},
    )
    second = await client.post(
        "/automation/vision-verify",
        json={"screenshot_b64": PNG_1X1_BASE64, "expected_state_description": "state"},
    )

    assert first.status_code == 200
    assert first.json()["verified"] is True
    assert second.status_code == 200
    assert second.json()["confidence"] >= 0.92


@pytest.mark.asyncio
async def test_route_input_wayland_available(
    client: AsyncClient, fake_pyautogui: FakePyAutoGUI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os as _os
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("WAYLAND_MCP_URL", "http://wayland-mcp-test:8103")

    import httpx as _httpx
    from unittest.mock import AsyncMock, MagicMock

    mock_resp = MagicMock()  # synchronous httpx.Response — json() is not async
    mock_resp.is_success = True
    mock_resp.json.return_value = {"ok": True, "backend": "wayland"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    monkeypatch.setattr(_httpx, "AsyncClient", lambda **kw: mock_client)

    resp = await client.post(
        "/automation/route-input",
        json={"action_type": "move", "x": 100, "y": 200},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "wayland"
    assert "latency_ms" in body


@pytest.mark.asyncio
async def test_route_input_x11_fallback(
    client: AsyncClient, fake_pyautogui: FakePyAutoGUI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> Any:
        calls.append(cmd)

        class FakeResult:
            stdout = ""
            returncode = 0

        return FakeResult()

    monkeypatch.setattr(service, "_run_command", fake_run)

    resp = await client.post(
        "/automation/route-input",
        json={"action_type": "move", "x": 50, "y": 75},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "x11"
    assert any("xdotool" in c for c in calls)
