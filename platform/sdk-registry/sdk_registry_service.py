from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from capability_router import CapabilityRouter
from manifest_validator import ManifestValidator
from registry_db import RegistryDB
from sandbox_manager import SandboxManager

VERSION = "1.0.0"
SERVICE_NAME = "sdk-registry"
DB_PATH = "/data/sdk_registry/registry.db"
WORKSPACE_BASE = "/home/user/kryos-apps"


class InstallRequest(BaseModel):
    manifest_url: str | None = None
    manifest_json: dict[str, Any] | None = None

    @field_validator("manifest_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("manifest_url must not be empty")
        return value


class DelegateRequest(BaseModel):
    capability: str
    payload: dict[str, Any]
    timeout_ms: int = 5000


class FsRequest(BaseModel):
    app_id: str
    path: str


class FsWriteRequest(BaseModel):
    app_id: str
    path: str
    content: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = RegistryDB(db_path=DB_PATH)
    await db.init()
    app.state.db = db
    app.state.validator = ManifestValidator()
    app.state.sandbox = SandboxManager(workspace_base=WORKSPACE_BASE)
    app.state.router = CapabilityRouter(db)
    yield
    if app.state.db:
        await app.state.db.close()


app = FastAPI(title="Kryos SDK Registry", version=VERSION, lifespan=lifespan)


def _manifest_from_app(app_row: dict[str, Any]) -> dict[str, Any]:
    manifest = app_row.get("manifest_json") or {}
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    return manifest


async def _load_manifest(request: InstallRequest) -> dict[str, Any]:
    if request.manifest_json is not None:
        return request.manifest_json
    if request.manifest_url:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(request.manifest_url)
        resp.raise_for_status()
        return resp.json()
    raise HTTPException(status_code=422, detail="manifest_url or manifest_json required")


@app.get("/sdk/apps")
async def list_apps() -> list[dict[str, Any]]:
    rows = await app.state.db.get_all_apps()
    return [
        {
            "app_id": row["app_id"],
            "display_name": row["display_name"],
            "version": row["version"],
            "author": row["author"],
            "status": row["status"],
            "permissions": row.get("permissions", []),
            "capabilities": row.get("capabilities", []),
            "installed_ts": row["installed_ts"],
            "last_active_ts": row.get("last_active_ts"),
        }
        for row in rows
    ]


@app.post("/sdk/apps/validate")
async def validate_manifest(request: InstallRequest) -> dict[str, Any]:
    manifest = await _load_manifest(request)
    result = app.state.validator.validate(manifest)
    return {"valid": result.valid, "errors": result.errors, "permissions": manifest.get("permissions", [])}


@app.post("/sdk/apps/install")
async def install_app(request: InstallRequest) -> dict[str, Any]:
    manifest = await _load_manifest(request)
    result = app.state.validator.validate(manifest)
    if not result.valid:
        raise HTTPException(status_code=422, detail={"errors": result.errors})
    try:
        app_id = await app.state.db.register_app(manifest)
        app.state.sandbox.start_app(app_id, manifest)
        await app.state.db.update_status(app_id, "running", f"kryos-sdk-{app_id}")
        return {"app_id": app_id, "status": "installed", "message": "App installed successfully"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/sdk/apps/{app_id}")
async def uninstall_app(app_id: str) -> dict[str, bool]:
    existing = await app.state.db.get_app(app_id)
    if not existing:
        raise HTTPException(status_code=404, detail="app not found")
    app.state.sandbox.remove_app(app_id)
    removed = await app.state.db.remove_app(app_id)
    return {"uninstalled": removed}


@app.post("/sdk/apps/{app_id}/start")
async def start_app(app_id: str) -> dict[str, Any]:
    existing = await app.state.db.get_app(app_id)
    if not existing:
        raise HTTPException(status_code=404, detail="app not found")
    manifest = _manifest_from_app(existing)
    info = app.state.sandbox.start_app(app_id, manifest)
    await app.state.db.update_status(app_id, "running", info.container_id)
    return {"status": "running", "container_id": info.container_id}


@app.post("/sdk/apps/{app_id}/stop")
async def stop_app(app_id: str) -> dict[str, str]:
    existing = await app.state.db.get_app(app_id)
    if not existing:
        raise HTTPException(status_code=404, detail="app not found")
    app.state.sandbox.stop_app(app_id)
    await app.state.db.update_status(app_id, "stopped", None)
    return {"status": "stopped"}


@app.get("/sdk/apps/{app_id}/status")
async def app_status(app_id: str) -> dict[str, Any]:
    existing = await app.state.db.get_app(app_id)
    if not existing:
        raise HTTPException(status_code=404, detail="app not found")
    status = app.state.sandbox.get_status(app_id)
    return {
        "app_id": app_id,
        "status": status.status,
        "container_id": status.container_id,
        "uptime_seconds": status.uptime_seconds,
        "memory_used_mb": status.memory_used_mb,
        "cpu_pct": status.cpu_pct,
    }


@app.post("/sdk/delegate")
async def delegate(request: DelegateRequest) -> dict[str, Any]:
    result = await app.state.router.delegate(request.capability, request.payload, request.timeout_ms)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.error)
    return {"app_id": result.app_id, "result": result.result, "latency_ms": result.latency_ms}


@app.get("/sdk/capabilities")
async def capabilities() -> list[dict[str, Any]]:
    return await app.state.router.get_capability_map()


@app.post("/sdk/fs/read")
async def fs_read(request: FsRequest) -> dict[str, Any]:
    if not app.state.validator.is_safe_path(request.path):
        raise HTTPException(status_code=400, detail="unsafe path")
    path = Path(WORKSPACE_BASE) / request.app_id / request.path
    content = path.read_text(encoding="utf-8")
    return {"content": content, "size_bytes": len(content.encode("utf-8"))}


@app.post("/sdk/fs/write")
async def fs_write(request: FsWriteRequest) -> dict[str, Any]:
    if not app.state.validator.is_safe_path(request.path):
        raise HTTPException(status_code=400, detail="unsafe path")
    data = request.content.encode("utf-8")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file too large")
    path = Path(WORKSPACE_BASE) / request.app_id / request.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(request.content, encoding="utf-8")
    return {"written": True, "size_bytes": len(data)}


@app.get("/sdk/fs/list")
async def fs_list(app_id: str, path: str = Query(default="/")) -> dict[str, Any]:
    if not app.state.validator.is_safe_path(path):
        raise HTTPException(status_code=400, detail="unsafe path")
    root = Path(WORKSPACE_BASE) / app_id / path.lstrip("/")
    entries = []
    if root.exists():
        for child in root.iterdir():
            stat = child.stat()
            entries.append({"name": child.name, "is_dir": child.is_dir(), "size_bytes": stat.st_size, "modified_ts": stat.st_mtime})
    return {"entries": entries}


@app.delete("/sdk/fs/delete")
async def fs_delete(request: FsRequest) -> dict[str, bool]:
    if not app.state.validator.is_safe_path(request.path):
        raise HTTPException(status_code=400, detail="unsafe path")
    path = Path(WORKSPACE_BASE) / request.app_id / request.path
    if path.exists():
        path.unlink()
        return {"deleted": True}
    return {"deleted": False}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": VERSION,
        "installed_apps": await app.state.db.get_installed_count(),
        "running_apps": await app.state.db.get_running_count(),
    }
