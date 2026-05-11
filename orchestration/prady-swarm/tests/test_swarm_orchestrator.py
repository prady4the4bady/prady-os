"""Tests for SwarmOrchestrator: spawn, coordinate, merge, broadcast, status."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import anyio
import httpx
import pytest
import respx

from app.agent_instance import AgentStatus, PraxAgent
from app.rag_store import RAGStore
from app.swarm_orchestrator import SwarmOrchestrator, SwarmStatus

pytestmark = pytest.mark.anyio


@pytest.fixture()
def rag() -> RAGStore:
    return RAGStore(path=":memory:")


@pytest.fixture()
def orchestrator(rag: RAGStore) -> SwarmOrchestrator:
    return SwarmOrchestrator(
        model_id="test-model",
        gateway_url="http://fake-gateway",
        workflow_engine_url="http://fake-workflow",
        max_swarm_agents=5,
        rag_store=rag,
    )


# ---------------------------------------------------------------------------
# spawn_agent
# ---------------------------------------------------------------------------


async def test_spawn_agent_creates_agent(orchestrator: SwarmOrchestrator) -> None:
    agent = await orchestrator.spawn_agent("test task")
    assert isinstance(agent, PraxAgent)
    assert agent.agent_id in orchestrator._message_bus


async def test_spawn_agent_uses_override_model(orchestrator: SwarmOrchestrator) -> None:
    agent = await orchestrator.spawn_agent("task", model_id="custom-model")
    assert agent.model_id == "custom-model"


async def test_spawn_agent_default_model(orchestrator: SwarmOrchestrator) -> None:
    agent = await orchestrator.spawn_agent("task")
    assert agent.model_id == "test-model"


# ---------------------------------------------------------------------------
# merge_results
# ---------------------------------------------------------------------------


async def test_merge_results_counts(orchestrator: SwarmOrchestrator) -> None:
    results: List[Dict[str, Any]] = [
        {"agent_id": "a1", "status": "done", "reasoning": "plan A"},
        {"agent_id": "a2", "status": "done", "reasoning": "plan B"},
        {"agent_id": "a3", "status": "failed", "error": "oops"},
    ]
    merged = await orchestrator.merge_results(results)
    assert merged["total"] == 3
    assert merged["successful"] == 2
    assert merged["failed"] == 1
    assert "plan A" in merged["combined_reasoning"]
    assert "plan B" in merged["combined_reasoning"]


async def test_merge_results_empty(orchestrator: SwarmOrchestrator) -> None:
    merged = await orchestrator.merge_results([])
    assert merged["total"] == 0
    assert merged["successful"] == 0
    assert merged["failed"] == 0


# ---------------------------------------------------------------------------
# broadcast
# ---------------------------------------------------------------------------


async def test_broadcast_delivers_to_all(orchestrator: SwarmOrchestrator) -> None:
    agents = [await orchestrator.spawn_agent(f"task {i}") for i in range(3)]
    msg = {"type": "stop", "reason": "cancelled"}
    await orchestrator.broadcast(msg, [a.agent_id for a in agents])
    for agent in agents:
        assert not agent.inbox.empty()
        received = await agent.inbox.get()
        assert received == msg


async def test_broadcast_ignores_unknown_ids(orchestrator: SwarmOrchestrator) -> None:
    # Should not raise even if IDs are missing
    await orchestrator.broadcast({"ping": True}, ["nonexistent-id"])


# ---------------------------------------------------------------------------
# get_swarm_status
# ---------------------------------------------------------------------------


async def test_get_swarm_status_initially_empty(orchestrator: SwarmOrchestrator) -> None:
    status = await orchestrator.get_swarm_status()
    assert status == []


# ---------------------------------------------------------------------------
# cancel_swarm
# ---------------------------------------------------------------------------


async def test_cancel_nonexistent_swarm(orchestrator: SwarmOrchestrator) -> None:
    ok = await orchestrator.cancel_swarm("does-not-exist")
    assert ok is False


# ---------------------------------------------------------------------------
# coordinate_swarm: goal decomposition fallback when gateway unavailable
# ---------------------------------------------------------------------------


@respx.mock
async def test_coordinate_swarm_fallback_to_single_task(orchestrator: SwarmOrchestrator) -> None:
    """When model-gateway is unavailable, the swarm falls back to a single-agent task."""
    respx.post("http://fake-gateway/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("offline")
    )
    swarm_id = await orchestrator.coordinate_swarm("do everything", max_agents=3)
    assert swarm_id.startswith("swarm-")
    record = orchestrator.get_swarm(swarm_id)
    assert record is not None
    # fallback: 1 agent spawned for the original goal
    assert len(record.agents) == 1


@respx.mock
async def test_coordinate_swarm_decomposes_goal(orchestrator: SwarmOrchestrator) -> None:
    """When model-gateway returns a JSON array, swarm should spawn N agents."""
    decomposed = json.dumps(["subtask A", "subtask B", "subtask C"])
    respx.post("http://fake-gateway/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": decomposed},
                        "finish_reason": "stop",
                    }
                ]
            },
        )
    )
    swarm_id = await orchestrator.coordinate_swarm("big goal", max_agents=5)
    record = orchestrator.get_swarm(swarm_id)
    assert record is not None
    assert len(record.agents) == 3


@respx.mock
async def test_coordinate_swarm_respects_max_agents(orchestrator: SwarmOrchestrator) -> None:
    """max_agents in SwarmOrchestrator caps agents even if decomposition is larger."""
    big_list = json.dumps([f"subtask {i}" for i in range(10)])
    respx.post("http://fake-gateway/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": big_list}}]},
        )
    )
    # orchestrator max is 5; request max_agents=4
    swarm_id = await orchestrator.coordinate_swarm("mega goal", max_agents=4)
    record = orchestrator.get_swarm(swarm_id)
    assert record is not None
    assert len(record.agents) <= 4


# ---------------------------------------------------------------------------
# cancel_swarm on existing swarm
# ---------------------------------------------------------------------------


@respx.mock
async def test_cancel_running_swarm(orchestrator: SwarmOrchestrator) -> None:
    respx.post("http://fake-gateway/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("offline")
    )
    swarm_id = await orchestrator.coordinate_swarm("goal", max_agents=1)
    ok = await orchestrator.cancel_swarm(swarm_id)
    assert ok is True
    record = orchestrator.get_swarm(swarm_id)
    assert record is not None
    assert record.status == SwarmStatus.CANCELLED
