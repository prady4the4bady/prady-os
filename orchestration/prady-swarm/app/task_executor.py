"""AutonomousTaskExecutor — perception-action loop for desktop automation."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH = Path("platform/audit/task_execution.jsonl")
_GATEWAY_DEFAULT = "http://localhost:8000"


def _write_audit(record: dict) -> None:  # type: ignore[type-arg]
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract first JSON object from arbitrary text."""
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


@dataclass
class StepEvent:
    task_id: str
    step: int
    action: str
    params: Dict[str, Any]
    reasoning: str
    screenshot_b64: str = ""
    screen_description: str = ""
    success: bool = True
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskResult:
    task_id: str
    goal: str
    user_id: str
    steps_taken: int
    success: bool
    final_screenshot_b64: str
    summary: str
    duration_seconds: float
    steps: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _dispatch_action(controller: Any, action: str, params: Dict[str, Any]) -> None:
    """Dispatch a single action to InputController."""
    if action == "click":
        controller.click(int(params.get("x", 0)), int(params.get("y", 0)), params.get("button", "left"))
    elif action == "double_click":
        controller.double_click(int(params.get("x", 0)), int(params.get("y", 0)))
    elif action == "right_click":
        controller.right_click(int(params.get("x", 0)), int(params.get("y", 0)))
    elif action == "type_text":
        controller.type_text(str(params.get("text", "")), float(params.get("interval", 0.05)))
    elif action == "hotkey":
        keys = params.get("keys", [])
        if keys:
            controller.hotkey(*keys)
    elif action == "scroll":
        controller.scroll(int(params.get("x", 0)), int(params.get("y", 0)), int(params.get("clicks", 1)))
    elif action == "move_mouse":
        controller.move_mouse(int(params.get("x", 0)), int(params.get("y", 0)), float(params.get("duration", 0.3)))


def _terminal_step(action: str, goal_complete: bool) -> bool:
    return action == "done" or goal_complete


async def _store_step_memory(
    memory_store: Any,
    *,
    user_id: str,
    task_id: str,
    step_num: int,
    action: str,
    params: Dict[str, Any],
    reasoning: str,
) -> None:
    if memory_store is None:
        return
    try:
        await memory_store.store(
            agent_id=f"task-executor-{user_id}",
            content=f"Step {step_num}: {action}({json.dumps(params)}) — {reasoning}",
            tags=["task", task_id, user_id],
        )
    except Exception:
        pass


class AutonomousTaskExecutor:
    """Execute a desktop goal via a vision → LLM → action loop."""

    def __init__(
        self,
        gateway_url: str = _GATEWAY_DEFAULT,
        vision_agent: Any = None,
        input_controller: Any = None,
        memory_store: Any = None,
    ) -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._vision_agent = vision_agent
        self._input_controller = input_controller
        self._memory_store = memory_store
        self._active: Dict[str, bool] = {}

    def _vision(self) -> Any:
        if self._vision_agent is not None:
            return self._vision_agent
        # Lazy import to avoid hard dependency at import time
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "platform" / "vision-agent"))
        from vision_agent import VisionAgent  # type: ignore[import-not-found]
        return VisionAgent(gateway_url=self._gateway_url)

    def _controller(self) -> Any:
        if self._input_controller is not None:
            return self._input_controller
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "platform" / "input-controller"))
        from input_controller import InputController  # type: ignore[import-not-found]
        return InputController()

    async def _ask_llm(
        self, goal: str, screen_desc: str, history: List[str]
    ) -> Dict[str, Any]:
        history_txt = "\n".join(f"  Step {i+1}: {h}" for i, h in enumerate(history[-5:]))
        prompt = (
            f"You are a desktop automation agent. Goal: {goal}\n\n"
            f"Screen: {screen_desc}\n\n"
            f"History:\n{history_txt or '  (none yet)'}\n\n"
            "Return ONLY JSON: "
            '{"action":"click|double_click|right_click|type_text|hotkey|scroll|move_mouse|done|error",'
            '"params":{...},"reasoning":"...","goal_complete":false}'
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._gateway_url}/v1/chat/completions",
                json={
                    "model": "lumyn-agent",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 300,
                },
            )
            if resp.status_code != 200:
                return {"action": "error", "params": {}, "reasoning": f"LLM {resp.status_code}", "goal_complete": False}
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _extract_json(content)
        if parsed:
            return parsed
        return {"action": "error", "params": {}, "reasoning": f"Parse failed: {content[:80]}", "goal_complete": False}

    async def execute_goal(
        self,
        goal: str,
        user_id: str = "default",
        max_steps: int = 50,
        task_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Yield step events then a final task-result event."""
        if task_id is None:
            task_id = str(uuid.uuid4())

        self._active[task_id] = True
        start = time.time()
        steps_log: List[Dict[str, Any]] = []
        history: List[str] = []
        vision = self._vision()
        controller = self._controller()
        final_b64 = ""
        success = False
        summary = ""
        error_msg: Optional[str] = None

        for step_num in range(1, max_steps + 1):
            if not self._active.get(task_id, False):
                summary = "Task aborted"
                break
            try:
                image = vision.capture_screen()
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                shot_b64 = base64.b64encode(buf.getvalue()).decode()
                final_b64 = shot_b64

                screen_desc = await vision.describe_screen(image)
                act = await self._ask_llm(goal, screen_desc, history)
                action = act.get("action", "error")
                params = act.get("params", {})
                reasoning = act.get("reasoning", "")
                goal_complete = bool(act.get("goal_complete", False))

                evt = StepEvent(
                    task_id=task_id,
                    step=step_num,
                    action=action,
                    params=params,
                    reasoning=reasoning,
                    screenshot_b64=shot_b64,
                    screen_description=screen_desc,
                )

                if _terminal_step(action, goal_complete):
                    evt.success = True
                    success = True
                    summary = reasoning or "Goal achieved"
                    steps_log.append(evt.to_dict())
                    yield {"type": "step", **evt.to_dict()}
                    break

                if action == "error":
                    evt.success = False
                    evt.error = reasoning
                    steps_log.append(evt.to_dict())
                    yield {"type": "step", **evt.to_dict()}
                    break

                _dispatch_action(controller, action, params)
                history.append(f"{action}({json.dumps(params)}) — {reasoning}")
                steps_log.append(evt.to_dict())
                yield {"type": "step", **evt.to_dict()}

                # Brief pause for UI to settle
                await asyncio.sleep(0.4)

                await _store_step_memory(
                    self._memory_store,
                    user_id=user_id,
                    task_id=task_id,
                    step_num=step_num,
                    action=action,
                    params=params,
                    reasoning=reasoning,
                )

            except Exception as exc:
                logger.exception("Executor step %d failed: %s", step_num, exc)
                error_msg = str(exc)
                steps_log.append({"step": step_num, "error": str(exc), "task_id": task_id})
                break
        else:
            summary = f"Reached max steps ({max_steps})"

        duration = round(time.time() - start, 2)
        self._active.pop(task_id, None)

        result = TaskResult(
            task_id=task_id,
            goal=goal,
            user_id=user_id,
            steps_taken=len(steps_log),
            success=success,
            final_screenshot_b64=final_b64,
            summary=summary,
            duration_seconds=duration,
            steps=steps_log,
            error=error_msg,
        )
        _write_audit(
            {
                "event": "task_completed",
                "task_id": task_id,
                "goal": goal,
                "user_id": user_id,
                "steps_taken": result.steps_taken,
                "success": success,
                "duration_seconds": duration,
                "ts": time.time(),
            }
        )
        yield {"type": "result", **result.to_dict()}

    def abort(self, task_id: str) -> bool:
        if task_id in self._active:
            self._active[task_id] = False
            return True
        return False
