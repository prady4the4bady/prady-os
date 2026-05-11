from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


REPO_ROOT = Path(__file__).parents[3]
COMPUTER_USE_DIR = REPO_ROOT / "platform" / "computer-use"
sys.path.insert(0, str(COMPUTER_USE_DIR))

import computer_use_service as cu
from computer_use_service import app
from task_loop import TaskExecutor

TRANSPORT = ASGITransport(app=app)


@pytest.fixture(autouse=True)
def _clear_state(monkeypatch):
    cu._macro_store.clear()
    cu._active_macro_id = None
    cu._confirm_tokens.clear()
    monkeypatch.setattr(cu, "SAFE_MODE", True)


def _fake_shot(width: int = 20, height: int = 20):
    rgb = bytes([0, 0, 0]) * width * height
    return SimpleNamespace(size=(width, height), rgb=rgb)


class _FakeMSS:
    def __init__(self):
        self.monitors = [{"left": 0, "top": 0, "width": 20, "height": 20}]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def grab(self, monitor):
        return _fake_shot(width=int(monitor.get("width", 20)), height=int(monitor.get("height", 20)))


@pytest.mark.asyncio
async def test_screenshot_full(monkeypatch):
    monkeypatch.setattr(cu, "mss", SimpleNamespace(mss=lambda: _FakeMSS()))

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/screenshot", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["image_b64"]


@pytest.mark.asyncio
async def test_screenshot_region(monkeypatch):
    monkeypatch.setattr(cu, "mss", SimpleNamespace(mss=lambda: _FakeMSS()))

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/screenshot", json={"x": 1, "y": 2, "w": 10, "h": 12})

    assert resp.status_code == 200
    body = resp.json()
    assert body["width"] == 10
    assert body["height"] == 12


@pytest.mark.asyncio
async def test_mouse_move(monkeypatch):
    fake_gui = SimpleNamespace(moveTo=MagicMock())
    monkeypatch.setattr(cu, "pyautogui", fake_gui)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/mouse/move", json={"x": 100, "y": 200, "duration_ms": 50})

    assert resp.status_code == 200
    fake_gui.moveTo.assert_called_once()


@pytest.mark.asyncio
async def test_mouse_click(monkeypatch):
    fake_gui = SimpleNamespace(moveTo=MagicMock(), click=MagicMock())
    monkeypatch.setattr(cu, "pyautogui", fake_gui)
    monkeypatch.setattr(cu, "_flash_red_border", lambda: None)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/mouse/click", json={"x": 10, "y": 20, "button": "left", "double": False})

    assert resp.status_code == 200
    fake_gui.click.assert_called_once()


@pytest.mark.asyncio
async def test_keyboard_type(monkeypatch):
    fake_gui = SimpleNamespace(write=MagicMock())
    monkeypatch.setattr(cu, "pyautogui", fake_gui)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/keyboard/type", json={"text": "hello", "delay_ms_between_chars": 5})

    assert resp.status_code == 200
    fake_gui.write.assert_called_once()


@pytest.mark.asyncio
async def test_keyboard_hotkey(monkeypatch):
    fake_gui = SimpleNamespace(hotkey=MagicMock())
    monkeypatch.setattr(cu, "pyautogui", fake_gui)
    monkeypatch.setattr(cu, "SAFE_MODE", False)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/keyboard/hotkey", json={"keys": ["ctrl", "c"]})

    assert resp.status_code == 200
    fake_gui.hotkey.assert_called_once_with("ctrl", "c")


@pytest.mark.asyncio
async def test_ocr_region(monkeypatch):
    monkeypatch.setattr(cu, "mss", SimpleNamespace(mss=lambda: _FakeMSS()))
    fake_tesseract = SimpleNamespace(image_to_string=MagicMock(return_value="Detected Text"))
    monkeypatch.setattr(cu, "pytesseract", fake_tesseract)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/ocr/region", json={"x": 0, "y": 0, "w": 20, "h": 20})

    assert resp.status_code == 200
    assert resp.json()["text"] == "Detected Text"


@pytest.mark.asyncio
async def test_element_find(monkeypatch):
    monkeypatch.setattr(cu, "mss", SimpleNamespace(mss=lambda: _FakeMSS()))
    fake_data = {
        "text": ["Search", "Button"],
        "left": [5, 10],
        "top": [6, 12],
        "width": [20, 30],
        "height": [8, 10],
        "conf": [90, 30],
    }
    fake_tesseract = SimpleNamespace(
        image_to_data=MagicMock(return_value=fake_data),
        Output=SimpleNamespace(DICT=object()),
    )
    monkeypatch.setattr(cu, "pytesseract", fake_tesseract)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/element/find", json={"description": "search"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["elements"]) == 1
    assert body["elements"][0]["x"] == 5


@pytest.mark.asyncio
async def test_macro_record_stop_replay(monkeypatch):
    fake_gui = SimpleNamespace(moveTo=MagicMock(), click=MagicMock(), write=MagicMock(), hotkey=MagicMock(), press=MagicMock(), dragTo=MagicMock())
    monkeypatch.setattr(cu, "pyautogui", fake_gui)
    monkeypatch.setattr(cu, "_flash_red_border", lambda: None)
    monkeypatch.setattr(cu, "SAFE_MODE", False)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        start = await ac.post("/macro/record")
        macro_id = start.json()["macro_id"]

        await ac.post("/mouse/click", json={"x": 1, "y": 1, "button": "left", "double": False})
        await ac.post("/keyboard/type", json={"text": "abc", "delay_ms_between_chars": 0})

        stop = await ac.post("/macro/stop", json={"macro_id": macro_id})
        actions = stop.json()["actions"]
        replay = await ac.post("/macro/replay", json={"macro_id": macro_id, "actions": actions})

    assert stop.status_code == 200
    assert len(actions) == 2
    assert replay.status_code == 200
    assert replay.json()["replayed"] == 2


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_safe_mode_flash(monkeypatch):
    fake_gui = SimpleNamespace(hotkey=MagicMock())
    monkeypatch.setattr(cu, "pyautogui", fake_gui)
    monkeypatch.setattr(cu, "SAFE_MODE", True)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/keyboard/hotkey", json={"keys": ["ctrl", "alt", "del"]})

    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert "confirm_token" in detail


@pytest.mark.asyncio
async def test_task_executor_single_step(tmp_path, monkeypatch):
    db_path = tmp_path / "task_journal.db"

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            await asyncio.sleep(0)
            if url.endswith("/screenshot"):
                return FakeResponse({"image_b64": "abc123"})
            return FakeResponse({"status": "ok"})

        async def post(self, url, json=None, **kwargs):
            await asyncio.sleep(0)
            if url.endswith("/v1/chat/completions"):
                return FakeResponse({
                    "choices": [
                        {"message": {"content": '{"action": "done", "params": {}, "reasoning": "complete"}'}}
                    ]
                })
            elif url.endswith("/policies/check"):
                # Return proper security policy response
                return FakeResponse({"allowed": True, "reason": ""})
            return FakeResponse({"ok": True})

    import task_loop as tl

    monkeypatch.setattr(tl.httpx, "AsyncClient", FakeClient)

    executor = TaskExecutor(
        proxy_url="http://vyrex-proxy:8105",
        computer_url="http://computer-use:8106",
        db_path=db_path,
    )
    result = await executor.run_task("open settings", max_steps=3)

    assert result.status == "done"
    assert result.steps == 1
    assert db_path.exists()
