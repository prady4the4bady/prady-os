"""PraxAgent: a single autonomous agent instance within a Kryos swarm."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from app.rag_store import RAGStore

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    DONE = "done"
    FAILED = "failed"


class PraxAgent:
    """A single Kryos agent that can think, act, remember, and recall."""

    def __init__(
        self,
        *,
        agent_id: Optional[str] = None,
        model_id: str = "lumyn-agent",
        memory_namespace: Optional[str] = None,
        gateway_url: str = "http://localhost:11430",
        workflow_engine_url: str = "http://localhost:11431",
        rag_store: Optional[RAGStore] = None,
        inbox: Optional[asyncio.Queue[Dict[str, Any]]] = None,
    ) -> None:
        self.agent_id = agent_id or f"agent-{uuid.uuid4().hex[:8]}"
        self.model_id = model_id
        self.memory_namespace = memory_namespace or self.agent_id
        self.status: AgentStatus = AgentStatus.IDLE
        self.task_history: List[Dict[str, Any]] = []
        self._gateway_url = gateway_url.rstrip("/")
        self._workflow_engine_url = workflow_engine_url.rstrip("/")
        self._rag = rag_store
        self.inbox: asyncio.Queue[Dict[str, Any]] = inbox or asyncio.Queue()
        self._result: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    async def run(self, task: str) -> Dict[str, Any]:
        """Execute a single agent task loop: think → act → return result."""
        self.status = AgentStatus.THINKING
        record: Dict[str, Any] = {
            "agent_id": self.agent_id,
            "task": task,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            context = await self._build_context(task)
            reasoning = await self.think(context)

            self.status = AgentStatus.ACTING
            action_result = await self.act({"type": "workflow", "goal": task, "reasoning": reasoning})

            record["reasoning"] = reasoning
            record["result"] = action_result
            record["status"] = "done"
            self.status = AgentStatus.DONE

            await self.remember(f"task:{task[:60]}", reasoning)

        except Exception as exc:
            logger.exception("Agent %s failed: %s", self.agent_id, exc)
            record["error"] = str(exc)
            record["status"] = "failed"
            self.status = AgentStatus.FAILED

        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.task_history.append(record)
        self._result = record
        return record

    # ------------------------------------------------------------------
    # Think
    # ------------------------------------------------------------------

    async def think(self, context: str) -> str:
        """Call Lumyn via model-gateway for a reasoning step."""
        payload = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Kryos autonomous agent. "
                        "Reason about the task and produce a concise action plan."
                    ),
                },
                {"role": "user", "content": context},
            ],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._gateway_url}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()

        data = resp.json()
        choices = data.get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("content", "") or ""
        return ""

    # ------------------------------------------------------------------
    # Act
    # ------------------------------------------------------------------

    async def act(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch action to appropriate executor (workflow-engine for now)."""
        action_type = action.get("type", "workflow")

        if action_type == "workflow":
            return await self._delegate_to_workflow_engine(action.get("goal", ""))

        logger.warning("Agent %s: unknown action type '%s'", self.agent_id, action_type)
        return {"status": "skipped", "reason": f"unknown action type: {action_type}"}

    async def _delegate_to_workflow_engine(self, goal: str) -> Dict[str, Any]:
        payload = {
            "goal": goal,
            "context": {"agent_id": self.agent_id, "model_id": self.model_id},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._workflow_engine_url}/tasks",
                json=payload,
            )
            resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    async def remember(self, key: str, value: str) -> None:
        """Store a value in ChromaDB shared memory."""
        if self._rag is None:
            return
        await self._rag.upsert(
            namespace=self.memory_namespace,
            key=key,
            content=value,
            metadata={"agent_id": self.agent_id},
        )

    async def recall(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantic search in ChromaDB shared memory."""
        if self._rag is None:
            return []
        return await self._rag.search(
            namespace=self.memory_namespace,
            query=query,
            top_k=top_k,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _build_context(self, task: str) -> str:
        """Augment task with recalled memories."""
        if self._rag is None:
            return task
        memories = await self.recall(task, top_k=3)
        if not memories:
            return task
        snippets = "\n".join(f"- {m['content'][:200]}" for m in memories)
        return f"{task}\n\nRelevant memory:\n{snippets}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "model_id": self.model_id,
            "status": self.status,
            "memory_namespace": self.memory_namespace,
            "task_history_count": len(self.task_history),
            "result": self._result,
        }
