from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class ModelInfo:
    id: str
    name: str
    active: bool


class KryosModel:
    def __init__(self, api_base: str = "http://localhost:8000") -> None:
        self.api_base = api_base

    async def query(self, prompt: str, options: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {"prompt": prompt}
        if options:
            payload.update(options)
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.api_base}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            if data.get("content"):
                return str(data["content"])
            choices = data.get("choices") or []
            if choices:
                return str(choices[0].get("message", {}).get("content", ""))
        return ""

    async def listModels(self) -> list[ModelInfo]:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8003/models")
        resp.raise_for_status()
        data = resp.json()
        items = data.get("models") if isinstance(data, dict) else data
        return [ModelInfo(**item) for item in (items or [])]
