"""Tests for AutonomousTaskExecutor."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap the import path
# ---------------------------------------------------------------------------
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from task_executor import AutonomousTaskExecutor, TaskResult  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_response(payload: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(payload)}}]
    }
    return mock_resp


def _make_executor(llm_payload: dict):
    """Build an AutonomousTaskExecutor with mocked dependencies."""
    vision_agent = MagicMock()
    vision_agent.capture_screen = MagicMock(return_value=MagicMock())
    vision_agent.capture_screen_bytes = MagicMock(return_value=b"\x89PNG\r\n\x1a\n")
    vision_agent.describe_screen = AsyncMock(return_value="Empty desktop")

    input_controller = MagicMock()

    memory_store = MagicMock()
    memory_store.search = AsyncMock(return_value=[])
    memory_store.store = AsyncMock()

    gateway_url = "http://fake-gateway"

    mock_resp = _make_llm_response(llm_payload)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    executor = AutonomousTaskExecutor(
        gateway_url=gateway_url,
        vision_agent=vision_agent,
        input_controller=input_controller,
        memory_store=memory_store,
    )
    return executor, mock_client


# ---------------------------------------------------------------------------
# execute_goal — happy path (done on first step)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_goal_completes_on_done_action(tmp_path, monkeypatch):
    """execute_goal yields steps and a final result; success=True when action=done."""
    import task_executor as te_mod
    monkeypatch.setattr(te_mod, "AUDIT_LOG_PATH", tmp_path / "task.jsonl")

    done_payload = {
        "action": "done",
        "params": {},
        "reasoning": "Goal already achieved",
        "goal_complete": True,
    }
    executor, mock_client = _make_executor(done_payload)

    with patch("httpx.AsyncClient", return_value=mock_client):
        events = []
        async for event in executor.execute_goal(
            goal="Open the browser",
            user_id="test-user",
            max_steps=10,
            task_id="test-task-001",
        ):
            events.append(event)

    # Last event should be the final result
    assert len(events) >= 1
    final = events[-1]
    assert final.get("type") == "result"
    assert final.get("success") is True
    assert "test-task-001" in final.get("task_id", "")


# ---------------------------------------------------------------------------
# execute_goal — max steps
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_goal_stops_at_max_steps(tmp_path, monkeypatch):
    """execute_goal stops after max_steps and reports failure."""
    import task_executor as te_mod
    monkeypatch.setattr(te_mod, "AUDIT_LOG_PATH", tmp_path / "task.jsonl")

    never_done_payload = {
        "action": "move_mouse",
        "params": {"x": 50, "y": 50},
        "reasoning": "Move to target",
        "goal_complete": False,
    }
    executor, mock_client = _make_executor(never_done_payload)

    with patch("httpx.AsyncClient", return_value=mock_client):
        events = []
        async for event in executor.execute_goal(
            goal="Loop forever",
            user_id="test-user",
            max_steps=3,
            task_id="test-task-002",
        ):
            events.append(event)

    final = events[-1]
    assert final.get("type") == "result"
    assert final.get("success") is False
    assert final.get("steps_taken") <= 3


# ---------------------------------------------------------------------------
# abort
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_abort_unknown_task_returns_false():
    """abort() returns False for an unknown task_id."""
    executor = AutonomousTaskExecutor(
        gateway_url="http://fake",
        vision_agent=MagicMock(),
        input_controller=MagicMock(),
        memory_store=MagicMock(),
    )
    result = executor.abort("no-such-task")
    assert result is False


@pytest.mark.asyncio
async def test_abort_running_task_returns_true(tmp_path, monkeypatch):
    """abort() returns True when called with a known active task_id."""
    import task_executor as te_mod
    monkeypatch.setattr(te_mod, "AUDIT_LOG_PATH", tmp_path / "task.jsonl")

    # Payload that keeps the executor busy (non-done action)
    slow_payload = {
        "action": "move_mouse",
        "params": {"x": 10, "y": 10},
        "reasoning": "Moving mouse",
        "goal_complete": False,
    }
    executor, _ = _make_executor(slow_payload)

    task_id = "abort-test-001"

    # Register the task manually
    executor._active_tasks.add(task_id)

    result = executor.abort(task_id)
    assert result is True
    assert task_id not in executor._active_tasks
