"""Shared pytest fixtures for kryos-swarm tests."""
from __future__ import annotations

from typing import Any, AsyncGenerator, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import httpx
import pytest
import pytest_anyio

import app.main as app_main
from app.config import SwarmConfig
from app.rag_store import RAGStore
from app.swarm_orchestrator import SwarmOrchestrator


# ---------------------------------------------------------------------------
# In-memory RAG
# ---------------------------------------------------------------------------


@pytest.fixture()
def rag() -> RAGStore:
    return RAGStore(path=":memory:")


# ---------------------------------------------------------------------------
# Config override
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_config() -> SwarmConfig:
    from pathlib import Path
    cfg = SwarmConfig(
        max_swarm_agents=3,
        swarm_model="test-model",
        workflow_engine_url="http://workflow-engine:8000",
        model_gateway_url="http://model-gateway:8000",
        chromadb_path=Path("/tmp/test-chroma"),
        log_level="DEBUG",
    )
    return cfg


# ---------------------------------------------------------------------------
# Mocked gateway / workflow engine helpers
# ---------------------------------------------------------------------------


def make_chat_response(content: str) -> Dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "model": "test-model",
    }


def make_workflow_response() -> Dict[str, Any]:
    return {"task_id": "task-abc", "status": "accepted"}


# ---------------------------------------------------------------------------
# Orchestrator fixture (no real HTTP)
# ---------------------------------------------------------------------------


@pytest.fixture()
def orchestrator(rag: RAGStore) -> SwarmOrchestrator:
    return SwarmOrchestrator(
        model_id="test-model",
        gateway_url="http://fake-gateway",
        workflow_engine_url="http://fake-workflow",
        max_swarm_agents=5,
        rag_store=rag,
    )
