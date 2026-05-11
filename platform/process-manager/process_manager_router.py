"""Standalone FastAPI router for ProcessManager (no relative imports)."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the parent directory is in sys.path for absolute import
_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from process_manager import ProcessHandle, ProcessInfo, ProcessManager, WindowInfo  # type: ignore[import-not-found]

router = APIRouter(tags=["processes"])
_manager: Optional[ProcessManager] = None


def _mgr() -> ProcessManager:
    global _manager
    if _manager is None:
        _manager = ProcessManager()
    return _manager


class LaunchRequest(BaseModel):
    app_name: str
    args: List[str] = []


@router.post("/processes/launch")
async def launch_process(body: LaunchRequest) -> Dict[str, Any]:
    try:
        return _mgr().launch_app(body.app_name, body.args).to_dict()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/processes/list")
async def list_processes() -> Dict[str, Any]:
    return {"processes": [p.to_dict() for p in _mgr().list_processes()]}


@router.delete("/processes/{pid}")
async def kill_process(pid: int) -> Dict[str, Any]:
    try:
        return {"success": _mgr().kill_process(pid), "pid": pid}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/processes/windows")
async def get_windows() -> Dict[str, Any]:
    return {"windows": [w.to_dict() for w in _mgr().get_open_windows()]}
