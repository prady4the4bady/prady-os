"""
agent_api.py – FastAPI service wrapping AgentManager.

Endpoints:
  POST   /agents/spawn           spawn a new agent
  GET    /agents/                list all agents
  DELETE /agents/{agent_id}      kill an agent
  POST   /agents/{agent_id}/prompt  send a prompt → SSE stream
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Path bootstrap – allow running from the platform/agent-runtime directory
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent.parent  # repo root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_COMPUTER_USE_DIR = _ROOT / "platform" / "computer-use"
if str(_COMPUTER_USE_DIR) not in sys.path:
    sys.path.insert(0, str(_COMPUTER_USE_DIR))

from vyrex.runtime.agent_manager import AgentHandle, AgentManager  # noqa: E402
from vyrex.runtime.model_registry import ModelRegistry             # noqa: E402
from task_loop import TaskExecutor, clear_stop, request_stop         # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
SSE_MEDIA_TYPE = "text/event-stream"

app = FastAPI(title="Prax Agent Runtime", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_manager = AgentManager()
_registry = ModelRegistry()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class SpawnRequest(BaseModel):
    model_id: str
    policy_id: str = "task-executor"


class AgentResponse(BaseModel):
    agent_id: str
    model_id: str
    policy_id: str
    pid: Optional[int]
    status: str
    started_at: float
    stopped_at: Optional[float] = None
    exit_code: Optional[int] = None


class PromptRequest(BaseModel):
    text: str


class AutomateRequest(BaseModel):
    action: str
    params: dict


class ActiveModelRequest(BaseModel):
    model_id: str


class ComputerTaskRunRequest(BaseModel):
    task_description: str
    max_steps: int = 20


_active_model_id: str = "lumyn-default"
_task_executor = TaskExecutor()
MODEL_HUB_URL = os.getenv("MODEL_HUB_URL", "http://model-hub:8113")
MEMORY_SERVICE_URL = os.getenv("MEMORY_SERVICE_URL", "http://memory-service:8108")
PERSONA_SERVICE_URL = os.getenv("PERSONA_SERVICE_URL", "http://persona-service:8114")
SCHEDULER_SERVICE_URL = os.getenv("SCHEDULER_SERVICE_URL", "http://task-scheduler:8110")
NOTIFICATION_BUS_URL = os.getenv("NOTIFICATION_BUS_URL", "http://notification-bus:8111")
AUDIT_LOG_URL = os.getenv("AUDIT_LOG_URL", "http://audit-log:8112")
WATCHDOG_URL = os.getenv("WATCHDOG_URL", "http://watchdog:8115")
PACKAGE_MANAGER_URL = os.getenv("PACKAGE_MANAGER_URL", "http://package-manager:8116")
SECURITY_POLICY_URL = os.getenv("SECURITY_POLICY_URL", "http://security-policy:8117")
OTA_SERVICE_URL = os.getenv("OTA_SERVICE_URL", "http://ota-service:8012")
SELF_LEARNING_URL = os.getenv("SELF_LEARNING_URL", "http://self-learning:8018")
SDK_REGISTRY_URL = os.getenv("SDK_REGISTRY_URL", "http://sdk-registry:8020")


async def _notify_self_learning(
    task_id: str,
    description: str,
    action_sequence: list,
    outcome: str,
    duration_ms: int,
    error_message: str | None,
    model_used: str,
) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{SELF_LEARNING_URL}/learn/record",
                json={
                    "task_id": task_id,
                    "task_description": description,
                    "action_sequence": action_sequence,
                    "outcome": outcome,
                    "duration_ms": duration_ms,
                    "error_message": error_message,
                    "model_used": model_used,
                    "user_rating": None,
                },
            )
    except Exception:
        pass


async def _try_sdk_delegation(capability: str, payload: dict, timeout_ms: int = 5000) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            resp = await client.post(
                f"{SDK_REGISTRY_URL}/sdk/delegate",
                json={"capability": capability, "payload": payload, "timeout_ms": timeout_ms},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success", True):
                    return data.get("result")
    except Exception:
        pass
    return None


def _handle_to_response(h: AgentHandle) -> AgentResponse:
    return AgentResponse(
        agent_id=h.agent_id,
        model_id=h.model_id,
        policy_id=h.policy_id,
        pid=h.pid,
        status=h.status,
        started_at=h.started_at,
        stopped_at=h.stopped_at,
        exit_code=h.exit_code,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/agents/spawn", response_model=AgentResponse, status_code=201)
def spawn_agent(req: SpawnRequest) -> AgentResponse:
    """Spawn a new sandboxed agent process."""
    try:
        handle = _manager.spawn_agent(req.model_id, req.policy_id)
        return _handle_to_response(handle)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/agents/", response_model=list[AgentResponse])
def list_agents() -> list[AgentResponse]:
    """List all agent handles."""
    return [_handle_to_response(h) for h in _manager.list_agents()]


@app.delete("/agents/{agent_id}", response_model=AgentResponse)
def kill_agent(agent_id: str) -> AgentResponse:
    """Gracefully terminate an agent."""
    try:
        handle = _manager.kill_agent(agent_id)
        return _handle_to_response(handle)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/agents/{agent_id}/prompt")
async def prompt_agent(agent_id: str, req: PromptRequest) -> StreamingResponse:
    """
    Send a text prompt to an agent and stream the response as SSE.

    The actual inference is forwarded to the model gateway; this endpoint
    proxies the SSE stream so the frontend has a single origin to talk to.
    """
    agents = _manager.list_agents()
    handle = next((h for h in agents if h.agent_id == agent_id), None)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    if handle.status != "running":
        raise HTTPException(status_code=409, detail=f"Agent {agent_id} is not running (status={handle.status})")

    async def _generate() -> AsyncIterator[str]:
        """Yield SSE-framed tokens simulating or proxying inference."""
        import json

        model_gateway_url = os.environ.get("MODEL_GATEWAY_URL", "http://localhost:8000")
        prompt_text = req.text

        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{model_gateway_url}/inference/stream",
                    json={
                        "model_id": handle.model_id,
                        "prompt": prompt_text,
                        "agent_id": agent_id,
                    },
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data:"):
                            yield f"{line}\n\n"
                        elif line:
                            yield f"data: {line}\n\n"
        except Exception as exc:
            # Fallback: echo the prompt back as a stub response
            logger.warning("Model gateway unavailable (%s) – using stub response", exc)
            stub = f"[Agent {agent_id[:8]}] Echo: {prompt_text}"
            for word in stub.split():
                payload = json.dumps({"token": word + " ", "agent_id": agent_id})
                yield f"data: {payload}\n\n"
                await asyncio.sleep(0.05)
            done_payload = json.dumps({"done": True, "agent_id": agent_id})
            yield f"data: {done_payload}\n\n"

    return StreamingResponse(
        _generate(),
        media_type=SSE_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/agents/{agent_id}/automate")
async def automate_agent(agent_id: str, req: AutomateRequest) -> JSONResponse:
    agents = _manager.list_agents()
    handle = next((h for h in agents if h.agent_id == agent_id), None)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    if handle.status != "running":
        raise HTTPException(status_code=409, detail=f"Agent {agent_id} is not running (status={handle.status})")

    automation_base = os.environ.get("AUTOMATION_SERVICE_URL", "http://automation-service:8101")
    action_path = req.action.strip("/")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{automation_base}/automation/{action_path}", json=req.params)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"automation service unavailable: {exc}") from exc

    try:
        content = response.json()
    except ValueError:
        content = {"body": response.text}
    return JSONResponse(status_code=response.status_code, content=content)


@app.post("/agents/active-model")
async def set_active_model(req: ActiveModelRequest) -> dict:
    global _active_model_id

    lumyn_base = os.environ.get("LUMYN_BRIDGE_URL", "http://lumyn-bridge:8102")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{lumyn_base}/lumyn/default-model",
                json={"model_id": req.model_id},
            )
        if not response.is_success:
            detail = response.json().get("detail", "lumyn bridge rejected model") if response.headers.get("content-type", "").startswith("application/json") else response.text
            raise HTTPException(status_code=response.status_code, detail=detail)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"failed to update lumyn default model: {exc}") from exc

    _active_model_id = req.model_id
    return {"ok": True, "active_model": _active_model_id}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/inference/metrics")
async def inference_metrics() -> dict:
    """Forward metrics summary from the Vyrex inference proxy."""
    proxy_url = os.environ.get("VYREX_PROXY_URL", "http://vyrex-proxy:8105")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{proxy_url}/proxy/metrics/summary")
        return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"inference proxy unavailable: {exc}") from exc


@app.get("/inference/health")
async def inference_health() -> dict:
    """Forward health check from the Vyrex inference proxy."""
    proxy_url = os.environ.get("VYREX_PROXY_URL", "http://vyrex-proxy:8105")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{proxy_url}/proxy/health")
        return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"inference proxy unavailable: {exc}") from exc


@app.get("/computer/screenshot")
@app.post("/computer/screenshot")
async def computer_screenshot() -> dict:
    computer_url = os.environ.get("COMPUTER_USE_URL", "http://computer-use:8106")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{computer_url}/screenshot", json={})
        return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"computer-use service unavailable: {exc}") from exc


@app.post("/computer/task/run")
async def computer_task_run(
    req: ComputerTaskRunRequest,
    x_run_id: str | None = Header(default=None, alias="X-Run-ID"),
) -> dict:
    clear_stop()
    started = time.perf_counter()
    result = await _task_executor.run_task(req.task_description, req.max_steps, run_id=x_run_id)
    duration_ms = int((time.perf_counter() - started) * 1000)

    run_id = x_run_id or f"task-{int(time.time() * 1000)}"
    outcome = "success" if str(result.status).lower() in {"completed", "done", "success"} else "failure"
    error_message = None if outcome == "success" else result.message
    if str(result.status).lower() == "capability_needed" or (error_message and "capability_needed" in error_message.lower()):
        await _try_sdk_delegation(req.task_description, {"task_description": req.task_description, "max_steps": req.max_steps})
    asyncio.create_task(
        _notify_self_learning(
            task_id=run_id,
            description=req.task_description,
            action_sequence=result.actions,
            outcome=outcome,
            duration_ms=duration_ms,
            error_message=error_message,
            model_used=_active_model_id,
        )
    )

    return {
        "status": result.status,
        "steps": result.steps,
        "message": result.message,
        "actions": result.actions,
    }


@app.post("/computer/task/stop")
async def computer_task_stop() -> dict:
    request_stop()
    return {"ok": True, "stopped": True}


@app.get("/computer/health")
async def computer_health() -> dict:
    computer_url = os.environ.get("COMPUTER_USE_URL", "http://computer-use:8106")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{computer_url}/health")
        return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"computer-use service unavailable: {exc}") from exc


@app.post("/api/models/pull")
async def api_models_pull(req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{MODEL_HUB_URL}/models/pull", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"model-hub unavailable: {exc}") from exc


@app.get("/api/models/pull/{job_id}/progress")
async def api_models_pull_progress(job_id: str) -> StreamingResponse:
    async def _stream() -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", f"{MODEL_HUB_URL}/models/pull/{job_id}/progress") as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        _stream(),
        media_type=SSE_MEDIA_TYPE,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/models")
async def api_models_list() -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{MODEL_HUB_URL}/models")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"model-hub unavailable: {exc}") from exc


@app.post("/api/models/{model_id}/activate")
async def api_models_activate(model_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{MODEL_HUB_URL}/models/{model_id}/activate")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"model-hub unavailable: {exc}") from exc


@app.delete("/api/models/{model_id}")
async def api_models_delete(model_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(f"{MODEL_HUB_URL}/models/{model_id}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"model-hub unavailable: {exc}") from exc


@app.get("/api/models/{model_id}/benchmark")
async def api_models_benchmark(model_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{MODEL_HUB_URL}/models/{model_id}/benchmark")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"model-hub unavailable: {exc}") from exc


@app.get("/api/models/health")
async def api_models_health() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{MODEL_HUB_URL}/health")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"model-hub unavailable: {exc}") from exc


# Backward-compatible aliases
@app.get("/api/models/list")
async def api_models_list_legacy() -> dict:
    return await api_models_list()


@app.post("/api/models/set-default")
async def api_models_set_default_legacy(req: dict) -> dict:
    model_id = str(req.get("model_id") or req.get("alias") or "")
    if not model_id:
        raise HTTPException(status_code=422, detail="model_id is required")
    return await api_models_activate(model_id)


@app.get("/api/models/config")
async def api_models_config_legacy() -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{MODEL_HUB_URL}/models/config")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"model-hub unavailable: {exc}") from exc


@app.post("/api/memory")
async def api_memory_create(req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{MEMORY_SERVICE_URL}/memory", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc


@app.get("/api/memory/search")
async def api_memory_search(q: str = "", user_id: str = "default", top_k: int = 10, type: str | None = None) -> dict:
    try:
        params: dict[str, str | int] = {"q": q, "user_id": user_id, "top_k": top_k}
        if type:
            params["type"] = type
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{MEMORY_SERVICE_URL}/memory/search", params=params)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc


@app.get("/api/memory/{memory_id}")
async def api_memory_get(memory_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{MEMORY_SERVICE_URL}/memory/{memory_id}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc


@app.patch("/api/memory/{memory_id}")
async def api_memory_patch(memory_id: str, req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(f"{MEMORY_SERVICE_URL}/memory/{memory_id}", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc


@app.delete("/api/memory/{memory_id}")
async def api_memory_delete(memory_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(f"{MEMORY_SERVICE_URL}/memory/{memory_id}")
        if resp.content:
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        return JSONResponse(status_code=resp.status_code, content={"ok": True})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc


@app.post("/api/memory/ingest-task")
async def api_memory_ingest_task(req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{MEMORY_SERVICE_URL}/memory/ingest-task", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc


@app.post("/api/session/start")
async def api_session_start(req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{MEMORY_SERVICE_URL}/session/start", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc


@app.post("/api/session/end")
async def api_session_end(req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{MEMORY_SERVICE_URL}/session/end", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc


@app.get("/api/session/list")
async def api_session_list(user_id: str = "default", limit: int = 20) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{MEMORY_SERVICE_URL}/session/list", params={"user_id": user_id, "limit": limit})
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc


@app.get("/api/context/build")
async def api_context_build(q: str, user_id: str = "default", max_tokens: int = 1500) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{MEMORY_SERVICE_URL}/context/build",
                params={"q": q, "user_id": user_id, "max_tokens": max_tokens},
            )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc


@app.post("/api/persona")
async def api_persona_create(req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{PERSONA_SERVICE_URL}/persona", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.get("/api/persona")
async def api_persona_list() -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{PERSONA_SERVICE_URL}/persona")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.get("/api/persona/active")
async def api_persona_active() -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{PERSONA_SERVICE_URL}/persona/active")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.get("/api/persona/{persona_id}")
async def api_persona_get(persona_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{PERSONA_SERVICE_URL}/persona/{persona_id}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.patch("/api/persona/{persona_id}")
async def api_persona_patch(persona_id: str, req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(f"{PERSONA_SERVICE_URL}/persona/{persona_id}", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.delete("/api/persona/{persona_id}")
async def api_persona_delete(persona_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(f"{PERSONA_SERVICE_URL}/persona/{persona_id}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.post("/api/persona/{persona_id}/activate")
async def api_persona_activate(persona_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{PERSONA_SERVICE_URL}/persona/{persona_id}/activate")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Scheduler proxy routes
# ---------------------------------------------------------------------------

@app.post("/api/scheduler/job")
async def api_scheduler_create_job(req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{SCHEDULER_SERVICE_URL}/job", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"task-scheduler unavailable: {exc}") from exc


@app.get("/api/scheduler/job")
async def api_scheduler_list_jobs(limit: int = 50, offset: int = 0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{SCHEDULER_SERVICE_URL}/job", params={"limit": limit, "offset": offset})
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"task-scheduler unavailable: {exc}") from exc


@app.get("/api/scheduler/job/{job_id}")
async def api_scheduler_get_job(job_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{SCHEDULER_SERVICE_URL}/job/{job_id}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"task-scheduler unavailable: {exc}") from exc


@app.patch("/api/scheduler/job/{job_id}")
async def api_scheduler_patch_job(job_id: str, req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(f"{SCHEDULER_SERVICE_URL}/job/{job_id}", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"task-scheduler unavailable: {exc}") from exc


@app.delete("/api/scheduler/job/{job_id}")
async def api_scheduler_delete_job(job_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(f"{SCHEDULER_SERVICE_URL}/job/{job_id}")
        if resp.content:
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        return JSONResponse(status_code=resp.status_code, content={"ok": True})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"task-scheduler unavailable: {exc}") from exc


@app.post("/api/scheduler/job/{job_id}/run-now")
async def api_scheduler_run_now(job_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{SCHEDULER_SERVICE_URL}/job/{job_id}/run-now")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"task-scheduler unavailable: {exc}") from exc


@app.get("/api/scheduler/job/{job_id}/runs")
async def api_scheduler_get_runs(job_id: str, limit: int = 20, offset: int = 0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SCHEDULER_SERVICE_URL}/job/{job_id}/runs",
                params={"limit": limit, "offset": offset},
            )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"task-scheduler unavailable: {exc}") from exc


@app.get("/api/scheduler/health")
async def api_scheduler_health() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{SCHEDULER_SERVICE_URL}/health")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"task-scheduler unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Notification bus proxy routes
# ---------------------------------------------------------------------------

@app.get("/api/notifications/stream")
async def api_notifications_stream() -> StreamingResponse:
    async def _stream_proxy():
        try:
            async with httpx.AsyncClient(timeout=None) as c:
                async with c.stream("GET", f"{NOTIFICATION_BUS_URL}/stream") as r:
                    async for chunk in r.aiter_bytes():
                        yield chunk
        except Exception:
            pass

    return StreamingResponse(
        _stream_proxy(),
        media_type=SSE_MEDIA_TYPE,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/notifications/notify", status_code=201)
async def api_notifications_notify(req: Request) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{NOTIFICATION_BUS_URL}/notify", content=await req.body(), headers={"Content-Type": "application/json"})
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"notification-bus unavailable: {exc}") from exc


@app.get("/api/notifications/notification")
async def api_notifications_list(request: Request) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{NOTIFICATION_BUS_URL}/notification", params=dict(request.query_params))
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"notification-bus unavailable: {exc}") from exc


@app.get("/api/notifications/notification/{notif_id}")
async def api_notifications_get(notif_id: str) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{NOTIFICATION_BUS_URL}/notification/{notif_id}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"notification-bus unavailable: {exc}") from exc


@app.patch("/api/notifications/notification/{notif_id}/read")
async def api_notifications_mark_read(notif_id: str) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(f"{NOTIFICATION_BUS_URL}/notification/{notif_id}/read")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"notification-bus unavailable: {exc}") from exc


@app.post("/api/notifications/notification/read-all")
async def api_notifications_read_all() -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{NOTIFICATION_BUS_URL}/notification/read-all")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"notification-bus unavailable: {exc}") from exc


@app.delete("/api/notifications/notification/{notif_id}", status_code=204, response_model=None)
async def api_notifications_delete(notif_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.delete(f"{NOTIFICATION_BUS_URL}/notification/{notif_id}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="notification not found")
        if resp.status_code not in (200, 204):
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"notification-bus unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Audit Log proxy routes
# ---------------------------------------------------------------------------

@app.get("/api/audit/runs/stats")
async def api_audit_stats() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{AUDIT_LOG_URL}/runs/stats")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"audit-log unavailable: {exc}") from exc


@app.get("/api/audit/runs")
async def api_audit_list_runs(request: Request) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{AUDIT_LOG_URL}/runs", params=dict(request.query_params))
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"audit-log unavailable: {exc}") from exc


@app.get("/api/audit/runs/{run_id}")
async def api_audit_get_run(run_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{AUDIT_LOG_URL}/runs/{run_id}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"audit-log unavailable: {exc}") from exc


@app.post("/api/audit/runs/{run_id}/replay")
async def api_audit_replay_run(run_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{AUDIT_LOG_URL}/runs/{run_id}/replay")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"audit-log unavailable: {exc}") from exc


@app.get("/api/audit/health")
async def api_audit_health() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{AUDIT_LOG_URL}/health")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"audit-log unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Persona manager proxy routes (Phase 24)
# ---------------------------------------------------------------------------

@app.get("/api/personas")
async def api_personas_list() -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{PERSONA_SERVICE_URL}/personas")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.post("/api/personas")
async def api_personas_create(req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{PERSONA_SERVICE_URL}/personas", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.get("/api/personas/active")
async def api_personas_active() -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{PERSONA_SERVICE_URL}/persona/active")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.get("/api/personas/{persona_id}")
async def api_personas_get(persona_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{PERSONA_SERVICE_URL}/personas/{persona_id}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.patch("/api/personas/{persona_id}")
async def api_personas_patch(persona_id: str, req: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(f"{PERSONA_SERVICE_URL}/personas/{persona_id}", json=req)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.delete("/api/personas/{persona_id}")
async def api_personas_delete(persona_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(f"{PERSONA_SERVICE_URL}/personas/{persona_id}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.post("/api/personas/{persona_id}/clone")
async def api_personas_clone(persona_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{PERSONA_SERVICE_URL}/personas/{persona_id}/clone")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.post("/api/personas/{persona_id}/activate")
async def api_personas_activate(persona_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{PERSONA_SERVICE_URL}/personas/{persona_id}/activate")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.get("/api/personas/{persona_id}/memory-summary")
async def api_personas_memory_summary(persona_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{PERSONA_SERVICE_URL}/personas/{persona_id}/memory-summary")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


@app.post("/api/personas/{persona_id}/compress-memory")
async def api_personas_compress_memory(persona_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{PERSONA_SERVICE_URL}/personas/{persona_id}/compress-memory")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"persona-service unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Watchdog proxy routes (Phase 25)
# ---------------------------------------------------------------------------


@app.get("/api/watchdog/health")
async def api_watchdog_health() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{WATCHDOG_URL}/health")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"watchdog unavailable: {exc}") from exc


@app.get("/api/watchdog/services")
async def api_watchdog_services() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{WATCHDOG_URL}/services")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"watchdog unavailable: {exc}") from exc


@app.get("/api/watchdog/services/{service_name}")
async def api_watchdog_get_service(service_name: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{WATCHDOG_URL}/services/{service_name}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"watchdog unavailable: {exc}") from exc


@app.post("/api/watchdog/services/{service_name}/check")
async def api_watchdog_check_service(service_name: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{WATCHDOG_URL}/services/{service_name}/check")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"watchdog unavailable: {exc}") from exc


@app.post("/api/watchdog/services/{service_name}/restart")
async def api_watchdog_restart_service(service_name: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=35) as client:
            resp = await client.post(f"{WATCHDOG_URL}/services/{service_name}/restart")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"watchdog unavailable: {exc}") from exc


@app.get("/api/watchdog/incidents")
async def api_watchdog_incidents(request: Request) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{WATCHDOG_URL}/incidents", params=dict(request.query_params))
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"watchdog unavailable: {exc}") from exc


@app.get("/api/watchdog/incidents/stats")
async def api_watchdog_incidents_stats() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{WATCHDOG_URL}/incidents/stats")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"watchdog unavailable: {exc}") from exc


@app.post("/api/watchdog/scan")
async def api_watchdog_scan() -> dict:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{WATCHDOG_URL}/scan")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"watchdog unavailable: {exc}") from exc


async def _proxy_package_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(method, f"{PACKAGE_MANAGER_URL}{path}", params=params, json=json_body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"package-manager unavailable: {exc}") from exc


@app.get("/api/packages/health")
async def api_packages_health() -> dict:
    return await _proxy_package_request("GET", "/health")


@app.get("/api/packages/catalog")
async def api_packages_catalog(request: Request) -> dict:
    return await _proxy_package_request("GET", "/packages/catalog", params=dict(request.query_params))


@app.get("/api/packages/operations/stats")
async def api_packages_operations_stats() -> dict:
    return await _proxy_package_request("GET", "/operations/stats")


@app.get("/api/packages/operations")
async def api_packages_operations(request: Request) -> dict:
    return await _proxy_package_request("GET", "/operations", params=dict(request.query_params))


@app.get("/api/packages")
async def api_packages_list(request: Request) -> dict:
    return await _proxy_package_request("GET", "/packages", params=dict(request.query_params))


@app.post("/api/packages/install")
async def api_packages_install(request: Request) -> dict:
    body = await request.json()
    return await _proxy_package_request("POST", "/packages/install", json_body=body)


@app.get("/api/packages/{package_id}")
async def api_packages_get(package_id: str) -> dict:
    return await _proxy_package_request("GET", f"/packages/{package_id}")


@app.post("/api/packages/{package_id}/update")
async def api_packages_update(package_id: str) -> dict:
    return await _proxy_package_request("POST", f"/packages/{package_id}/update")


@app.post("/api/packages/{package_id}/enable")
async def api_packages_enable(package_id: str) -> dict:
    return await _proxy_package_request("POST", f"/packages/{package_id}/enable")


@app.post("/api/packages/{package_id}/disable")
async def api_packages_disable(package_id: str) -> dict:
    return await _proxy_package_request("POST", f"/packages/{package_id}/disable")


@app.post("/api/packages/{package_id}/check")
async def api_packages_check(package_id: str) -> dict:
    return await _proxy_package_request("POST", f"/packages/{package_id}/check")


@app.delete("/api/packages/{package_id}")
async def api_packages_remove(package_id: str) -> dict:
    return await _proxy_package_request("DELETE", f"/packages/{package_id}")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "agents": len(_manager.list_agents())}


@app.get("/api/security/health")
async def api_security_health() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{SECURITY_POLICY_URL}/health")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"security-policy unavailable: {exc}") from exc


@app.get("/api/security/policies")
async def api_security_policies(request: Request) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{SECURITY_POLICY_URL}/policies", params=dict(request.query_params))
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"security-policy unavailable: {exc}") from exc


@app.get("/api/security/policies/{subject_type}/{subject_id}")
async def api_security_policies_subject(subject_type: str, subject_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{SECURITY_POLICY_URL}/policies/{subject_type}/{subject_id}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"security-policy unavailable: {exc}") from exc


@app.post("/api/security/grant")
async def api_security_grant(request: Request) -> dict:
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{SECURITY_POLICY_URL}/policies/grant", json=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"security-policy unavailable: {exc}") from exc


@app.post("/api/security/revoke")
async def api_security_revoke(request: Request) -> dict:
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{SECURITY_POLICY_URL}/policies/revoke", json=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"security-policy unavailable: {exc}") from exc


@app.post("/api/security/check")
async def api_security_check(request: Request) -> dict:
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{SECURITY_POLICY_URL}/policies/check", json=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"security-policy unavailable: {exc}") from exc


@app.get("/api/security/audit")
async def api_security_audit(request: Request) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{SECURITY_POLICY_URL}/audit", params=dict(request.query_params))
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"security-policy unavailable: {exc}") from exc


@app.get("/api/security/audit/stats")
async def api_security_audit_stats() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{SECURITY_POLICY_URL}/audit/stats")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"security-policy unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# OTA proxy routes (Phase 30)
# ---------------------------------------------------------------------------


@app.get("/api/ota/status")
async def api_ota_status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OTA_SERVICE_URL}/status")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ota-service unavailable: {exc}") from exc


@app.post("/api/ota/check")
async def api_ota_check() -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{OTA_SERVICE_URL}/check")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ota-service unavailable: {exc}") from exc


@app.post("/api/ota/download")
async def api_ota_download() -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{OTA_SERVICE_URL}/download")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ota-service unavailable: {exc}") from exc


@app.post("/api/ota/apply")
async def api_ota_apply() -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{OTA_SERVICE_URL}/apply")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ota-service unavailable: {exc}") from exc


@app.post("/api/ota/commit")
async def api_ota_commit() -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{OTA_SERVICE_URL}/commit")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ota-service unavailable: {exc}") from exc


@app.post("/api/ota/rollback")
async def api_ota_rollback() -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{OTA_SERVICE_URL}/rollback")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ota-service unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Voice Service proxy routes (Phase 31)
# ---------------------------------------------------------------------------

VOICE_SERVICE_URL = os.environ.get("VOICE_SERVICE_URL", "http://voice-service:8012")
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth-service:8013")


@app.get("/api/voice/status")
async def api_voice_status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{VOICE_SERVICE_URL}/voice/status")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"voice-service unavailable: {exc}") from exc


@app.post("/api/voice/transcribe")
async def api_voice_transcribe(request: Request) -> dict:
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{VOICE_SERVICE_URL}/voice/transcribe", json=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"voice-service unavailable: {exc}") from exc


@app.post("/api/voice/speak")
async def api_voice_speak(request: Request) -> dict:
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{VOICE_SERVICE_URL}/voice/speak", json=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"voice-service unavailable: {exc}") from exc


@app.post("/api/voice/pipeline")
async def api_voice_pipeline(request: Request) -> dict:
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{VOICE_SERVICE_URL}/voice/pipeline", json=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"voice-service unavailable: {exc}") from exc


@app.get("/api/voice/models")
async def api_voice_models() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            stt_resp = await client.get(f"{VOICE_SERVICE_URL}/voice/models/stt")
            tts_resp = await client.get(f"{VOICE_SERVICE_URL}/voice/models/tts")
        return JSONResponse(status_code=200, content={
            "stt_models": stt_resp.json().get("models", []),
            "tts_models": tts_resp.json().get("models", []),
        })
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"voice-service unavailable: {exc}") from exc


@app.post("/api/voice/models/{model_name}/load")
async def api_voice_load_model(model_name: str) -> dict:
    try:
        # Determine if it's STT or TTS based on model name patterns
        if model_name in ["tiny", "base", "small", "medium", "large"]:
            url = f"{VOICE_SERVICE_URL}/voice/models/stt/activate"
            body = {"model_size": model_name}
        else:
            url = f"{VOICE_SERVICE_URL}/voice/models/tts/activate"
            body = {"voice": model_name}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"voice-service unavailable: {exc}") from exc


@app.post("/api/voice/wake-word/enable")
async def api_voice_wake_word_enable() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{VOICE_SERVICE_URL}/voice/start")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"voice-service unavailable: {exc}") from exc


@app.post("/api/voice/wake-word/disable")
async def api_voice_wake_word_disable() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{VOICE_SERVICE_URL}/voice/stop")
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"voice-service unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Auth Service proxy routes (Phase 32)
# ---------------------------------------------------------------------------


@app.post("/auth/login")
async def api_auth_login(request: Request) -> dict:
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{AUTH_SERVICE_URL}/auth/login", json=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"auth-service unavailable: {exc}") from exc


@app.post("/auth/refresh")
async def api_auth_refresh(request: Request) -> dict:
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{AUTH_SERVICE_URL}/auth/refresh", json=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"auth-service unavailable: {exc}") from exc


@app.post("/auth/logout")
async def api_auth_logout(request: Request) -> dict:
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{AUTH_SERVICE_URL}/auth/logout", json=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"auth-service unavailable: {exc}") from exc


@app.get("/auth/me")
async def api_auth_me(request: Request) -> dict:
    try:
        auth_header = request.headers.get("authorization")
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AUTH_SERVICE_URL}/auth/me", headers=headers)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"auth-service unavailable: {exc}") from exc


@app.get("/auth/verify")
async def api_auth_verify(request: Request) -> dict:
    try:
        auth_header = request.headers.get("authorization")
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AUTH_SERVICE_URL}/auth/verify", headers=headers)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"auth-service unavailable: {exc}") from exc


@app.get("/users")
async def api_users(request: Request) -> dict:
    try:
        auth_header = request.headers.get("authorization")
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AUTH_SERVICE_URL}/users", headers=headers)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"auth-service unavailable: {exc}") from exc


@app.post("/users/{username}/role")
async def api_user_role(username: str, request: Request) -> dict:
    try:
        body = await request.json()
        auth_header = request.headers.get("authorization")
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{AUTH_SERVICE_URL}/users/{username}/role", json=body, headers=headers)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"auth-service unavailable: {exc}") from exc


@app.get("/users/{username}/prefs")
async def api_user_prefs(username: str, request: Request) -> dict:
    try:
        auth_header = request.headers.get("authorization")
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AUTH_SERVICE_URL}/users/{username}/prefs", headers=headers)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"auth-service unavailable: {exc}") from exc


@app.patch("/users/{username}/prefs")
async def api_user_prefs_patch(username: str, request: Request) -> dict:
    try:
        body = await request.json()
        auth_header = request.headers.get("authorization")
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.patch(f"{AUTH_SERVICE_URL}/users/{username}/prefs", json=body, headers=headers)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"auth-service unavailable: {exc}") from exc
