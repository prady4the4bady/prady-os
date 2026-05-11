from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

try:
    import aiosqlite
except Exception:  # pragma: no cover - optional import fallback
    aiosqlite = None


VYREX_PROXY_URL = os.environ.get("VYREX_PROXY_URL", "http://vyrex-proxy:8105")
COMPUTER_USE_URL = os.environ.get("COMPUTER_USE_URL", "http://computer-use:8106")
COMPUTER_USE_MODEL = os.environ.get("COMPUTER_USE_MODEL", "llama3")
TASK_DB_PATH = Path(os.environ.get("TASK_JOURNAL_PATH", "data/task_journal.db"))
MEMORY_SERVICE_URL = os.getenv("MEMORY_SERVICE_URL", "http://memory-service:8108")
NOTIFICATION_BUS_URL = os.getenv("NOTIFICATION_BUS_URL", "http://notification-bus:8111")
SECURITY_POLICY_URL = os.getenv("SECURITY_POLICY_URL", "http://security-policy:8117")

_stop_requested = False


@dataclass
class TaskResult:
    status: str
    steps: int
    message: str
    actions: list[dict[str, Any]]


def request_stop() -> None:
    global _stop_requested
    _stop_requested = True


def clear_stop() -> None:
    global _stop_requested
    _stop_requested = False


async def _fire_notify(
    task_description: str,
    status: str,
    message: str,
    run_id: str | None = None,
) -> None:
    """Fire-and-forget notification to notification bus."""
    try:
        run_tag = f" [run:{run_id[:8]}]" if run_id else ""
        if status == "done":
            payload = {
                "type": "task_complete",
                "title": f"Task completed{run_tag}",
                "body": task_description[:80],
                "source": "computer-use",
                "severity": "success",
            }
        else:
            payload = {
                "type": "task_failed",
                "title": f"Task failed{run_tag}",
                "body": f"{task_description[:60]}: {message[:20]}",
                "source": "computer-use",
                "severity": "error",
            }
        async with httpx.AsyncClient(timeout=5) as nc:
            await nc.post(f"{NOTIFICATION_BUS_URL}/notify", json=payload)
    except Exception:
        pass


class TaskExecutor:
    @staticmethod
    async def _policy_check_computer_use() -> tuple[bool, str]:
        """Check security policy for computer-control. Fail-closed on error."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{SECURITY_POLICY_URL}/policies/check",
                    json={"subject_type": "service", "subject_id": "computer-use", "permission": "computer-control"},
                )
                data = resp.json()
                return bool(data.get("allowed", False)), str(data.get("reason", ""))
        except Exception as exc:
            return False, f"security-policy unavailable: {exc}"

    def __init__(self, proxy_url: str | None = None, computer_url: str | None = None, db_path: Path | None = None) -> None:
        self.proxy_url = proxy_url or VYREX_PROXY_URL
        self.computer_url = computer_url or COMPUTER_USE_URL
        self.db_path = db_path or TASK_DB_PATH

    async def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if aiosqlite is not None:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task TEXT NOT NULL,
                        step INTEGER NOT NULL,
                        action_json TEXT NOT NULL,
                        screenshot_before_b64 TEXT NOT NULL,
                        screenshot_after_b64 TEXT NOT NULL,
                        timestamp REAL NOT NULL
                    )
                    """
                )
                await db.commit()
            return

        def _sync_create() -> None:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task TEXT NOT NULL,
                        step INTEGER NOT NULL,
                        action_json TEXT NOT NULL,
                        screenshot_before_b64 TEXT NOT NULL,
                        screenshot_after_b64 TEXT NOT NULL,
                        timestamp REAL NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_sync_create)

    async def _log_step(
        self,
        task: str,
        step: int,
        action_json: dict[str, Any],
        before_b64: str,
        after_b64: str,
    ) -> None:
        if aiosqlite is not None:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO task_runs (task, step, action_json, screenshot_before_b64, screenshot_after_b64, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (task, step, json.dumps(action_json), before_b64, after_b64, time.time()),
                )
                await db.commit()
            return

        def _sync_insert() -> None:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO task_runs (task, step, action_json, screenshot_before_b64, screenshot_after_b64, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (task, step, json.dumps(action_json), before_b64, after_b64, time.time()),
                )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_sync_insert)

    async def _screenshot(self, client: httpx.AsyncClient) -> str:
        response = await client.get(f"{self.computer_url}/screenshot")
        response.raise_for_status()
        payload = response.json()
        return payload.get("image_b64", "")

    async def _plan(self, client: httpx.AsyncClient, task_description: str, screenshot_b64: str, history: list[dict[str, Any]]) -> dict[str, Any]:
        system_prompt = "You are an AI controlling a desktop. Decide the next action."
        user_prompt = {
            "task": task_description,
            "last_actions": history,
            "screenshot_b64": screenshot_b64,
            "respond_json": {
                "action": "click|type|hotkey|scroll|done|fail",
                "params": {},
                "reasoning": "string",
            },
        }

        response = await client.post(
            f"{self.proxy_url}/v1/chat/completions",
            json={
                "model": COMPUTER_USE_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_prompt)},
                ],
                "temperature": 0.1,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()

        try:
            content = payload["choices"][0]["message"]["content"]
            action_json = json.loads(content)
            return action_json
        except Exception as exc:
            return {"action": "fail", "params": {"error": str(exc)}, "reasoning": "planner parse failure"}

    async def _act(self, client: httpx.AsyncClient, action: str, params: dict[str, Any]) -> None:
        action = action.lower().strip()
        if action == "click":
            await client.post(f"{self.computer_url}/mouse/click", json=params)
        elif action == "type":
            await client.post(f"{self.computer_url}/keyboard/type", json=params)
        elif action == "hotkey":
            await client.post(f"{self.computer_url}/keyboard/hotkey", json=params)
        elif action == "scroll":
            key = params.get("key", "pagedown")
            await client.post(f"{self.computer_url}/keyboard/key", json={"key": key})

    async def _ingest_task_memory(self, task_description: str, result: str, duration_s: float, steps_taken: int) -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{MEMORY_SERVICE_URL}/memory/ingest-task",
                    json={
                        "task_description": task_description,
                        "result": result,
                        "duration_s": duration_s,
                        "steps_taken": steps_taken,
                    },
                )
        except Exception:
            pass

    async def run_task(self, task_description: str, max_steps: int = 20, run_id: str | None = None) -> TaskResult:
        clear_stop()
        allowed, reason = await self._policy_check_computer_use()
        if not allowed:
            return TaskResult(
                status="failed",
                steps=0,
                message=f"policy denied computer-control: {reason}",
                actions=[],
            )
        await self._ensure_schema()
        started_at = time.time()

        history: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=90) as client:
            for step in range(1, max_steps + 1):
                if _stop_requested:
                    await self._ingest_task_memory(task_description, "failed", time.time() - started_at, max(step - 1, 0))
                    result = TaskResult(
                        status="failed",
                        steps=step - 1,
                        message="Task stopped by user",
                        actions=history,
                    )
                    notify_task = asyncio.create_task(_fire_notify(task_description, result.status, result.message, run_id))
                    _ = notify_task
                    return result

                before_b64 = await self._screenshot(client)
                plan = await self._plan(client, task_description, before_b64, history[-5:])
                action = str(plan.get("action", "fail")).lower().strip()
                params = plan.get("params", {}) or {}

                if action == "done":
                    await self._log_step(task_description, step, plan, before_b64, before_b64)
                    history.append(plan)
                    await self._ingest_task_memory(task_description, "done", time.time() - started_at, step)
                    result = TaskResult(status="done", steps=step, message="Task completed", actions=history)
                    notify_task = asyncio.create_task(_fire_notify(task_description, result.status, result.message, run_id))
                    _ = notify_task
                    return result

                if action == "fail":
                    await self._log_step(task_description, step, plan, before_b64, before_b64)
                    history.append(plan)
                    await self._ingest_task_memory(task_description, "failed", time.time() - started_at, step)
                    result = TaskResult(status="failed", steps=step, message="Planner reported failure", actions=history)
                    notify_task = asyncio.create_task(_fire_notify(task_description, result.status, result.message, run_id))
                    _ = notify_task
                    return result

                await self._act(client, action, params)
                after_b64 = await self._screenshot(client)

                history.append(plan)
                await self._log_step(task_description, step, plan, before_b64, after_b64)

        await self._ingest_task_memory(task_description, "max_steps_reached", time.time() - started_at, max_steps)
        result = TaskResult(status="failed", steps=max_steps, message="Reached max steps", actions=history)
        notify_task = asyncio.create_task(_fire_notify(task_description, result.status, result.message, run_id))
        _ = notify_task
        return result
