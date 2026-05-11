"""FastAPI application – Vyrex model gateway.

Exposed routes
──────────────
  POST /v1/chat/completions   OpenAI-compatible chat
  POST /v1/completions        OpenAI-compatible text completion
  GET  /v1/models             List all registered models
  GET  /healthz               Health / liveness check
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import yaml

from app.audit import get_audit_logger, reset_audit_logger
from app.config import load_vyrex_settings, load_routing_policy, reset_config_cache
from app.gateway import GatewayError, ModelGateway
from app.vyrex import VyrexMiddleware
from app.middleware import CorrelationIDMiddleware
from app.policy import RoutingPolicyEngine, reset_policy_engine
from app.registry import ModelRegistry, reset_registry
from app.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    CompletionRequest,
    CompletionResponse,
    ErrorDetail,
    ErrorResponse,
    LoadedModelsResponse,
    ModelInfo,
    ModelsResponse,
    PullModelRequest,
    PullModelResponse,
)

# Load .env if present (development convenience)
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
_GATEWAY_NOT_INITIALISED = "Gateway not initialised"
_REGISTRY_NOT_INITIALISED = "Registry not initialised"

# ---------------------------------------------------------------------------
# Application-level singletons (created once at startup)
# ---------------------------------------------------------------------------

_gateway: ModelGateway | None = None
_registry: ModelRegistry | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _gateway, _registry

    # --- startup ---
    logger.info("model-gateway starting up")
    policy_cfg = load_routing_policy()
    vyrex_settings = load_vyrex_settings()
    audit = get_audit_logger()
    engine = RoutingPolicyEngine(policy_cfg)
    vyrex = VyrexMiddleware(
        enabled=vyrex_settings.enabled,
        endpoint=vyrex_settings.endpoint,
        storage_dir=str(vyrex_settings.model_storage_dir),
        hf_token=vyrex_settings.huggingface_token,
    )
    _gateway = ModelGateway(
        policy_cfg=policy_cfg,
        policy_engine=engine,
        audit=audit,
        vyrex=vyrex,
    )
    _registry = ModelRegistry()
    logger.info(
        "routing mode=%s, registered models=%d, vyrex_enabled=%s, nvidia_gpu=%s",
        policy_cfg.mode,
        len(_registry),
        vyrex_settings.enabled,
        vyrex.nvidia_gpu_detected,
    )
    yield

    # --- shutdown ---
    logger.info("model-gateway shutting down")
    reset_config_cache()
    reset_policy_engine()
    reset_registry()
    reset_audit_logger()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Vyrex Model Gateway",
    description=(
        "OpenAI-compatible inference gateway with local-first routing. "
        "Routes requests to Ollama (local) or cloud providers based on policy."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(CorrelationIDMiddleware)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(GatewayError)
async def gateway_error_handler(request: Request, exc: GatewayError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(message=str(exc))
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error [correlation_id=%s]", _cid(request))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error=ErrorDetail(message="Internal server error", type="internal_error")
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, Any]:
    """Liveness probe."""
    return {"status": "ok", "ts": int(time.time())}


@app.get("/v1/models", response_model=ModelsResponse, tags=["models"])
async def list_models() -> ModelsResponse:
    """Return all models known to the registry."""
    assert _registry is not None, _REGISTRY_NOT_INITIALISED
    provider_map = {
        "ollama": "kryos",
        "openai": "openai",
        "anthropic": "anthropic",
        "vyrex": "vyrex",
    }
    data = [
        ModelInfo(
            id=m.id,
            owned_by=provider_map.get(m.provider, m.provider),
        )
        for m in _registry.all()
    ]
    return ModelsResponse(data=data)


@app.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    tags=["chat"],
)
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
) -> ChatCompletionResponse:
    """OpenAI-compatible chat completion endpoint."""
    assert _gateway is not None, _GATEWAY_NOT_INITIALISED
    return await _gateway.chat_completion(body, correlation_id=_cid(request))


@app.post(
    "/v1/completions",
    response_model=CompletionResponse,
    tags=["completions"],
)
async def completions(
    request: Request,
    body: CompletionRequest,
) -> CompletionResponse:
    """OpenAI-compatible text completion endpoint (converted to chat internally)."""
    assert _gateway is not None, _GATEWAY_NOT_INITIALISED
    return await _gateway.completion(body, correlation_id=_cid(request))


@app.post("/models/pull", response_model=PullModelResponse, tags=["models"])
async def pull_model(body: PullModelRequest) -> PullModelResponse:
    """Pull a model from HuggingFace or GitHub via Vyrex."""
    assert _gateway is not None, _GATEWAY_NOT_INITIALISED
    result = await _gateway.pull_model(body.source, checksum=body.checksum)
    return PullModelResponse(
        status=str(result.get("status", "error")),
        source=body.source,
        model_id=result.get("model_id"),
        path=result.get("path"),
        provider=result.get("provider"),
        detail=result.get("detail"),
    )


@app.get("/models/loaded", response_model=LoadedModelsResponse, tags=["models"])
async def loaded_models() -> LoadedModelsResponse:
    """List models loaded through Vyrex runtime pull."""
    assert _gateway is not None, _GATEWAY_NOT_INITIALISED
    models = await _gateway.list_loaded_models()
    return LoadedModelsResponse(loaded_models=models)


@app.post("/models/{model_id}/activate", tags=["models"])
async def activate_model(model_id: str) -> dict[str, Any]:
    """Set a model as default in routing policy for primary capabilities."""
    policy_path = Path(os.getenv("MG_POLICY_PATH", "./config/routing-policy.yaml"))
    if not policy_path.exists():
        raise GatewayError(f"Routing policy not found: {policy_path}", status_code=404)

    def _read_policy() -> dict[str, Any]:
        with policy_path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    policy_data = await asyncio.to_thread(_read_policy)

    defaults = dict(policy_data.get("default_models") or {})
    for capability in ("chat", "code", "vision"):
        defaults[capability] = model_id
    policy_data["default_models"] = defaults

    def _write_policy() -> None:
        with policy_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(policy_data, fh, sort_keys=False)

    await asyncio.to_thread(_write_policy)

    return {"ok": True, "model_id": model_id, "default_models": defaults}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cid(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


# ===========================================================================
# Vision endpoints  (Phase 8)
# ===========================================================================

class VisionDescribeRequest(BaseModel):
    image_b64: str
    prompt: str = "Describe the screen in detail."


@app.post("/vision/describe", tags=["vision"])
async def vision_describe(request: Request, body: VisionDescribeRequest) -> dict[str, Any]:
    """Describe a screen image using the active vision model."""
    assert _gateway is not None, _GATEWAY_NOT_INITIALISED
    assert _registry is not None, _REGISTRY_NOT_INITIALISED

    # Build a vision message — encode image as data URI in the message content
    vision_message = {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{body.image_b64}"},
            },
            {"type": "text", "text": body.prompt},
        ],
    }

    # Load current routing policy to find the active vision model
    policy_cfg = load_routing_policy()
    model_id: str = (policy_cfg.default_models or {}).get("vision", "llava")  # type: ignore[union-attr]

    vision_req = ChatCompletionRequest(
        model=model_id,
        messages=[vision_message],  # type: ignore[arg-type]
        temperature=0.2,
        max_tokens=512,
    )
    try:
        resp = await _gateway.chat_completion(vision_req, correlation_id=_cid(request))
        description = resp.choices[0].message.content if resp.choices else ""
    except Exception as exc:
        logger.warning("vision_describe failed: %s", exc)
        description = f"[Vision model unavailable: {exc}]"

    return {"description": description, "model_used": model_id}


@app.get("/vision/status", tags=["vision"])
async def vision_status() -> dict[str, Any]:
    """Return vision subsystem readiness."""
    assert _registry is not None, "Registry not initialised"
    policy_cfg = load_routing_policy()
    active_model: str = (policy_cfg.default_models or {}).get("vision", "llava")  # type: ignore[union-attr]
    all_ids = [m.id for m in _registry.all()]
    available = active_model in all_ids
    return {"ready": available, "active_model": active_model, "registered_models": all_ids}
