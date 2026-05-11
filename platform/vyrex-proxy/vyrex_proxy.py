"""
vyrex_proxy.py – Vyrex Inference Proxy (port 8105)

Transparent proxy in front of Ollama that enforces Vyrex policies,
tracks per-request metrics, and exposes a summary endpoint for the
Performance Dashboard UI.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

_SHARED_PATH = Path(__file__).resolve().parents[1] / "shared"
if str(_SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(_SHARED_PATH))

from auth_middleware import require_auth

# ── constants ─────────────────────────────────────────────────────────────────
PROXY_VERSION = "1.0.0"
METRICS_MAX = 200
_DEFAULT_POLICY_PATH = (
    Path(__file__).parent.parent.parent / "vyrex" / "policies" / "inference_policy.yaml"
)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "llama3")

logger = logging.getLogger(__name__)

app = FastAPI(title="Vyrex Inference Proxy", version=PROXY_VERSION)

# ── metrics store ─────────────────────────────────────────────────────────────
@dataclass
class RequestRecord:
    id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    timestamp: float
    status: str  # "success" | "error"


_metrics: deque[RequestRecord] = deque(maxlen=METRICS_MAX)
_active_model_id: str = DEFAULT_MODEL
_active_model_path: str = ""

# ── rate limiter (sliding window) ────────────────────────────────────────────
_action_timestamps: deque[float] = deque(maxlen=10_000)


# ── policy helpers ────────────────────────────────────────────────────────────
def _load_policy() -> dict[str, Any]:
    policy_path = Path(os.environ.get("INFERENCE_POLICY_PATH", str(_DEFAULT_POLICY_PATH)))
    if not policy_path.exists():
        return {
            "max_prompt_tokens": 4096,
            "max_requests_per_minute": 60,
            "blocked_models": [],
            "require_model_allowlist": False,
            "allowed_models": [],
            "stream_allowed": True,
            "vram_limit_mb": 0,
        }
    with policy_path.open() as fh:
        return yaml.safe_load(fh) or {}


def _assert_policy(model: str, prompt_tokens: int) -> None:
    policy = _load_policy()
    # rate limit
    max_rpm: int = policy.get("max_requests_per_minute", 60)
    now = time.time()
    window_start = now - 60.0
    _action_timestamps.append(now)
    recent = sum(1 for t in _action_timestamps if t > window_start)
    if recent > max_rpm:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    # blocked models
    blocked: list[str] = policy.get("blocked_models", []) or []
    for pattern in blocked:
        if re.fullmatch(pattern.replace("*", ".*"), model):
            raise HTTPException(status_code=403, detail=f"Model '{model}' is blocked by policy")
    # prompt token budget
    max_tokens: int = policy.get("max_prompt_tokens", 4096)
    if prompt_tokens > max_tokens:
        raise HTTPException(
            status_code=422,
            detail=f"Prompt exceeds token budget: {prompt_tokens} > {max_tokens}",
        )


def _count_tokens(text: str) -> int:
    """Approximate token count via whitespace split."""
    return len(text.split())


def _count_chat_tokens(messages: list[dict[str, Any]]) -> int:
    """Sum word counts across all message content fields."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += _count_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += _count_tokens(str(part.get("text", "")))
    return total


# ── VRAM detection ────────────────────────────────────────────────────────────
def _read_vram() -> dict[str, Any]:
    """Try to read VRAM from /proc/driver/nvidia; fall back to mock zeros."""
    try:
        pattern = "/proc/driver/nvidia/gpus/*/information"
        files = glob.glob(pattern)
        if not files:
            return {"vram_used_mb": 0, "vram_total_mb": 0, "vram_source": "unavailable"}
        info = Path(files[0]).read_text(encoding="utf-8", errors="replace")
        total_mb = 0
        for line in info.splitlines():
            if "GPU Memory:" in line:
                # e.g. "GPU Memory:    16376 MiB"
                nums = re.findall(r"\d+", line)
                if nums:
                    total_mb = int(nums[0])
                    break
        # used VRAM: not available from /proc; return 0
        return {"vram_used_mb": 0, "vram_total_mb": total_mb, "vram_source": "proc"}
    except Exception:
        return {"vram_used_mb": 0, "vram_total_mb": 0, "vram_source": "unavailable"}


# ── request / response models ─────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    model: str | None = None
    prompt: str
    images: list[str] = []
    stream: bool = False
    options: dict[str, Any] = {}


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]] = []
    stream: bool = False
    options: dict[str, Any] = {}


class PullRequest(BaseModel):
    name: str


class ActiveModelUpdateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_id: str
    model_path: str


# ── helpers ───────────────────────────────────────────────────────────────────
async def _forward_json(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=120) as client:
        if method == "GET":
            resp = await client.get(f"{OLLAMA_URL}{path}")
        else:
            resp = await client.post(f"{OLLAMA_URL}{path}", json=body)
    resp.raise_for_status()
    return resp.json()


def _get_default_model() -> str:
    config_path = Path(os.getenv("DATA_DIR", "/app/data")) / "model_hub_config.json"
    try:
        return json.loads(config_path.read_text(encoding="utf-8")).get("default_model", DEFAULT_MODEL)
    except Exception:
        return DEFAULT_MODEL


def _get_effective_model(explicit_model: str | None) -> str:
    if explicit_model:
        return explicit_model
    if _active_model_id:
        return _active_model_id
    return _get_default_model()


# ── endpoints ─────────────────────────────────────────────────────────────────
@app.post("/proxy/generate")
async def proxy_generate(req: GenerateRequest) -> dict[str, Any]:
    model = _get_effective_model(req.model)
    prompt_tokens = _count_tokens(req.prompt)
    _assert_policy(model, prompt_tokens)
    t0 = time.time()
    status = "success"
    completion_tokens = 0
    try:
        body: dict[str, Any] = {
            "model": model,
            "prompt": req.prompt,
            "stream": False,
            "options": req.options,
        }
        if req.images:
            body["images"] = req.images
        result = await _forward_json("POST", "/api/generate", body)
        completion_tokens = _count_tokens(str(result.get("response", "")))
    except HTTPException:
        status = "error"
        raise
    except Exception as exc:
        status = "error"
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {exc}") from exc
    finally:
        latency_ms = round((time.time() - t0) * 1000, 2)
        _metrics.append(
            RequestRecord(
                id=str(uuid.uuid4()),
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                timestamp=time.time(),
                status=status,
            )
        )
    return result


@app.post("/proxy/chat")
async def proxy_chat(req: ChatRequest) -> dict[str, Any]:
    model = _get_effective_model(req.model)
    prompt_tokens = _count_chat_tokens(req.messages)
    _assert_policy(model, prompt_tokens)
    t0 = time.time()
    status = "success"
    completion_tokens = 0
    try:
        body: dict[str, Any] = {
            "model": model,
            "messages": req.messages,
            "stream": False,
            "options": req.options,
        }
        result = await _forward_json("POST", "/api/chat", body)
        msg_content = ""
        if isinstance(result.get("message"), dict):
            msg_content = str(result["message"].get("content", ""))
        completion_tokens = _count_tokens(msg_content)
    except HTTPException:
        status = "error"
        raise
    except Exception as exc:
        status = "error"
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {exc}") from exc
    finally:
        latency_ms = round((time.time() - t0) * 1000, 2)
        _metrics.append(
            RequestRecord(
                id=str(uuid.uuid4()),
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                timestamp=time.time(),
                status=status,
            )
        )
    return result


@app.post("/v1/chat/completions")
async def v1_chat_completions(
    req: ChatRequest,
    _current_user: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    return await proxy_chat(req)


@app.get("/proxy/models")
async def proxy_models() -> dict[str, Any]:
    try:
        data = await _forward_json("GET", "/api/tags")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {exc}") from exc
    models = data.get("models", [])
    for m in models:
        m.setdefault("status", "ready")
        m.setdefault("size_mb", round(m.get("size", 0) / (1024 * 1024), 1))
    return {"models": models}


@app.post("/proxy/models/pull")
async def proxy_model_pull(req: PullRequest, raw_request: Request) -> StreamingResponse:
    async def _stream() -> Any:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/pull",
                json={"name": req.name},
            ) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@app.get("/proxy/metrics")
def proxy_metrics() -> dict[str, Any]:
    records = list(_metrics)
    return {
        "requests": [
            {
                "id": r.id,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "latency_ms": r.latency_ms,
                "timestamp": r.timestamp,
                "status": r.status,
            }
            for r in records
        ]
    }


@app.get("/proxy/metrics/summary")
def proxy_metrics_summary() -> dict[str, Any]:
    records = list(_metrics)
    total = len(records)
    latencies = [r.latency_ms for r in records]
    avg_latency = round(sum(latencies) / total, 2) if total > 0 else 0.0
    sorted_lat = sorted(latencies)
    p95_idx = int(0.95 * len(sorted_lat))
    p95_latency = sorted_lat[p95_idx] if sorted_lat else 0.0
    total_completion = sum(r.completion_tokens for r in records)
    total_latency_s = sum(r.latency_ms for r in records) / 1000.0
    tps = round(total_completion / total_latency_s, 2) if total_latency_s > 0 else 0.0
    active_models = list({r.model for r in records if r.status == "success"})
    vram = _read_vram()
    return {
        "total_requests": total,
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95_latency,
        "tokens_per_second_avg": tps,
        "active_models": active_models,
        "queue_depth": 0,
        **vram,
    }


@app.get("/proxy/health")
async def proxy_health() -> dict[str, Any]:
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            reachable = resp.is_success
    except Exception:
        reachable = False
    return {
        "status": "ok",
        "ollama_reachable": reachable,
        "proxy_version": PROXY_VERSION,
        "active_model_id": _active_model_id,
        "active_model_path": _active_model_path,
    }


@app.post("/active-model")
async def set_active_model(req: ActiveModelUpdateRequest) -> dict[str, Any]:
    global _active_model_id, _active_model_path
    _active_model_id = req.model_id
    _active_model_path = req.model_path
    logger.info("Hot-swapped active model to %s", req.model_id)
    return {"ok": True, "model_id": _active_model_id, "model_path": _active_model_path}


@app.get("/active-model")
async def get_active_model() -> dict[str, Any]:
    return {"model_id": _active_model_id, "model_path": _active_model_path}
