"""SwarmOrchestrator: top-level multi-agent coordination layer."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from app.agent_instance import AgentStatus, PraxAgent
from app.rag_store import RAGStore

logger = logging.getLogger(__name__)


_DECOMPOSE_SYSTEM_PROMPT = """\
You are Kryos SwarmPlanner. Break the given goal into independent parallel subtasks.
Each subtask should be self-contained and executable by a single autonomous agent.

Respond ONLY with a valid JSON array of strings — each string is a subtask goal.
Keep the list concise (max 10 items). No markdown, no explanation.

Example for "Research the top 3 Linux distros and write a comparison":
["Research Arch Linux features and use cases",
 "Research Ubuntu features and use cases",
 "Research Fedora features and use cases",
 "Write a comparison of the three distros"]"""


class SwarmStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SwarmRecord:
    def __init__(
        self,
        swarm_id: str,
        goal: str,
        max_agents: int,
        model_id: str,
    ) -> None:
        self.swarm_id = swarm_id
        self.goal = goal
        self.max_agents = max_agents
        self.model_id = model_id
        self.status = SwarmStatus.RUNNING
        self.agents: List[PraxAgent] = []
        self.results: List[Dict[str, Any]] = []
        self.merged_result: Optional[Dict[str, Any]] = None
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.finished_at: Optional[str] = None
        self._cancelled = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "swarm_id": self.swarm_id,
            "goal": self.goal,
            "status": self.status,
            "agent_count": len(self.agents),
            "agents": [a.to_dict() for a in self.agents],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "merged_result": self.merged_result,
        }


class SwarmOrchestrator:
    """Coordinates multiple PraxAgent instances across one or more swarms."""

    def __init__(
        self,
        *,
        model_id: str = "lumyn-agent",
        gateway_url: str = "http://localhost:11430",
        workflow_engine_url: str = "http://localhost:11431",
        max_swarm_agents: int = 10,
        rag_store: Optional[RAGStore] = None,
    ) -> None:
        self._model_id = model_id
        self._gateway_url = gateway_url.rstrip("/")
        self._workflow_engine_url = workflow_engine_url.rstrip("/")
        self._max_agents = max_swarm_agents
        self._rag = rag_store
        self._swarms: Dict[str, SwarmRecord] = {}
        # Global message bus: agent_id → Queue
        self._message_bus: Dict[str, asyncio.Queue[Dict[str, Any]]] = {}
        self._swarm_tasks: Dict[str, asyncio.Task[None]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def spawn_agent(
        self,
        task: str,
        model_id: Optional[str] = None,
        context: Optional[str] = None,
        *,
        swarm_id: Optional[str] = None,
    ) -> PraxAgent:
        """Create a new PraxAgent, register it on the message bus, and return it."""
        await asyncio.sleep(0)
        inbox: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        agent = PraxAgent(
            model_id=model_id or self._model_id,
            gateway_url=self._gateway_url,
            workflow_engine_url=self._workflow_engine_url,
            rag_store=self._rag,
            inbox=inbox,
        )
        self._message_bus[agent.agent_id] = inbox
        logger.info(
            "SwarmOrchestrator: spawned agent %s for swarm=%s task=%r",
            agent.agent_id,
            swarm_id or "standalone",
            task[:80],
        )
        return agent

    async def coordinate_swarm(
        self,
        goal: str,
        max_agents: int = 5,
        model_id: Optional[str] = None,
    ) -> str:
        """Decompose goal into parallel subtasks, run agents, return swarm_id."""
        effective_max = min(max_agents, self._max_agents)
        effective_model = model_id or self._model_id
        swarm_id = f"swarm-{uuid.uuid4().hex[:10]}"
        record = SwarmRecord(
            swarm_id=swarm_id,
            goal=goal,
            max_agents=effective_max,
            model_id=effective_model,
        )
        self._swarms[swarm_id] = record

        subtasks = await self._decompose_goal(goal, max_tasks=effective_max)
        logger.info(
            "SwarmOrchestrator: swarm=%s goal=%r → %d subtasks",
            swarm_id,
            goal[:80],
            len(subtasks),
        )
        record._subtasks = subtasks  # type: ignore[attr-defined]

        for task in subtasks:
            agent = await self.spawn_agent(task, model_id=effective_model, swarm_id=swarm_id)
            record.agents.append(agent)

        # Fire and forget — results collected by background task
        swarm_task = asyncio.create_task(self._run_swarm(record))
        self._swarm_tasks[swarm_id] = swarm_task
        return swarm_id

    async def merge_results(self, agent_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate multi-agent outputs into a unified result."""
        await asyncio.sleep(0)
        successful = [r for r in agent_results if r.get("status") == "done"]
        failed = [r for r in agent_results if r.get("status") == "failed"]
        combined_reasoning = "\n\n".join(
            f"[{r.get('agent_id', 'unknown')}] {r.get('reasoning', '')}"
            for r in successful
            if r.get("reasoning")
        )
        return {
            "total": len(agent_results),
            "successful": len(successful),
            "failed": len(failed),
            "combined_reasoning": combined_reasoning,
            "results": agent_results,
        }

    async def broadcast(
        self,
        message: Dict[str, Any],
        agent_ids: List[str],
    ) -> None:
        """Send a message to multiple agents simultaneously via their inboxes."""
        coros = []
        for aid in agent_ids:
            queue = self._message_bus.get(aid)
            if queue is not None:
                coros.append(queue.put(message))
            else:
                logger.warning("broadcast: agent %s not found on bus", aid)
        if coros:
            await asyncio.gather(*coros)

    async def get_swarm_status(self) -> List[Dict[str, Any]]:
        """Return status of all active swarms."""
        await asyncio.sleep(0)
        return [r.to_dict() for r in self._swarms.values()]

    def get_swarm(self, swarm_id: str) -> Optional[SwarmRecord]:
        return self._swarms.get(swarm_id)

    async def cancel_swarm(self, swarm_id: str) -> bool:
        await asyncio.sleep(0)
        record = self._swarms.get(swarm_id)
        if record is None:
            return False
        record._cancelled = True
        record.status = SwarmStatus.CANCELLED
        record.finished_at = datetime.now(timezone.utc).isoformat()
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _decompose_goal(self, goal: str, max_tasks: int = 5) -> List[str]:
        """Call model-gateway to break the goal into parallel subtasks."""
        import json

        payload = {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": _DECOMPOSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Break this goal into at most {max_tasks} parallel subtasks:\n{goal}",
                },
            ],
            "temperature": 0.1,
        }
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(
                    f"{self._gateway_url}/v1/chat/completions",
                    json=payload,
                )
                resp.raise_for_status()

            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()
            subtasks: List[str] = json.loads(raw)
            if not isinstance(subtasks, list):
                raise ValueError("expected JSON array")
            return [str(t) for t in subtasks[:max_tasks]]

        except Exception as exc:
            logger.warning(
                "SwarmOrchestrator: goal decomposition failed (%s); "
                "running as single agent",
                exc,
            )
            return [goal]

    async def _run_swarm(self, record: SwarmRecord) -> None:
        """Execute all agents concurrently and merge results."""
        if not record.agents:
            record.status = SwarmStatus.DONE
            record.finished_at = datetime.now(timezone.utc).isoformat()
            record.merged_result = await self.merge_results([])
            return

        agent_list = record.agents
        subtasks: List[str] = getattr(record, "_subtasks", [record.goal] * len(agent_list))

        coros = [
            agent.run(subtasks[i] if i < len(subtasks) else record.goal)
            for i, agent in enumerate(agent_list)
        ]

        results = await asyncio.gather(*coros, return_exceptions=True)
        agent_results: List[Dict[str, Any]] = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                agent_results.append(
                    {
                        "agent_id": agent_list[i].agent_id,
                        "status": "failed",
                        "error": str(res),
                    }
                )
            else:
                agent_results.append(res)  # type: ignore[arg-type]

        record.results = agent_results
        record.merged_result = await self.merge_results(agent_results)

        if record._cancelled:
            record.status = SwarmStatus.CANCELLED
        elif any(r.get("status") == "failed" for r in agent_results) and not any(
            r.get("status") == "done" for r in agent_results
        ):
            record.status = SwarmStatus.FAILED
        else:
            record.status = SwarmStatus.DONE

        record.finished_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "SwarmOrchestrator: swarm=%s finished status=%s agents=%d",
            record.swarm_id,
            record.status,
            len(agent_list),
        )
        self._swarm_tasks.pop(record.swarm_id, None)
