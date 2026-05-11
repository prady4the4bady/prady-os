from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class TaskResult:
    task_id: str
    status: str
    result: str | None = None
    error: str | None = None


@dataclass
class Skill:
    skill_id: str
    description: str
    avg_score: float


class PraxAgent:
    def __init__(self, api_base: str = "http://localhost:8001") -> None:
        self.api_base = api_base

    async def assignTask(self, description: str, options: dict[str, Any] | None = None) -> TaskResult:
        payload = {"description": description}
        if options:
            payload.update(options)
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.api_base}/tasks", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return TaskResult(**data)

    async def getTaskStatus(self, taskId: str) -> TaskResult:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.api_base}/tasks/{taskId}")
        resp.raise_for_status()
        return TaskResult(**resp.json())

    async def listSkills(self) -> list[Skill]:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8018/learn/skills")
        resp.raise_for_status()
        data = resp.json()
        items = data.get("skills") if isinstance(data, dict) else data
        return [Skill(**item) for item in (items or [])]
