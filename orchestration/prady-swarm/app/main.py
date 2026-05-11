"""FastAPI entrypoint for the Kryos Swarm Orchestration service."""
from __future__ import annotations

import logging
import sys
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from app.config import load_config
from app.lumyn_bridge import LumynBridge, Skill, list_skills, get_skill, remove_skill
from app.rag_store import RAGStore
from app.schemas import (
    StartSwarmRequest,
    StartSwarmResponse,
    SwarmResultResponse,
    SwarmState,
    SwarmStatusResponse,
)
from app.skill_curator import SkillCurator
from app.swarm_orchestrator import SwarmOrchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_orchestrator: SwarmOrchestrator | None = None
_skill_curator: SkillCurator | None = None
_ORCHESTRATOR_NOT_INIT = "SwarmOrchestrator not initialised"

# Simple admin key guard for destructive endpoints
_ADMIN_KEY_HEADER = APIKeyHeader(name="X-Admin-Key", auto_error=False)
_ADMIN_KEY = os.getenv("SWARM_ADMIN_KEY", "kryos-admin-dev")


def _require_admin(key: Optional[str] = Security(_ADMIN_KEY_HEADER)) -> str:
    if key != _ADMIN_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")
    return key


# Pydantic models for Lumyn / Soul / AgentNet requests -------------------

class AcquireSkillRequest(BaseModel):
    task_description: str
    user_id: str = "default"


class ExecuteSkillRequest(BaseModel):
    skill_id: str
    context: Dict[str, Any] = {}
    user_id: str = "default"


class AgentVerifyRequest(BaseModel):
    from_agent: str
    payload: str          # base64-encoded bytes
    signature: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _orchestrator, _skill_curator

    cfg = load_config()
    logging.getLogger().setLevel(cfg.log_level)

    cfg.chromadb_path.mkdir(parents=True, exist_ok=True)
    rag = RAGStore(path=str(cfg.chromadb_path))

    _orchestrator = SwarmOrchestrator(
        model_id=cfg.swarm_model,
        gateway_url=cfg.model_gateway_url,
        workflow_engine_url=cfg.workflow_engine_url,
        max_swarm_agents=cfg.max_swarm_agents,
        rag_store=rag,
    )
    logger.info(
        "SwarmOrchestrator ready — model=%s max_agents=%d gateway=%s",
        cfg.swarm_model,
        cfg.max_swarm_agents,
        cfg.model_gateway_url,
    )

    # Start skill curator background task
    _skill_curator = SkillCurator()
    _skill_curator.start()

    yield

    if _skill_curator:
        _skill_curator.stop()
    logger.info("SwarmOrchestrator shutting down")


app = FastAPI(
    title="Kryos Swarm Orchestration",
    description="Multi-agent swarm coordination with RAG memory and parallel execution.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/healthz", tags=["meta"])
async def healthz() -> Dict[str, Any]:
    return {"status": "ok", "service": "kryos-swarm"}


@app.post(
    "/swarm/start",
    response_model=StartSwarmResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["swarm"],
)
async def start_swarm(body: StartSwarmRequest) -> StartSwarmResponse:
    """Decompose a goal and launch parallel agent execution."""
    assert _orchestrator is not None, _ORCHESTRATOR_NOT_INIT

    swarm_id = await _orchestrator.coordinate_swarm(
        goal=body.goal,
        max_agents=body.max_agents,
        model_id=body.model_id,
    )
    record = _orchestrator.get_swarm(swarm_id)
    assert record is not None

    return StartSwarmResponse(
        swarm_id=swarm_id,
        goal=body.goal,
        max_agents=body.max_agents,
        model_id=record.model_id,
        status=record.status,
    )


@app.get("/swarm/status", response_model=SwarmStatusResponse, tags=["swarm"])
async def swarm_status() -> SwarmStatusResponse:
    """Return status of all active swarms."""
    assert _orchestrator is not None, _ORCHESTRATOR_NOT_INIT

    raw = await _orchestrator.get_swarm_status()
    swarms = [SwarmState.model_validate(r) for r in raw]
    return SwarmStatusResponse(swarms=swarms)


@app.post("/swarm/{swarm_id}/cancel", tags=["swarm"])
async def cancel_swarm(swarm_id: str) -> Dict[str, Any]:
    """Cancel a running swarm."""
    assert _orchestrator is not None, _ORCHESTRATOR_NOT_INIT

    ok = await _orchestrator.cancel_swarm(swarm_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Swarm '{swarm_id}' not found",
        )
    return {"swarm_id": swarm_id, "cancelled": True}


@app.get(
    "/swarm/{swarm_id}/result",
    response_model=SwarmResultResponse,
    tags=["swarm"],
)
async def swarm_result(swarm_id: str) -> SwarmResultResponse:
    """Return the merged result for a completed swarm."""
    assert _orchestrator is not None, _ORCHESTRATOR_NOT_INIT

    record = _orchestrator.get_swarm(swarm_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Swarm '{swarm_id}' not found",
        )
    return SwarmResultResponse(
        swarm_id=swarm_id,
        status=record.status,
        merged_result=record.merged_result,
    )


# ===========================================================================
# Lumyn skill endpoints  (7.1 + 7.2)
# ===========================================================================

@app.post("/lumyn/skill/acquire", tags=["lumyn"])
async def acquire_skill(body: AcquireSkillRequest) -> Dict[str, Any]:
    """Acquire (or synthesise) a Lumyn skill for the given task."""
    # Load SOUL context for this user
    soul_context: Optional[str] = None
    try:
        import sys as _sys
        import os as _os
        _sys.path.insert(0, str(_os.path.join(_os.path.dirname(__file__), "..", "..", "..", "platform")))
        from soul.soul_manager import SoulManager
        soul_context = SoulManager().load(body.user_id)
    except Exception:
        pass

    bridge = LumynBridge(soul_context=soul_context, agent_id="lumyn-bridge")
    skill = await bridge.acquire_skill(body.task_description)
    return {"skill": skill.to_dict()}


@app.post("/lumyn/skill/execute", tags=["lumyn"])
async def execute_skill(body: ExecuteSkillRequest) -> Dict[str, Any]:
    """Execute a previously acquired skill by ID."""
    skill = get_skill(body.skill_id)
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{body.skill_id}' not found",
        )
    if skill.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Skill '{body.skill_id}' is not active (status={skill.status})",
        )

    soul_context: Optional[str] = None
    try:
        import sys as _sys
        import os as _os
        _sys.path.insert(0, str(_os.path.join(_os.path.dirname(__file__), "..", "..", "..", "platform")))
        from soul.soul_manager import SoulManager
        soul_context = SoulManager().load(body.user_id)
    except Exception:
        pass

    bridge = LumynBridge(soul_context=soul_context, agent_id="lumyn-bridge")
    result = await bridge.execute_skill(skill, body.context)
    return {"result": result.to_dict()}


@app.get("/lumyn/skills", tags=["lumyn"])
async def list_lumyn_skills() -> Dict[str, Any]:
    """List all skills with grade, status, and telemetry."""
    skills = [s.to_dict() for s in list_skills()]
    return {"skills": skills, "total": len(skills)}


@app.delete("/lumyn/skills/{skill_id}", tags=["lumyn"])
async def delete_skill(
    skill_id: str,
    _admin: str = Security(_require_admin),
) -> Dict[str, Any]:
    """Manually prune a skill (admin only)."""
    removed = remove_skill(skill_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_id}' not found",
        )
    return {"skill_id": skill_id, "deleted": True}


# ===========================================================================
# SOUL endpoints  (7.3)
# ===========================================================================

try:
    import sys as _sys
    import os as _os
    _sys.path.insert(0, str(_os.path.join(_os.path.dirname(__file__), "..", "..", "..", "platform")))
    from soul.router import router as soul_router
    app.include_router(soul_router)
    logger.info("Soul router mounted at /soul")
except Exception as _soul_exc:
    logger.warning("Soul router not mounted: %s", _soul_exc)


# ===========================================================================
# AgentNet endpoints  (7.4)
# ===========================================================================

@app.get("/agentnet/identities", tags=["agentnet"])
async def agentnet_identities() -> Dict[str, Any]:
    """List all registered agent public keys."""
    try:
        import sys as _sys
        import os as _os
        _sys.path.insert(0, str(_os.path.join(_os.path.dirname(__file__), "..", "..", "..", "platform")))
        from agentnet.identity import get_all_public_keys  # type: ignore[import]
        keys = get_all_public_keys()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return {"identities": keys, "total": len(keys)}


@app.post("/agentnet/verify", tags=["agentnet"])
async def agentnet_verify(body: AgentVerifyRequest) -> Dict[str, Any]:
    """Verify a signed inter-agent message."""
    import base64
    try:
        import sys as _sys
        import os as _os
        _sys.path.insert(0, str(_os.path.join(_os.path.dirname(__file__), "..", "..", "..", "platform")))
        from agentnet.identity import generate_identity, verify_message  # type: ignore[import]

        # Get sender's public key
        identity = generate_identity(body.from_agent)
        payload_bytes = base64.b64decode(body.payload)
        valid = verify_message(identity.public_key_pem, payload_bytes, body.signature)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    return {"valid": valid, "from_agent": body.from_agent}


# ===========================================================================
# Phase 8: Vision / Input / Task / Process / Memory endpoints
# ===========================================================================

import base64 as _b64
import json as _json

from fastapi.responses import StreamingResponse

_PLATFORM_PATH = str(
    __import__("pathlib").Path(__file__).resolve().parents[3] / "platform"
)


def _add_platform() -> None:
    import sys
    if _PLATFORM_PATH not in sys.path:
        sys.path.insert(0, _PLATFORM_PATH)


_VISION_AGENT_URL = os.getenv("VISION_AGENT_URL", "http://localhost:8091")
_INPUT_CONTROLLER_URL = os.getenv("INPUT_CONTROLLER_URL", "http://localhost:8092")
_PROCESS_MANAGER_URL = os.getenv("PROCESS_MANAGER_URL", "http://localhost:8093")
_MEMORY_STORE_URL = os.getenv("MEMORY_STORE_URL", "http://localhost:8094")
_GATEWAY_URL = os.getenv("MODEL_GATEWAY_URL", "http://localhost:8000")


# ── Vision ────────────────────────────────────────────────────────────────

@app.get("/vision/status", tags=["vision"])
async def vision_status() -> Dict[str, Any]:
    """Return vision agent readiness."""
    _add_platform()
    try:
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "platform" / "vision-agent"))
        from vision_agent import VisionAgent  # type: ignore[import-not-found]
        _va = VisionAgent(gateway_url=_GATEWAY_URL)
        return {"ready": True, "gateway": _GATEWAY_URL}
    except Exception as exc:
        return {"ready": False, "error": str(exc)}


class VisionCaptureRequest(BaseModel):
    describe: bool = False


@app.post("/vision/capture", tags=["vision"])
async def vision_capture(body: VisionCaptureRequest) -> Dict[str, Any]:
    """Capture the current screen and optionally describe it."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "platform" / "vision-agent"))
    try:
        from vision_agent import VisionAgent  # type: ignore[import-not-found]
        va = VisionAgent(gateway_url=_GATEWAY_URL)
        img_bytes = va.capture_screen_bytes()
        img_b64 = _b64.b64encode(img_bytes).decode()
        result: Dict[str, Any] = {"image_b64": img_b64}
        if body.describe:
            image = va.capture_screen()
            result["description"] = await va.describe_screen(image)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vision capture failed: {exc}")


# ── Input ─────────────────────────────────────────────────────────────────

@app.get("/input/screenshot", tags=["input"])
async def input_screenshot() -> Dict[str, Any]:
    """Return a live screenshot as base64 PNG."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "platform" / "input-controller"))
    try:
        from input_controller import InputController  # type: ignore[import-not-found]
        ic = InputController()
        png_bytes = ic.screenshot()
        return {"image_b64": _b64.b64encode(png_bytes).decode(), "format": "png"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Screenshot failed: {exc}")


class InputActionRequest(BaseModel):
    action: str  # click|double_click|right_click|type_text|hotkey|scroll|move_mouse
    params: Dict[str, Any] = {}
    agent_id: str = "ui"


_ALLOWED_ACTIONS = {
    "click", "double_click", "right_click", "type_text",
    "hotkey", "scroll", "move_mouse",
}


@app.post("/input/action", tags=["input"])
async def input_action(body: InputActionRequest) -> Dict[str, Any]:
    """Execute a single desktop input action."""
    if body.action not in _ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action!r}")
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "platform" / "input-controller"))
    try:
        from input_controller import InputController  # type: ignore[import-not-found]
        ic = InputController(agent_id=body.agent_id)
        from app.task_executor import _dispatch_action
        _dispatch_action(ic, body.action, body.params)
        return {"success": True, "action": body.action, "params": body.params}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Action failed: {exc}")


# ── Task execution ────────────────────────────────────────────────────────

class TaskExecuteRequest(BaseModel):
    goal: str
    user_id: str = "default"
    max_steps: int = 50


TASK_AUDIT_LOG = __import__("pathlib").Path("platform/audit/task_execution.jsonl")


@app.post("/task/execute", tags=["task"])
async def task_execute(body: TaskExecuteRequest) -> StreamingResponse:
    """Execute an autonomous desktop task and stream step events as SSE."""
    import sys
    _va_path = str(__import__("pathlib").Path(__file__).resolve().parents[3] / "platform" / "vision-agent")
    _ic_path = str(__import__("pathlib").Path(__file__).resolve().parents[3] / "platform" / "input-controller")
    sys.path.insert(0, _va_path)
    sys.path.insert(0, _ic_path)

    from app.task_executor import AutonomousTaskExecutor  # type: ignore[import]

    executor = AutonomousTaskExecutor(gateway_url=_GATEWAY_URL)

    async def event_stream():
        async for event in executor.execute_goal(
            goal=body.goal,
            user_id=body.user_id,
            max_steps=body.max_steps,
        ):
            yield f"data: {_json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.delete("/task/{task_id}", tags=["task"])
async def abort_task(task_id: str) -> Dict[str, Any]:
    """Abort a running task by ID (best-effort)."""
    return {"task_id": task_id, "aborted": True}


@app.get("/task/history", tags=["task"])
async def task_history(limit: int = 100) -> Dict[str, Any]:
    """Return the last N task execution records."""
    audit_path = TASK_AUDIT_LOG
    if not audit_path.exists():
        return {"history": [], "total": 0}
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    records = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(_json.loads(line))
        except _json.JSONDecodeError:
            continue
        if len(records) >= limit:
            break
    return {"history": records, "total": len(records)}


# ── Process manager router ────────────────────────────────────────────────

try:
    import sys as _sys2
    _sys2.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "platform" / "process-manager"))
    from process_manager_router import router as _process_router  # type: ignore[import-not-found]
    app.include_router(_process_router)
    logger.info("Process manager router mounted")
except Exception as _pm_exc:
    logger.warning("Process manager router not mounted: %s", _pm_exc)


# ── Memory store router ───────────────────────────────────────────────────

try:
    import sys as _sys3
    _sys3.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "platform" / "memory-store"))
    from memory_store_router import router as _memory_router  # type: ignore[import-not-found]
    app.include_router(_memory_router)
    logger.info("Memory store router mounted")
except Exception as _ms_exc:
    logger.warning("Memory store router not mounted: %s", _ms_exc)