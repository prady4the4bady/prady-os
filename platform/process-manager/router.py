"""FastAPI router for ProcessManager — exposes process and window management."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .process_manager import ProcessHandle, ProcessInfo, ProcessManager, WindowInfo

router = APIRouter(tags=["processes"])
_manager: Optional[ProcessManager] = None


def get_manager() -> ProcessManager:
    global _manager
    if _manager is None:
        _manager = ProcessManager()
    return _manager


class LaunchRequest(BaseModel):
    app_name: str
    args: List[str] = []


class ProcessListResponse(BaseModel):
    processes: List[Dict[str, Any]]


class WindowListResponse(BaseModel):
    windows: List[Dict[str, Any]]


@router.post("/processes/launch")
async def launch_process(body: LaunchRequest) -> Dict[str, Any]:
    """Launch a registered application."""
    mgr = get_manager()
    try:
        handle = mgr.launch_app(body.app_name, body.args)
        return handle.to_dict()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/processes/list")
async def list_processes() -> ProcessListResponse:
    """List running processes sorted by CPU usage."""
    mgr = get_manager()
    return ProcessListResponse(processes=[p.to_dict() for p in mgr.list_processes()])


@router.delete("/processes/{pid}")
async def kill_process(pid: int) -> Dict[str, Any]:
    """Terminate a process by PID."""
    mgr = get_manager()
    try:
        ok = mgr.kill_process(pid)
        return {"success": ok, "pid": pid}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/processes/windows")
async def get_windows() -> WindowListResponse:
    """List open desktop windows."""
    mgr = get_manager()
    return WindowListResponse(windows=[w.to_dict() for w in mgr.get_open_windows()])
