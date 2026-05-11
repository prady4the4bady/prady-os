from __future__ import annotations

import httpx


class KryosFS:
    def __init__(self, app_name: str, api_base: str = "http://localhost:8001") -> None:
        self.app_name = app_name
        self.api_base = api_base

    async def read(self, relativePath: str) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.api_base}/sdk/fs/read", params={"app": self.app_name, "path": relativePath})
        resp.raise_for_status()
        return resp.json()["content"]

    async def write(self, relativePath: str, content: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.api_base}/sdk/fs/write", json={"app": self.app_name, "path": relativePath, "content": content})
        resp.raise_for_status()

    async def list(self, relativePath: str) -> list[str]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.api_base}/sdk/fs/list", params={"app": self.app_name, "path": relativePath})
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return [entry["name"] for entry in data.get("entries", [])]

    async def delete(self, relativePath: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{self.api_base}/sdk/fs/delete", params={"app": self.app_name, "path": relativePath})
        resp.raise_for_status()
