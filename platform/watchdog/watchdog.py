"""Phase 9B-1: Watchdog daemon — monitors services, auto-restarts on failure."""
import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress
from typing import Any

import docker
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_poll_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="PradyOS Watchdog", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SERVICES: list[dict[str, Any]] = [
    {"name": "model-gateway",    "url": "http://model-gateway:8000/health",    "container": "prady-os-model-gateway-1"},
    {"name": "kryos-swarm",      "url": "http://kryos-swarm:8000/health",      "container": "prady-os-kryos-swarm-1"},
    {"name": "vision-agent",     "url": "http://vision-agent:8010/health",     "container": "prady-os-vision-agent-1"},
    {"name": "input-controller", "url": "http://input-controller:8011/health", "container": "prady-os-input-controller-1"},
    {"name": "process-manager",  "url": "http://process-manager:8012/health",  "container": "prady-os-process-manager-1"},
    {"name": "memory-store",     "url": "http://memory-store:8094/health",     "container": "prady-os-memory-store-1"},
]

_status: dict[str, dict[str, Any]] = {
    s["name"]: {"name": s["name"], "status": "unknown", "failures": 0, "uptime": 0, "started": time.time()}
    for s in SERVICES
}


class RestartResponse(BaseModel):
    restarted: bool
    service: str


async def _check_service(svc: dict[str, Any]) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(svc["url"])
            return resp.status_code < 400
    except Exception:
        return False


def _restart_container(container_name: str) -> bool:
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.restart(timeout=10)
        return True
    except Exception as exc:
        logger.error("Failed to restart %s: %s", container_name, exc)
        return False


async def _poll_loop() -> None:
    while True:
        for svc in SERVICES:
            name = svc["name"]
            ok = await _check_service(svc)
            entry = _status[name]
            if ok:
                entry["failures"] = 0
                entry["status"] = "healthy"
                entry["uptime"] = int(time.time() - entry["started"])
            else:
                entry["failures"] = entry.get("failures", 0) + 1
                entry["status"] = "degraded"
                logger.warning("Service %s health check failed (%d)", name, entry["failures"])
                if entry["failures"] >= 3:
                    logger.error("Restarting %s after 3 consecutive failures", name)
                    _restart_container(svc["container"])
                    entry["failures"] = 0
                    entry["started"] = time.time()
                    entry["status"] = "restarting"
        await asyncio.sleep(15)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/watchdog/status")
async def get_status() -> dict[str, Any]:
    return {"services": list(_status.values())}


@app.post("/api/watchdog/restart/{service_name}")
async def restart_service(service_name: str) -> RestartResponse:
    svc = next((s for s in SERVICES if s["name"] == service_name), None)
    if svc is None:
        return RestartResponse(restarted=False, service=service_name)
    ok = _restart_container(svc["container"])
    if ok:
        _status[service_name]["failures"] = 0
        _status[service_name]["started"] = time.time()
        _status[service_name]["status"] = "restarting"
    return RestartResponse(restarted=ok, service=service_name)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("watchdog:app", host="0.0.0.0", port=8010, reload=False)
