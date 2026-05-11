from __future__ import annotations

import httpx


class KryosNotify:
    def __init__(self, api_base: str = "http://localhost:8007") -> None:
        self.api_base = api_base

    async def send(self, title: str, body: str, severity: str = "info") -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.api_base}/notify",
                json={"title": title, "body": body, "severity": severity, "source": "sdk-app"},
            )
        resp.raise_for_status()
