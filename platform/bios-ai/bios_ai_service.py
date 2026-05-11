"""Kryos BIOS AI Service (Stage 2) - port 8017."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from brain_db import BrainDB
from efi_reader import EFIReader
from filesystem_checker import FilesystemChecker
from hardware_profiler import HardwareProfiler
from repair_engine import RepairEngine

VERSION = "1.0.0"
SERVICE_NAME = "bios-ai"

DATA_DIR = Path(os.environ.get("DATA_DIR", "/var/kryos/bios-ai"))
DB_PATH = DATA_DIR / "bios_ai.db"

AUDIT_LOG_URL = os.environ.get("AUDIT_LOG_URL", "http://audit-log:8112")
NOTIFY_URL = os.environ.get("NOTIFICATION_BUS_URL", "http://notification-bus:8111")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.efi_reader = EFIReader()
    app.state.fs_checker = FilesystemChecker()
    app.state.hw_profiler = HardwareProfiler()
    app.state.db = BrainDB(DB_PATH)
    await app.state.db.init()
    app.state.repair_engine = RepairEngine(app.state.db, app.state.fs_checker)
    app.state.scan_tasks: dict[str, asyncio.Task[None]] = {}
    app.state.stage2_complete = False
    app.state.repairs_made = 0
    app.state.last_boot_ts = _utc_now()

    # Startup boot snapshot
    start = time.perf_counter()
    decision = app.state.efi_reader.read_boot_decision()
    hw = await app.state.hw_profiler.profile()
    duration_ms = int((time.perf_counter() - start) * 1000)

    await app.state.db.save_hardware_snapshot(hw)
    await app.state.db.add_boot_history(
        decision=decision,
        repairs_made=0,
        boot_time_ms=duration_ms,
        hardware_score=float(hw.get("hardware_score", 0.0)),
        stage1_ran=decision in {"NORMAL", "REPAIR", "SAFE", "RECOVERY"},
        stage2_complete=True,
    )
    app.state.stage2_complete = True

    yield


app = FastAPI(title="Kryos BIOS AI Service", version=VERSION, lifespan=lifespan)


async def _run_scan(scan_id: str) -> None:
    scan_results = await app.state.fs_checker.scan()

    summary = await app.state.repair_engine.run(
        scan_results,
        audit_url=AUDIT_LOG_URL,
        notify_url=NOTIFY_URL,
        scan_id=scan_id,
    )

    app.state.repairs_made += summary.issues_fixed
    await app.state.db.set_scan_status(
        scan_id,
        status="complete",
        issues_found=summary.issues_found,
        issues_fixed=summary.issues_fixed,
        issues_pending_approval=summary.issues_pending_approval,
    )


@app.get("/bios-ai/status")
async def bios_ai_status() -> dict[str, Any]:
    decision = app.state.efi_reader.read_boot_decision()
    history = await app.state.db.list_boot_history(limit=1)
    latest = history[0] if history else {
        "hardware_score": 0.0,
        "ts": app.state.last_boot_ts,
    }

    return {
        "boot_decision": decision,
        "stage1_ran": decision in {"NORMAL", "REPAIR", "SAFE", "RECOVERY"},
        "stage2_complete": bool(app.state.stage2_complete),
        "repairs_made": int(app.state.repairs_made),
        "hardware_score": float(latest.get("hardware_score", 0.0)),
        "last_boot_ts": latest.get("ts", app.state.last_boot_ts),
    }


@app.get("/bios-ai/hardware")
async def bios_ai_hardware() -> dict[str, Any]:
    hw = await app.state.hw_profiler.profile()
    await app.state.db.save_hardware_snapshot(hw)
    return hw


@app.get("/bios-ai/boot-history")
async def bios_ai_boot_history() -> list[dict[str, Any]]:
    return await app.state.db.list_boot_history(limit=30)


@app.post("/bios-ai/repair/scan")
async def bios_ai_repair_scan() -> dict[str, str]:
    scan_id = str(uuid.uuid4())
    await app.state.db.create_scan(scan_id)

    task = asyncio.create_task(_run_scan(scan_id))
    app.state.scan_tasks[scan_id] = task

    return {"scan_id": scan_id, "status": "started"}


@app.get("/bios-ai/repair/scan/{scan_id}")
async def bios_ai_scan_status(scan_id: str) -> dict[str, Any]:
    scan = await app.state.db.get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="scan_id not found")

    items = await app.state.db.list_scan_items(scan_id)

    return {
        "scan_id": scan_id,
        "status": scan["status"],
        "issues_found": int(scan["issues_found"]),
        "issues_fixed": int(scan["issues_fixed"]),
        "issues_pending_approval": int(scan["issues_pending_approval"]),
        "items": [
            {
                "item_id": i["item_id"],
                "path": i["path"],
                "issue_type": i["issue_type"],
                "action": i["action"],
                "zone": i["zone"],
                "approved": i["approved"],
            }
            for i in items
        ],
    }


@app.post("/bios-ai/repair/approve/{item_id}")
async def bios_ai_repair_approve(item_id: str) -> dict[str, str]:
    try:
        result = await app.state.repair_engine.apply_approved(item_id, audit_url=AUDIT_LOG_URL)
    except KeyError:
        raise HTTPException(status_code=404, detail="item_id not found")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    return {"status": "applied", "path": result.path}


@app.post("/bios-ai/repair/reject/{item_id}")
async def bios_ai_repair_reject(item_id: str) -> dict[str, str]:
    try:
        await app.state.repair_engine.reject_item(item_id, audit_url=AUDIT_LOG_URL)
    except KeyError:
        raise HTTPException(status_code=404, detail="item_id not found")

    return {"status": "rejected"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}
