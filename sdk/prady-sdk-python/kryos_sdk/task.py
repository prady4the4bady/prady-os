from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class ScheduledTask:
    schedule_id: str
    description: str
    run_at: str
    status: str


class KryosTask:
    def __init__(self, api_base: str = "http://localhost:8005") -> None:
        self.api_base = api_base

    async def schedule(self, description: str, runAt, options: dict | None = None) -> str:
        payload = {"description": description, "run_at": runAt.isoformat()}
        if options:
            payload.update(options)
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.api_base}/tasks/schedule", json=payload)
        resp.raise_for_status()
        return resp.json()["schedule_id"]

    async def cancel(self, scheduleId: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{self.api_base}/tasks/{scheduleId}")
        resp.raise_for_status()

    async def list(self) -> list[ScheduledTask]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.api_base}/tasks")
        resp.raise_for_status()
        data = resp.json()
        items = data.get("tasks") if isinstance(data, dict) else data
        return [ScheduledTask(**item) for item in (items or [])]
