"""Phase 9B-2: Self-correction engine for the autonomous agent loop."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MODEL_GATEWAY_URL = "http://model-gateway:8000"
AGENTNET_URL = "http://kryos-swarm:8000"
MAX_CORRECTION_ATTEMPTS = 2


class SelfCorrectionEngine:
    """Re-runs failed tasks through an LLM correction pass."""

    async def correct(
        self,
        task_result: dict[str, Any],
        *,
        max_attempts: int = MAX_CORRECTION_ATTEMPTS,
    ) -> dict[str, Any]:
        original_task = task_result.get("task", {})
        last_error = task_result.get("error", "unknown error")
        last_output = task_result.get("output", "")

        for attempt in range(1, max_attempts + 1):
            logger.info("Self-correction attempt %d/%d for task %s", attempt, max_attempts, original_task.get("id"))
            prompt = self._build_prompt(original_task, last_error, last_output)
            try:
                corrected_output = await self._call_model(prompt)
            except Exception as exc:
                logger.warning("Model call failed on attempt %d: %s", attempt, exc)
                continue

            corrected_result = {**task_result, "output": corrected_output, "corrected": True, "attempts": attempt}

            # Re-submit corrected task
            try:
                resubmit_resp = await self._resubmit(original_task, corrected_output)
                if resubmit_resp.get("status") == "done":
                    await self._emit_event("task.corrected", corrected_result)
                    return corrected_result
            except Exception as exc:
                last_error = str(exc)
                last_output = corrected_output

        failed_result = {**task_result, "corrected": False, "permanently_failed": True}
        await self._emit_event("task.permanently_failed", failed_result)
        return failed_result

    def _build_prompt(self, task: dict[str, Any], error: str, output: str) -> str:
        return (
            f"The following task failed.\n\nTask: {task}\n\nError: {error}\n\nPrevious output: {output}\n\n"
            "Please produce a corrected response that avoids the error above. "
            "Reply only with the corrected task output."
        )

    async def _call_model(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{MODEL_GATEWAY_URL}/api/v1/chat",
                json={"messages": [{"role": "user", "content": prompt}], "model": "lumyn-agent"},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return str(data.get("choices", [{}])[0].get("message", {}).get("content", ""))

    async def _resubmit(self, task: dict[str, Any], corrected_output: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{AGENTNET_URL}/task/execute",
                json={**task, "corrected_input": corrected_output},
            )
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

    async def _emit_event(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{AGENTNET_URL}/agentnet/publish",
                    json={"topic": topic, "payload": payload},
                )
        except Exception as exc:
            logger.debug("AgentNet emit failed: %s", exc)
