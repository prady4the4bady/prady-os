from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_POLICY_PATH = _ROOT / "vyrex" / "policies" / "lumyn_policy.yaml"
MODELS_DIR = Path(os.environ.get("LUMYN_MODELS_DIR", "/models"))
SKILLS_DIR = Path.home() / ".lumyn" / "skills"
REGISTRY_FILE = MODELS_DIR / "registry.json"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
# Vyrex proxy URL — if set, all Ollama calls route through the proxy.
# Falls back to direct OLLAMA_URL if VYREX_PROXY_URL is not set.
_VYREX_PROXY_URL = os.environ.get("VYREX_PROXY_URL", "")
_INFERENCE_BASE = _VYREX_PROXY_URL if _VYREX_PROXY_URL else OLLAMA_URL
_GENERATE_PATH = "/proxy/generate" if _VYREX_PROXY_URL else "/api/generate"
MEMORY_SERVICE_URL = os.getenv("MEMORY_SERVICE_URL", "http://memory-service:8108")
PERSONA_SERVICE_URL = os.getenv("PERSONA_SERVICE_URL", "http://persona-service:8109")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _ensure_runtime_dirs()
    yield


app = FastAPI(title="Kryos Lumyn Bridge", version="1.0.0", lifespan=lifespan)

_running_tasks: dict[str, dict[str, Any]] = {}


class TaskRequest(BaseModel):
    task: str
    model_id: str = "lumyn-default"
    context: dict[str, Any] = {}


class PullRequest(BaseModel):
    source: str
    url: str


class SkillsRequest(BaseModel):
    action: str = "list"
    name: str | None = None
    content: str | None = None


class DefaultModelRequest(BaseModel):
    model_id: str


def _ensure_runtime_dirs() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_FILE.exists():
        REGISTRY_FILE.write_text(json.dumps({"models": [], "default_model": "lumyn-default"}, indent=2), encoding="utf-8")


def _policy_path() -> Path:
    configured = os.environ.get("LUMYN_POLICY_PATH")
    return Path(configured) if configured else DEFAULT_POLICY_PATH


def _load_policy() -> dict[str, Any]:
    path = _policy_path()
    if not path.exists():
        return {
            "allowed_task_types": ["general"],
            "blocked_keywords": [],
            "max_task_duration_s": 120,
            "require_user_confirmation_for": [],
            "model_sources_allowed": ["huggingface", "github", "ollama"],
        }
    with open(path, encoding="utf-8") as handle:
        policy = yaml.safe_load(handle) or {}
    policy.setdefault("allowed_task_types", ["general"])
    policy.setdefault("blocked_keywords", [])
    policy.setdefault("max_task_duration_s", 120)
    policy.setdefault("require_user_confirmation_for", [])
    policy.setdefault("model_sources_allowed", ["huggingface", "github", "ollama"])
    return policy


def _slugify(value: str) -> str:
    value = value.strip().rstrip("/")
    value = re.sub(r"^https?://", "", value)
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower()[:120]


def _load_registry() -> dict[str, Any]:
    _ensure_runtime_dirs()
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))


def _save_registry(registry: dict[str, Any]) -> None:
    _ensure_runtime_dirs()
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def _list_registered_models() -> list[dict[str, Any]]:
    registry = _load_registry()
    models = registry.get("models", [])
    out: list[dict[str, Any]] = []
    for model in models:
        path = Path(model["path"])
        size_bytes = 0
        if path.exists():
            if path.is_file():
                size_bytes = path.stat().st_size
            else:
                size_bytes = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        out.append({**model, "size_bytes": size_bytes})
    return out


def _set_default_model(model_id: str) -> dict[str, Any]:
    registry = _load_registry()
    if not any(model.get("id") == model_id for model in registry.get("models", [])) and model_id != "lumyn-default":
        raise HTTPException(status_code=404, detail=f"model not registered: {model_id}")
    registry["default_model"] = model_id
    _save_registry(registry)
    return {"ok": True, "default_model": model_id}


def _check_task_policy(req: TaskRequest) -> None:
    policy = _load_policy()
    task_type = str(req.context.get("task_type", "general"))
    if task_type not in policy["allowed_task_types"]:
        raise HTTPException(status_code=403, detail=f"task_type not allowed: {task_type}")

    lowered = req.task.lower()
    for keyword in policy["blocked_keywords"]:
        if keyword.lower() in lowered:
            raise HTTPException(status_code=403, detail=f"blocked keyword detected: {keyword}")

    confirm_required = set(policy["require_user_confirmation_for"])
    if task_type in confirm_required and not bool(req.context.get("user_confirmed", False)):
        raise HTTPException(status_code=403, detail=f"user confirmation required for {task_type}")


def _dispatch_with_lumyn_agent(req: TaskRequest, timeout_s: int) -> dict[str, Any]:
    cmd = [
        "lumyn-agent",
        "--task",
        req.task,
        "--model",
        req.model_id,
        "--json-output",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout_s)
    stdout = proc.stdout.strip()
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"output": stdout}
    else:
        payload = {"output": ""}
    return {"backend": "lumyn-agent", "result": payload}


async def _dispatch_with_ollama(req: TaskRequest) -> dict[str, Any]:
    persona_prompt = await _fetch_active_persona()
    memory_context = await _fetch_memory_context(req.task)

    prompt_parts: list[str] = []
    if persona_prompt:
        prompt_parts.append(persona_prompt)
    if memory_context:
        prompt_parts.append(memory_context)
    prompt_parts.append(req.task)

    prompt = "\n\n".join(prompt_parts)

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{_INFERENCE_BASE}{_GENERATE_PATH}",
            json={"model": req.model_id, "prompt": prompt, "stream": False},
        )
    response.raise_for_status()
    body = response.json()
    return {"backend": "ollama", "result": body}


async def _fetch_active_persona() -> str:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{PERSONA_SERVICE_URL}/persona/active")
        if response.status_code == 200:
            active = response.json().get("active")
            if isinstance(active, dict):
                return str(active.get("system_prompt", "") or "")
    except Exception:
        pass
    return ""


async def _fetch_memory_context(query: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(
                f"{MEMORY_SERVICE_URL}/context/build",
                params={"q": query, "max_tokens": 800},
            )
        if response.status_code == 200:
            return response.json().get("context", "")
    except Exception:
        pass
    return ""


async def _ingest_task_memory(task_description: str, result: str, duration_s: float, steps_taken: int) -> None:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                f"{MEMORY_SERVICE_URL}/memory/ingest-task",
                json={
                    "task_description": task_description,
                    "result": result,
                    "duration_s": duration_s,
                    "steps_taken": steps_taken,
                },
            )
    except Exception:
        pass


def _repo_id_from_hf_url(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    if cleaned.startswith("hf://"):
        return cleaned[len("hf://") :]
    cleaned = re.sub(r"^https?://huggingface.co/", "", cleaned)
    return cleaned.split("/tree/")[0].split("/resolve/")[0]


def _register_model(model_id: str, source: str, source_url: str, path: Path, status: str = "ready") -> dict[str, Any]:
    registry = _load_registry()
    models = [m for m in registry.get("models", []) if m.get("id") != model_id]
    model = {
        "id": model_id,
        "source": source,
        "url": source_url,
        "path": str(path),
        "status": status,
        "updated_at": time.time(),
    }
    models.append(model)
    registry["models"] = models
    _save_registry(registry)
    return model


@app.post("/lumyn/task")
async def lumyn_task(req: TaskRequest) -> dict[str, Any]:
    _check_task_policy(req)
    policy = _load_policy()
    task_id = f"task-{int(time.time() * 1000)}"
    started_at = time.time()
    _running_tasks[task_id] = {
        "task": req.task,
        "model_id": req.model_id,
        "status": "running",
        "started_at": started_at,
    }

    try:
        try:
            dispatch = _dispatch_with_lumyn_agent(req, int(policy["max_task_duration_s"]))
        except FileNotFoundError:
            dispatch = await _dispatch_with_ollama(req)
        _running_tasks[task_id]["status"] = "done"
        _running_tasks[task_id]["finished_at"] = time.time()
        _running_tasks[task_id]["result"] = dispatch["result"]
        await _ingest_task_memory(
            task_description=req.task,
            result="done",
            duration_s=_running_tasks[task_id]["finished_at"] - started_at,
            steps_taken=1,
        )
        return {
            "task_id": task_id,
            "status": "done",
            "backend": dispatch["backend"],
            "result": dispatch["result"],
        }
    except Exception as exc:
        _running_tasks[task_id]["status"] = "error"
        _running_tasks[task_id]["error"] = str(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/lumyn/status")
def lumyn_status() -> dict[str, Any]:
    skills = sorted([p.name for p in SKILLS_DIR.glob("*.yaml")])
    recent_tasks = list(_running_tasks.items())[-20:]
    return {
        "tasks": [{"task_id": task_id, **entry} for task_id, entry in recent_tasks],
        "memory_summary": {
            "skills_count": len(skills),
            "skills": skills,
            "models_registered": len(_load_registry().get("models", [])),
        },
    }


@app.post("/lumyn/model/pull")
def pull_model(req: PullRequest) -> dict[str, Any]:
    policy = _load_policy()
    if req.source not in policy["model_sources_allowed"]:
        raise HTTPException(status_code=403, detail=f"model source blocked by policy: {req.source}")

    slug = _slugify(req.url)
    target = MODELS_DIR / slug
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    if req.source == "huggingface":
        repo_id = _repo_id_from_hf_url(req.url)
        try:
            from huggingface_hub import snapshot_download
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"huggingface_hub unavailable: {exc}") from exc
        snapshot_download(repo_id=repo_id, local_dir=str(target), local_dir_use_symlinks=False)
    elif req.source == "github":
        try:
            from git import Repo
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"gitpython unavailable: {exc}") from exc
        Repo.clone_from(req.url, str(target))
    else:
        raise HTTPException(status_code=400, detail=f"unsupported source: {req.source}")

    model = _register_model(model_id=slug, source=req.source, source_url=req.url, path=target)
    return {"ok": True, "model": model}


@app.get("/lumyn/models")
def list_models() -> dict[str, Any]:
    registry = _load_registry()
    return {"models": _list_registered_models(), "default_model": registry.get("default_model", "lumyn-default")}


@app.delete("/lumyn/models/{model_id}")
def delete_model(model_id: str) -> dict[str, Any]:
    registry = _load_registry()
    models = registry.get("models", [])
    target = next((m for m in models if m.get("id") == model_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"model not found: {model_id}")
    path = Path(target["path"])
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    registry["models"] = [m for m in models if m.get("id") != model_id]
    if registry.get("default_model") == model_id:
        registry["default_model"] = "lumyn-default"
    _save_registry(registry)
    return {"ok": True, "deleted": model_id}


@app.post("/lumyn/skills")
def skills(req: SkillsRequest | None = None) -> dict[str, Any]:
    _ensure_runtime_dirs()
    payload = req or SkillsRequest(action="list")
    action = payload.action.lower()

    if action == "list":
        items = sorted([p.name for p in SKILLS_DIR.glob("*.yaml")])
        return {"skills": items}

    if action == "add":
        if not payload.name:
            raise HTTPException(status_code=400, detail="name is required for add")
        content = payload.content or "name: skill\nversion: '1.0'\ndescription: user skill\n"
        skill_file = SKILLS_DIR / f"{_slugify(payload.name)}.yaml"
        skill_file.write_text(content, encoding="utf-8")
        return {"ok": True, "skill": skill_file.name}

    if action == "remove":
        if not payload.name:
            raise HTTPException(status_code=400, detail="name is required for remove")
        skill_file = SKILLS_DIR / f"{_slugify(payload.name)}.yaml"
        if skill_file.exists():
            skill_file.unlink()
        return {"ok": True, "removed": skill_file.name}

    raise HTTPException(status_code=400, detail=f"unsupported skills action: {action}")


@app.post("/lumyn/default-model")
def set_default_model(req: DefaultModelRequest) -> dict[str, Any]:
    return _set_default_model(req.model_id)