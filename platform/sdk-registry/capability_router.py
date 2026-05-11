from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from registry_db import RegistryDB


@dataclass
class DelegationResult:
    success: bool
    app_id: str = ""
    result: dict | None = None
    error: str = ""
    latency_ms: int = 0


class CapabilityRouter:
    def __init__(self, registry_db: RegistryDB, http_timeout_ms: int = 5000):
        self._db = registry_db
        self._timeout = http_timeout_ms / 1000

    async def delegate(self, capability: str, payload: dict, timeout_ms: int) -> DelegationResult:
        apps = await self._db.get_apps_by_capability(capability)
        running = [a for a in apps if a["status"] == "running"]
        if not running:
            return DelegationResult(success=False, error=f"No running app provides capability: {capability}")
        app = running[0]
        target_url = f"http://kryos-sdk-{app['app_id']}:8080/kryos/task"
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=min(timeout_ms / 1000, self._timeout)) as client:
                resp = await client.post(target_url, json={"capability": capability, "payload": payload, "timeout_ms": timeout_ms})
            latency_ms = int((time.monotonic() - start) * 1000)
            if resp.status_code == 200:
                return DelegationResult(success=True, app_id=app["app_id"], result=resp.json(), latency_ms=latency_ms)
            return DelegationResult(success=False, error=f"App returned {resp.status_code}", latency_ms=latency_ms)
        except httpx.TimeoutException:
            return DelegationResult(success=False, error=f"App timed out after {timeout_ms}ms")
        except Exception as exc:
            return DelegationResult(success=False, error=str(exc))

    async def get_capability_map(self) -> list[dict]:
        apps = await self._db.get_all_apps()
        result: list[dict] = []
        for app in apps:
            if app["status"] == "running":
                for cap in app.get("capabilities", []):
                    result.append({"capability": cap, "app_id": app["app_id"], "app_name": app["display_name"], "avg_latency_ms": 0.0})
        return result
