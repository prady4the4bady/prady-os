"""Tests for ScreenAgent backend detection, OCR flow, and conductor routing."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.conductor import Conductor
from app.dag import DAG
from app.schemas import Subtask
from app.agents.screen_agent import ScreenAgent

pytestmark = pytest.mark.anyio


def test_backend_auto_detect_wayland_prefers_ydotool(monkeypatch: pytest.MonkeyPatch):
    agent = ScreenAgent(backend="auto")
    monkeypatch.setattr(agent, "_command_exists", lambda name: name == "ydotool")
    detected = agent._detect_backend({"WAYLAND_DISPLAY": "wayland-0"})
    assert detected == "ydotool"


def test_backend_auto_detect_x11_prefers_xdotool(monkeypatch: pytest.MonkeyPatch):
    agent = ScreenAgent(backend="auto")
    monkeypatch.setattr(agent, "_command_exists", lambda name: name == "xdotool")
    detected = agent._detect_backend({"DISPLAY": ":0"})
    assert detected == "xdotool"


async def test_move_cursor_uses_xdotool_when_forced(monkeypatch: pytest.MonkeyPatch):
    agent = ScreenAgent(backend="xdotool")

    async def fake_run(*args: str):
        await asyncio.sleep(0)
        assert args[0] == "xdotool"
        assert args[1] == "mousemove"
        return 0, "", ""

    monkeypatch.setattr(agent, "_run_command", fake_run)
    result = await agent.move_cursor(100, 200)
    assert result["status"] == "ok"
    assert result["backend"] == "xdotool"


async def test_ocr_pipeline_with_sample_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pil = pytest.importorskip("PIL.Image")

    image_path = tmp_path / "sample.png"
    img = pil.new("RGB", (120, 40), "white")
    img.save(image_path)

    agent = ScreenAgent(backend="auto", ocr_enabled=True, screenshot_dir=tmp_path)

    class FakeTesseract:
        @staticmethod
        def image_to_string(_img):
            return "Sample OCR Text"

    import app.agents.screen_agent as module

    monkeypatch.setattr(module, "pytesseract", FakeTesseract)
    result = await agent.ocr_region(path=str(image_path), x=0, y=0, width=120, height=40)

    assert result["status"] == "ok"
    assert result["text"] == "Sample OCR Text"


async def test_conductor_routes_screen_subtask_to_screen_agent(
    conductor: Conductor,
    monkeypatch: pytest.MonkeyPatch,
):
    called = {"ok": False}

    class StubScreenAgent:
        def requires_approval(self, action: str, policy: str) -> bool:
            return False

        async def execute(self, action: str, params):
            await asyncio.sleep(0)
            called["ok"] = True
            assert action == "click"
            assert params.get("button") == "left"
            return {"status": "ok", "backend": "stub"}

    conductor._agents["screen"] = StubScreenAgent()  # type: ignore[index]

    st = Subtask(
        subtask_id="screen-1",
        parent_task_id="task-screen",
        agent_type="screen",
        action="click",
        params={"button": "left"},
        depends_on=[],
    )

    dag = DAG()
    dag.add_node(st.subtask_id, st.depends_on)
    subtask_map = {st.subtask_id: st}

    await conductor._execute_subtask(st, "default", dag, subtask_map)

    assert called["ok"]
    assert st.status.value == "completed"
