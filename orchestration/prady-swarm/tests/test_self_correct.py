"""Tests for the self-correction engine."""
import pytest
from unittest.mock import AsyncMock, patch

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)) + "/app")
from self_correct import SelfCorrectionEngine


@pytest.fixture
def engine():
    return SelfCorrectionEngine()


@pytest.mark.asyncio
async def test_correct_succeeds_on_first_attempt(engine: SelfCorrectionEngine) -> None:
    task_result = {"task": {"id": "t1", "goal": "do x"}, "error": "timeout", "output": ""}
    with (
        patch.object(engine, "_call_model", new=AsyncMock(return_value="fixed output")),
        patch.object(engine, "_resubmit", new=AsyncMock(return_value={"status": "done"})),
        patch.object(engine, "_emit_event", new=AsyncMock()),
    ):
        result = await engine.correct(task_result)
    assert result["corrected"] is True
    assert result["output"] == "fixed output"


@pytest.mark.asyncio
async def test_correct_permanently_fails_after_max_attempts(engine: SelfCorrectionEngine) -> None:
    task_result = {"task": {"id": "t2"}, "error": "error", "output": ""}
    with (
        patch.object(engine, "_call_model", new=AsyncMock(return_value="output")),
        patch.object(engine, "_resubmit", new=AsyncMock(side_effect=Exception("still broken"))),
        patch.object(engine, "_emit_event", new=AsyncMock()),
    ):
        result = await engine.correct(task_result, max_attempts=2)
    assert result.get("permanently_failed") is True


@pytest.mark.asyncio
async def test_correct_skips_failed_model_calls(engine: SelfCorrectionEngine) -> None:
    task_result = {"task": {"id": "t3"}, "error": "err", "output": ""}
    with (
        patch.object(engine, "_call_model", new=AsyncMock(side_effect=Exception("model down"))),
        patch.object(engine, "_emit_event", new=AsyncMock()),
    ):
        result = await engine.correct(task_result, max_attempts=1)
    assert result.get("permanently_failed") is True


@pytest.mark.asyncio
async def test_emit_event_called_on_success(engine: SelfCorrectionEngine) -> None:
    task_result = {"task": {"id": "t4"}, "error": "", "output": ""}
    emit = AsyncMock()
    with (
        patch.object(engine, "_call_model", new=AsyncMock(return_value="ok")),
        patch.object(engine, "_resubmit", new=AsyncMock(return_value={"status": "done"})),
        patch.object(engine, "_emit_event", new=emit),
    ):
        await engine.correct(task_result)
    emit.assert_awaited_once_with("task.corrected", pytest.approx({"task": {"id": "t4"}, "error": "", "output": "ok", "corrected": True, "attempts": 1}))


@pytest.mark.asyncio
async def test_build_prompt_includes_error(engine: SelfCorrectionEngine) -> None:
    prompt = engine._build_prompt({"id": "t5"}, "NullPointerException", "partial output")
    assert "NullPointerException" in prompt
    assert "partial output" in prompt
