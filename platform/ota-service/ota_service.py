from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from delta_patcher import DeltaPatcher
from slot_manager import SlotManager


MANIFEST_URL = os.environ.get("MANIFEST_URL", "http://localhost:8012/static/manifest.json")
SLOT_DB_PATH = os.environ.get("SLOT_DB_PATH", "/data/ota/slot_state.db")
STAGING_DIR = Path(os.environ.get("STAGING_DIR", "/data/ota/staging"))
GRUBENV_PATH = os.environ.get("GRUBENV_PATH", "/tmp/grubenv")

APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
SLOTS_DIR = STAGING_DIR.parent / "slots"


def _load_local_manifest_validator() -> tuple[type, type, type]:
    module_path = APP_DIR / "manifest_validator.py"
    spec = importlib.util.spec_from_file_location("ota_manifest_validator", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load manifest validator from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Manifest, module.ManifestValidator, module.ValidationError


Manifest, ManifestValidator, ValidationError = _load_local_manifest_validator()

VALIDATOR = ManifestValidator()
PATCHER = DeltaPatcher()
SLOT_MANAGER = SlotManager(SLOT_DB_PATH, GRUBENV_PATH)

LAST_CHECK_TS: str | None = None
LAST_MANIFEST: Manifest | None = None
DOWNLOADS: dict[str, dict[str, Any]] = {}
DOWNLOAD_TASKS: dict[str, asyncio.Task[None]] = {}


class HealthReportRequest(BaseModel):
    success: bool
    service: str


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    SLOTS_DIR.mkdir(parents=True, exist_ok=True)
    for slot in ("slot_a", "slot_b"):
        slot_dir = SLOTS_DIR / slot
        slot_dir.mkdir(parents=True, exist_ok=True)
        rootfs = slot_dir / "rootfs.bin"
        if not rootfs.exists():
            rootfs.write_bytes(b"")
    yield


app = FastAPI(title="Kryos OTA Service", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _fetch_manifest() -> Manifest:
    if MANIFEST_URL.startswith("file://"):
        path = Path(MANIFEST_URL.replace("file://", "", 1))
        raw = json.loads(path.read_text(encoding="utf-8"))
    elif MANIFEST_URL.startswith("http"):
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(MANIFEST_URL)
            resp.raise_for_status()
            raw = resp.json()
    else:
        path = Path(MANIFEST_URL)
        raw = json.loads(path.read_text(encoding="utf-8"))

    return VALIDATOR.validate(raw)


def _slot_rootfs(slot: str) -> Path:
    return SLOTS_DIR / f"slot_{slot}" / "rootfs.bin"


async def _download_worker(download_id: str, manifest: Manifest) -> None:
    total = max(1, manifest.size_delta)
    download_path = STAGING_DIR / f"{download_id}.delta"
    DOWNLOADS[download_id]["path"] = str(download_path)

    async with aiofiles.open(download_path, "wb") as handle:
        bytes_written = 0
        chunks = 8
        chunk_size = max(1, total // chunks)
        while bytes_written < total:
            write_now = min(chunk_size, total - bytes_written)
            await handle.write(b"0" * write_now)
            bytes_written += write_now
            percent = (bytes_written / total) * 100
            DOWNLOADS[download_id].update(
                {
                    "bytes_downloaded": bytes_written,
                    "total_bytes": total,
                    "percent": percent,
                    "done": bytes_written >= total,
                }
            )
            await asyncio.sleep(0.02)

    SLOT_MANAGER.set_state("IDLE")


@app.get("/status")
async def status() -> dict[str, Any]:
    state = SLOT_MANAGER.get_state()
    return {
        "active_slot": state["active_slot"],
        "version": state["active_version"],
        "last_check_ts": state.get("last_check_ts") or LAST_CHECK_TS,
        "state": state["state"],
    }


@app.post("/check")
async def check_update() -> dict[str, Any]:
    global LAST_MANIFEST, LAST_CHECK_TS

    LAST_CHECK_TS = _now_iso()
    SLOT_MANAGER.set_last_check(LAST_CHECK_TS)

    try:
        manifest = await _fetch_manifest()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"manifest fetch failed: {exc}") from exc

    LAST_MANIFEST = manifest
    current_version = SLOT_MANAGER.get_state()["active_version"]
    update_available = VALIDATOR.is_newer_than(manifest, current_version)

    return {
        "update_available": update_available,
        "version": manifest.version,
        "changelog": manifest.changelog,
    }


@app.post("/download")
async def download_update() -> dict[str, Any]:
    if LAST_MANIFEST is None:
        raise HTTPException(status_code=400, detail="no checked manifest; call /check first")

    SLOT_MANAGER.set_state("DOWNLOADING")

    download_id = str(uuid.uuid4())
    DOWNLOADS[download_id] = {
        "bytes_downloaded": 0,
        "total_bytes": max(1, LAST_MANIFEST.size_delta),
        "percent": 0.0,
        "done": False,
        "path": None,
    }

    task = asyncio.create_task(_download_worker(download_id, LAST_MANIFEST))
    DOWNLOAD_TASKS[download_id] = task

    return {"download_id": download_id}


@app.get("/download/{download_id}/progress")
async def download_progress(download_id: str) -> StreamingResponse:
    if download_id not in DOWNLOADS:
        raise HTTPException(status_code=404, detail="download not found")

    async def _stream() -> Any:
        for _ in range(120):
            progress = DOWNLOADS[download_id]
            payload = {
                "bytes_downloaded": progress["bytes_downloaded"],
                "total_bytes": progress["total_bytes"],
                "percent": round(progress["percent"], 2),
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if progress["done"]:
                break
            await asyncio.sleep(0.05)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/apply")
async def apply_update() -> dict[str, Any]:
    if LAST_MANIFEST is None:
        raise HTTPException(status_code=400, detail="no checked manifest")

    latest_download = next(iter(reversed(DOWNLOADS.values())), None)
    if not latest_download or not latest_download.get("path"):
        raise HTTPException(status_code=400, detail="no download available")

    SLOT_MANAGER.set_state("APPLYING")

    state = SLOT_MANAGER.get_state()
    source = _slot_rootfs(state["active_slot"])
    target = _slot_rootfs(state["standby_slot"])
    patch_path = Path(str(latest_download["path"]))

    ok = PATCHER.apply_patch(source, patch_path, target, expected_sha256=LAST_MANIFEST.sha256_full)
    if not ok:
        SLOT_MANAGER.set_state("IDLE")
        raise HTTPException(status_code=422, detail="patched file sha256 mismatch")

    SLOT_MANAGER.set_standby_version(LAST_MANIFEST.version)
    SLOT_MANAGER.set_state("IDLE")

    return {"status": "applied", "slot": state["standby_slot"]}


@app.post("/commit")
async def commit_update() -> dict[str, Any]:
    if LAST_MANIFEST is None:
        raise HTTPException(status_code=400, detail="no checked manifest")

    committed = SLOT_MANAGER.mark_committed(LAST_MANIFEST.version)

    return {
        "status": "committed",
        "next_slot": committed["standby_slot"],
    }


@app.post("/rollback")
async def rollback_update() -> dict[str, Any]:
    rolled = SLOT_MANAGER.rollback()
    return {"status": "rolled_back", "active_slot": rolled["active_slot"]}


@app.get("/history")
async def history() -> dict[str, Any]:
    state = SLOT_MANAGER.get_state()
    return {"history": state["update_history"], "total": len(state["update_history"]) }


@app.post("/health-report")
async def health_report(req: HealthReportRequest) -> dict[str, Any]:
    updated = SLOT_MANAGER.record_boot_health(req.success)
    return {
        "ok": True,
        "service": req.service,
        "boot_fail_count": updated["boot_fail_count"],
        "rolled_back": bool(updated.get("rolled_back", False)),
        "active_slot": updated["active_slot"],
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8012)
