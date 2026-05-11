"""Conductor: the central orchestration agent.

Responsibilities:
1. Accept TaskRequests and enqueue them.
2. Decompose the goal into subtasks via the Phase-1 model gateway.
3. Build a DAG and execute subtasks in dependency order, concurrently where possible.
4. Gate dangerous actions behind the ApprovalStore (human-in-the-loop).
5. Publish each dispatch and result to Redis Streams for observability.
6. Collect agent results and produce a final summary.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.activity_log import ActivityLogger
from app.agents.browser_agent import BrowserAgent
from app.agents.file_agent import FileAgent
from app.agents.research_agent import ResearchAgent
from app.agents.screen_agent import ScreenAgent
from app.agents.shell_agent import ShellAgent
from app.approvals import ApprovalStore
from app.bus import CONDUCTOR_RESULTS_STREAM, MessageBus, agent_stream
from app.dag import DAG
from app.schemas import (
    ApprovalDecision,
    ApprovalRequest,
    Subtask,
    SubtaskStatus,
    TaskRecord,
    TaskRequest,
    TaskStatus,
)

logger = logging.getLogger(__name__)

_DECOMPOSE_SYSTEM_PROMPT = """\
You are Lumyn Planner, the orchestration planner for Kryos.
Given a user goal, decompose it into the minimal set of concrete subtasks.

Available agents and their supported actions:
        screen   : move_cursor(x,y), click(button, clicks), type_text(text), screenshot(path),
                             ocr_region(x,y,width,height,path), scroll(amount), key_press(key)
  browser  : navigate(url), search(query), extract_text(selector), screenshot(path)
             extract_hn_top_story(url, selector)
  shell    : run(command), which(program)
  file     : read(path), write(path, content), list(path), exists(path)
  research : summarize(content, question), analyze(content), extract_info(content, fields), question(context, question)

Planning requirements:
    - Prefer screen/browser/file subtasks whenever possible.
    - Use shell/research only when browser/file/screen cannot complete the goal.
    - Keep params concrete and execution-ready.

Respond ONLY with a valid JSON array (no markdown, no explanation). Each element must have:
    "agent_type" : one of [screen, browser, shell, file, research]
  "action"     : action name from the list above
  "params"     : dict of parameters
  "depends_on" : list of 0-based indices of subtasks this one depends on

Example for "Check if git is installed and save the version to /tmp/git.txt":
[
  {"agent_type": "shell",  "action": "run",   "params": {"command": "git --version"}, "depends_on": []},
  {"agent_type": "file",   "action": "write", "params": {"path": "/tmp/git.txt", "content": "result"}, "depends_on": [0]}
]"""


class Conductor:
    def __init__(
        self,
        bus: MessageBus,
        approvals: ApprovalStore,
        activity: ActivityLogger,
        gateway_url: str,
        playwright_runner_url: str,
        gateway_model: str,
        planner_model: str = "lumyn-agent",
        screen_backend: str = "auto",
        screen_ocr_enabled: bool = True,
        screen_screenshot_dir: str = "/tmp/kryos-screenshots",
        approval_timeout: float = 300.0,
    ) -> None:
        self._bus = bus
        self._approvals = approvals
        self._activity = activity
        self._gateway_url = gateway_url.rstrip("/")
        self._model = gateway_model
        self._planner_model = planner_model
        self._approval_timeout = approval_timeout
        self._tasks: Dict[str, TaskRecord] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._agents = {
            "screen": ScreenAgent(
                backend=screen_backend,
                ocr_enabled=screen_ocr_enabled,
                screenshot_dir=screen_screenshot_dir,
            ),
            "browser": BrowserAgent(playwright_runner_url),
            "shell": ShellAgent(),
            "file": FileAgent(),
            "research": ResearchAgent(gateway_url, gateway_model),
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def enqueue(self, req: TaskRequest) -> TaskRecord:
        """Accept a task, create its record, and fire off async execution."""
        record = TaskRecord(
            task_id=req.task_id,
            goal=req.goal,
            agent=req.agent,
            priority=req.priority,
            policy=req.policy,
        )
        self._tasks[req.task_id] = record
        await self._activity.log(
            "task_start",
            req.task_id,
            goal=req.goal,
            policy=req.policy,
            priority=str(req.priority),
        )
        background_task = asyncio.create_task(self._run_task(req, record))
        self._background_tasks.add(background_task)
        background_task.add_done_callback(self._background_tasks.discard)
        return record

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[TaskRecord]:
        return list(self._tasks.values())

    # ------------------------------------------------------------------
    # Core orchestration loop
    # ------------------------------------------------------------------

    async def _run_task(self, req: TaskRequest, record: TaskRecord) -> None:
        try:
            record.status = TaskStatus.decomposing
            subtasks = await self._decompose(req.goal, req.task_id)
            record.subtasks = subtasks

            dag = DAG()
            for st in subtasks:
                dag.add_node(st.subtask_id, st.depends_on)

            if dag.has_cycle():
                record.status = TaskStatus.failed
                record.error = "Cycle detected in subtask dependency graph"
                await self._activity.log("task_failed", req.task_id, error=record.error)
                return

            record.status = TaskStatus.running
            subtask_map = {st.subtask_id: st for st in subtasks}

            while not dag.is_complete():
                ready = dag.ready_to_run()
                if not ready:
                    # All pending nodes blocked — small yield to avoid busy-spin
                    await asyncio.sleep(0.05)
                    continue

                for sid in ready:
                    dag.mark_running(sid)

                coros = [
                    self._execute_subtask(subtask_map[sid], req.policy, dag, subtask_map)
                    for sid in ready
                    if sid in subtask_map
                ]
                await asyncio.gather(*coros, return_exceptions=True)

                if dag.has_failures():
                    failed_ids = [
                        sid for sid, st in dag.statuses().items() if st == "failed"
                    ]
                    record.status = TaskStatus.failed
                    record.error = f"Subtask(s) failed: {', '.join(failed_ids)}"
                    await self._activity.log(
                        "task_failed", req.task_id, failed_subtasks=failed_ids
                    )
                    return

            results = [st.result for st in subtasks if st.result]
            record.result = await self._summarize(req.goal, results)
            record.status = TaskStatus.completed
            record.completed_at = datetime.now(timezone.utc)
            await self._activity.log(
                "task_completed",
                req.task_id,
                result_preview=(record.result or "")[:200],
            )

        except Exception as exc:
            logger.exception("Unexpected error in task %s", req.task_id)
            record.status = TaskStatus.failed
            record.error = str(exc)
            await self._activity.log("task_failed", req.task_id, error=str(exc))

    async def _execute_subtask(
        self, subtask: Subtask, policy: str, dag: DAG, subtask_map: Dict[str, Subtask]
    ) -> None:
        agent = self._agents.get(subtask.agent_type)
        if not agent:
            subtask.status = SubtaskStatus.failed
            subtask.error = f"Unknown agent type: {subtask.agent_type!r}"
            dag.mark_failed(subtask.subtask_id)
            return

        is_approved = await self._request_approval_if_needed(subtask, agent, policy, dag)
        if not is_approved:
            return

        # ---- Dispatch -------------------------------------------------------
        self._hydrate_file_write_content(subtask, subtask_map)

        subtask.status = SubtaskStatus.running
        subtask.started_at = datetime.now(timezone.utc)
        await self._activity.log(
            "subtask_start",
            subtask.parent_task_id,
            subtask_id=subtask.subtask_id,
            agent_type=subtask.agent_type,
            action=subtask.action,
        )
        # Publish dispatch event to the agent's stream (observability)
        await self._bus.publish(
            agent_stream(subtask.agent_type),
            {
                "subtask_id": subtask.subtask_id,
                "task_id": subtask.parent_task_id,
                "agent_type": subtask.agent_type,
                "action": subtask.action,
                "params": subtask.params,
            },
        )

        try:
            result = await agent.execute(subtask.action, subtask.params)
            result_status = str(result.get("status", "ok")).lower() if isinstance(result, dict) else "ok"
            if result_status in {"error", "unsupported", "failed"}:
                raise RuntimeError(f"Agent returned {result_status}: {result}")
            subtask.result = result
            subtask.status = SubtaskStatus.completed
            subtask.completed_at = datetime.now(timezone.utc)
            dag.mark_complete(subtask.subtask_id)

            # Publish result event to conductor results stream
            await self._bus.publish(
                CONDUCTOR_RESULTS_STREAM,
                {
                    "subtask_id": subtask.subtask_id,
                    "task_id": subtask.parent_task_id,
                    "status": "completed",
                    "result": result,
                },
            )
            await self._activity.log(
                "subtask_completed",
                subtask.parent_task_id,
                subtask_id=subtask.subtask_id,
                agent_type=subtask.agent_type,
                action=subtask.action,
            )

        except Exception as exc:
            subtask.status = SubtaskStatus.failed
            subtask.error = str(exc)
            subtask.completed_at = datetime.now(timezone.utc)
            dag.mark_failed(subtask.subtask_id)
            await self._activity.log(
                "subtask_failed",
                subtask.parent_task_id,
                subtask_id=subtask.subtask_id,
                agent_type=subtask.agent_type,
                action=subtask.action,
                error=str(exc),
            )

    async def _request_approval_if_needed(
        self,
        subtask: Subtask,
        agent: Any,
        policy: str,
        dag: DAG,
    ) -> bool:
        if not agent.requires_approval(subtask.action, policy):
            return True

        approval_req = ApprovalRequest(
            task_id=subtask.parent_task_id,
            subtask_id=subtask.subtask_id,
            agent_type=subtask.agent_type,
            action=subtask.action,
            params=subtask.params,
            reason=(
                f"Policy '{policy}' requires human approval for "
                f"{subtask.agent_type}/{subtask.action}"
            ),
        )
        subtask.status = SubtaskStatus.waiting_approval
        approval = await self._approvals.request(approval_req)
        await self._activity.log(
            "approval_requested",
            subtask.parent_task_id,
            subtask_id=subtask.subtask_id,
            approval_id=approval.approval_id,
            agent_type=subtask.agent_type,
            action=subtask.action,
        )

        decision = await self._approvals.wait_for_decision(
            approval.approval_id, timeout=self._approval_timeout
        )
        if decision and decision.status == "approved":
            await self._activity.log(
                "approval_granted",
                subtask.parent_task_id,
                subtask_id=subtask.subtask_id,
                approval_id=approval.approval_id,
            )
            return True

        subtask.status = SubtaskStatus.cancelled
        subtask.error = "Action rejected or timed out waiting for human approval"
        dag.mark_failed(subtask.subtask_id)
        await self._activity.log(
            "approval_rejected",
            subtask.parent_task_id,
            subtask_id=subtask.subtask_id,
            approval_id=approval.approval_id,
        )
        return False

    def _hydrate_file_write_content(
        self, subtask: Subtask, subtask_map: Dict[str, Subtask]
    ) -> None:
        if subtask.agent_type != "file" or subtask.action != "write":
            return
        source_id = str(subtask.params.get("content_from_subtask", "")).strip()
        content_field = str(subtask.params.get("content_field", "text")).strip()
        if not source_id or subtask.params.get("content"):
            return
        dep_subtask = subtask_map.get(source_id)
        dep_result = dep_subtask.result if dep_subtask else None
        extracted = self._extract_field(dep_result, content_field)
        if extracted:
            subtask.params["content"] = extracted

    @staticmethod
    def _extract_field(value: Any, dotted_field: str) -> str:
        current = value
        for part in dotted_field.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
            if current is None:
                return ""
        return str(current)

    # ------------------------------------------------------------------
    # Goal decomposition
    # ------------------------------------------------------------------

    async def _decompose(self, goal: str, task_id: str) -> List[Subtask]:
        """Call the model gateway to decompose *goal* into a list of Subtask objects."""
        raw_items: Optional[List[Dict[str, Any]]] = None
        planner_used = ""

        planner_models = [self._planner_model]
        if self._model and self._model != self._planner_model:
            planner_models.append(self._model)

        for model in planner_models:
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        f"{self._gateway_url}/v1/chat/completions",
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": _DECOMPOSE_SYSTEM_PROMPT},
                                {"role": "user", "content": goal},
                            ],
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"]
                    parsed_items = self._parse_json_array(text)
                    if parsed_items:
                        raw_items = [item for item in parsed_items if isinstance(item, dict)]
                        planner_used = model
                        if raw_items:
                            break
            except Exception as exc:
                logger.warning(
                    "Decompose gateway call failed for task %s with model %s: %s",
                    task_id,
                    model,
                    exc,
                )
                await self._activity.log(
                    "decompose_failed",
                    task_id,
                    planner_model=model,
                    error=str(exc),
                )

        if not raw_items:
            # Fallback: single research subtask that analyses the goal directly
            return [
                Subtask(
                    parent_task_id=task_id,
                    agent_type="research",
                    action="analyze",
                    params={"content": goal, "question": "What needs to be done?"},
                )
            ]

        # Pre-assign UUIDs so index-based depends_on can be translated to real IDs
        ids = [str(uuid.uuid4()) for _ in raw_items]
        subtasks: List[Subtask] = []
        for i, item in enumerate(raw_items):
            dep_indices = item.get("depends_on", [])
            dep_ids = [
                ids[j]
                for j in dep_indices
                if isinstance(j, int) and 0 <= j < len(ids)
            ]
            st = Subtask(
                subtask_id=ids[i],
                parent_task_id=task_id,
                agent_type=item.get("agent_type", "research"),
                action=item.get("action", "analyze"),
                params=item.get("params", {}),
                depends_on=dep_ids,
            )
            subtasks.append(st)

        await self._activity.log(
            "task_decomposed",
            task_id,
            subtask_count=len(subtasks),
            planner=planner_used or "fallback",
        )
        return subtasks

    async def _summarize(self, goal: str, results: List[Any]) -> str:
        """Ask the gateway for a human-readable summary of all agent results."""
        results_text = json.dumps(results, default=str, indent=2)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._gateway_url}/v1/chat/completions",
                    json={
                        "model": self._model,
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    f"Original goal: {goal}\n\n"
                                    f"Agent results:\n{results_text}\n\n"
                                    "Provide a concise summary of what was accomplished."
                                ),
                            }
                        ],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("Summarize call failed: %s", exc)
            return f"Task completed. {len(results)} subtask(s) executed successfully."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_array(text: str) -> Optional[List[Dict[str, Any]]]:
        """Extract and parse the first JSON array found in *text*."""
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        return None
