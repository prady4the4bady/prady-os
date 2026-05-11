"""Tests for PraxAgent: think/act/remember/recall."""
from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import httpx
import pytest
import respx

from app.agent_instance import AgentStatus, PraxAgent
from app.rag_store import RAGStore

pytestmark = pytest.mark.anyio


@pytest.fixture()
def rag() -> RAGStore:
    return RAGStore(path=":memory:")


@pytest.fixture()
def agent(rag: RAGStore) -> PraxAgent:
    return PraxAgent(
        model_id="test-model",
        gateway_url="http://fake-gateway",
        workflow_engine_url="http://fake-workflow",
        rag_store=rag,
    )


# ---------------------------------------------------------------------------
# think
# ---------------------------------------------------------------------------


@respx.mock
async def test_think_calls_gateway(agent: PraxAgent) -> None:
    respx.post("http://fake-gateway/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "my plan"}, "finish_reason": "stop"}
                ]
            },
        )
    )
    result = await agent.think("Do something interesting")
    assert result == "my plan"


@respx.mock
async def test_think_returns_empty_on_empty_choices(agent: PraxAgent) -> None:
    respx.post("http://fake-gateway/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": []})
    )
    result = await agent.think("task")
    assert result == ""


# ---------------------------------------------------------------------------
# remember / recall
# ---------------------------------------------------------------------------


async def test_remember_and_recall(agent: PraxAgent) -> None:
    await agent.remember("test-key", "important information about the task")
    results = await agent.recall("important information")
    assert len(results) >= 1
    assert any("important" in r["content"] for r in results)


async def test_recall_empty_when_no_rag() -> None:
    agent_no_rag = PraxAgent(
        gateway_url="http://fake-gateway",
        workflow_engine_url="http://fake-workflow",
        rag_store=None,
    )
    results = await agent_no_rag.recall("anything")
    assert results == []


async def test_remember_no_rag_does_not_raise() -> None:
    agent_no_rag = PraxAgent(
        gateway_url="http://fake-gateway",
        workflow_engine_url="http://fake-workflow",
        rag_store=None,
    )
    # Should not raise
    await agent_no_rag.remember("k", "v")


# ---------------------------------------------------------------------------
# act
# ---------------------------------------------------------------------------


@respx.mock
async def test_act_workflow_type(agent: PraxAgent) -> None:
    respx.post("http://fake-workflow/tasks").mock(
        return_value=httpx.Response(200, json={"task_id": "wf-1", "status": "accepted"})
    )
    result = await agent.act({"type": "workflow", "goal": "build something"})
    assert result["status"] == "accepted"


async def test_act_unknown_type_skipped(agent: PraxAgent) -> None:
    result = await agent.act({"type": "undefined_action"})
    assert result["status"] == "skipped"


# ---------------------------------------------------------------------------
# run (full loop)
# ---------------------------------------------------------------------------


@respx.mock
async def test_run_full_loop(agent: PraxAgent) -> None:
    respx.post("http://fake-gateway/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "execute plan A"}, "finish_reason": "stop"}
                ]
            },
        )
    )
    respx.post("http://fake-workflow/tasks").mock(
        return_value=httpx.Response(200, json={"task_id": "t1", "status": "accepted"})
    )

    record = await agent.run("do something useful")
    assert record["status"] == "done"
    assert agent.status == AgentStatus.DONE
    assert "reasoning" in record


@respx.mock
async def test_run_marks_failed_on_error(agent: PraxAgent) -> None:
    respx.post("http://fake-gateway/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    record = await agent.run("task that will fail")
    assert record["status"] == "failed"
    assert agent.status == AgentStatus.FAILED
    assert "error" in record


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


def test_to_dict_fields(agent: PraxAgent) -> None:
    d = agent.to_dict()
    assert "agent_id" in d
    assert "status" in d
    assert "model_id" in d
