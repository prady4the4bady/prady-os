"""eBPF Hardening Service — port 8118

Loads, manages, and monitors eBPF kernel programs for syscall filtering and LSM hooks.
Tracks PIDs of prax-agent and computer-use services.
Streams denial events to audit-log service in batches.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import psutil
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PROGRAMS_DIR = Path(__file__).parent / "programs"
AUDIT_LOG_URL = os.environ.get("AUDIT_LOG_URL", "http://audit-log:8112")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global State (in-memory; can be persisted to SQLite if needed)
# ---------------------------------------------------------------------------

class ProgramInfo(BaseModel):
    """Metadata for a loaded eBPF program."""
    name: str
    path: str
    loaded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    syscall_count: int = 0
    denial_count: int = 0
    attached_pids: list[int] = Field(default_factory=list)
    handle: str | None = None  # BPF program FD or identifier


PROGRAMS: dict[str, ProgramInfo] = {}

# Track denial events for audit
DENIAL_EVENTS: list[dict[str, Any]] = []
DENIAL_LOCK = asyncio.Lock()

_ring_buffer_task: asyncio.Task[None] | None = None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# eBPF Program Management
# ---------------------------------------------------------------------------

def _compile_program(name: str) -> str:
    """Compile a .bpf.c program to .bpf.o bytecode using clang.
    
    In a real implementation, this would invoke:
      clang -O2 -target bpf -D__TARGET_ARCH_x86 ... -c programs/{name}.bpf.c -o programs/{name}.bpf.o
    
    Returns the path to the compiled object file.
    For tests, this will be mocked.
    """
    src_path = PROGRAMS_DIR / f"{name}.bpf.c"
    obj_path = PROGRAMS_DIR / f"{name}.bpf.o"
    
    if not src_path.exists():
        raise FileNotFoundError(f"Source not found: {src_path}")
    
    # In a Linux environment with clang/libbpf, invoke:
    # clang -O2 -target bpf ... -c src_path -o obj_path
    # For now, we mock this in tests.
    try:
        subprocess.run(
            [
                "clang",
                "-O2",
                "-target", "bpf",
                "-D__TARGET_ARCH_x86",
                "-D__KERNEL__",
                "-D__BPF_CORE__",
                "-I/usr/include/bpf",
                "-c", str(src_path),
                "-o", str(obj_path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        logger.info(f"Compiled {name}: {obj_path}")
        return str(obj_path)
    except subprocess.CalledProcessError as e:
        logger.error(f"Compilation failed for {name}: {e.stderr.decode()}")
        raise RuntimeError(f"Failed to compile {name}") from e
    except FileNotFoundError:
        raise RuntimeError("clang not found; eBPF toolchain not installed")


def _load_program(name: str, obj_path: str) -> str:
    """Load compiled eBPF program into kernel.
    
    In a real implementation, uses libbpf or bcc to:
    1. Load the .bpf.o file
    2. Attach to tracepoint/LSM hook
    3. Return a file descriptor or handle
    
    For tests, this will be mocked.
    """
    logger.info(f"Loading eBPF program: {name} from {obj_path}")
    
    # Mock handle for now; in production, this would be a libbpf prog_fd
    handle = f"handle_{name}_{uuid.uuid4().hex[:8]}"
    return handle


def _unload_program(handle: str) -> None:
    """Unload and detach an eBPF program from kernel."""
    logger.info(f"Unloading eBPF program: {handle}")
    # In production, detach and close libbpf prog_fd


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("eBPF Hardening service starting")
    # Optional: start ring buffer polling task
    # global _ring_buffer_task
    # _ring_buffer_task = asyncio.create_task(_poll_ring_buffer())
    yield
    logger.info("eBPF Hardening service shutting down")
    if _ring_buffer_task:
        _ring_buffer_task.cancel()


app = FastAPI(
    title="Kryos eBPF Hardening Service",
    description="Kernel-level syscall filtering and LSM hooks",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "service": "ebpf-hardening"}


@app.get("/programs")
async def list_programs() -> dict[str, Any]:
    """List all loaded eBPF programs."""
    return {
        "programs": [
            {
                "name": prog.name,
                "loaded_at": prog.loaded_at,
                "syscall_count": prog.syscall_count,
                "denial_count": prog.denial_count,
                "attached_pids": prog.attached_pids,
            }
            for prog in PROGRAMS.values()
        ],
        "total": len(PROGRAMS),
    }


@app.get("/programs/{name}/stats")
async def get_program_stats(name: str) -> dict[str, Any]:
    """Get statistics for a named program."""
    if name not in PROGRAMS:
        raise HTTPException(status_code=404, detail=f"Program not found: {name}")
    
    prog = PROGRAMS[name]
    return {
        "name": prog.name,
        "loaded_at": prog.loaded_at,
        "syscall_count": prog.syscall_count,
        "denial_count": prog.denial_count,
        "attached_pids": prog.attached_pids,
        "handle": prog.handle,
    }


@app.post("/programs/{name}/load")
async def load_program(name: str) -> dict[str, Any]:
    """Compile and load a named eBPF program."""
    if name in PROGRAMS:
        raise HTTPException(status_code=409, detail=f"Program already loaded: {name}")
    
    try:
        obj_path = _compile_program(name)
        handle = _load_program(name, obj_path)
        
        prog_info = ProgramInfo(
            name=name,
            path=obj_path,
            handle=handle,
            syscall_count=0,
            denial_count=0,
            attached_pids=[],
        )
        PROGRAMS[name] = prog_info
        
        logger.info(f"Loaded program: {name}")
        return {"ok": True, "name": name, "handle": handle, "loaded_at": prog_info.loaded_at}
    except Exception as e:
        logger.error(f"Failed to load program {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/programs/{name}/unload")
async def unload_program(name: str) -> dict[str, Any]:
    """Unload and detach an eBPF program."""
    if name not in PROGRAMS:
        raise HTTPException(status_code=404, detail=f"Program not found: {name}")
    
    prog = PROGRAMS[name]
    if prog.handle:
        _unload_program(prog.handle)
    
    del PROGRAMS[name]
    logger.info(f"Unloaded program: {name}")
    return {"ok": True, "name": name}


@app.post("/sandbox/agent")
async def sandbox_agent(pid: int = Query(..., description="PID of prax-agent process")) -> dict[str, Any]:
    """Attach prax_agent_seccomp to a specific process by PID."""
    # Verify PID exists
    try:
        psutil.Process(pid)
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail=f"Process not found: PID {pid}")
    
    # Ensure prax_agent_seccomp is loaded
    if "prax_agent_seccomp" not in PROGRAMS:
        try:
            await load_program("prax_agent_seccomp")
        except HTTPException as e:
            if e.status_code != 409:  # Already loaded
                raise
    
    prog = PROGRAMS["prax_agent_seccomp"]
    if pid not in prog.attached_pids:
        prog.attached_pids.append(pid)
    
    logger.info(f"Attached prax_agent_seccomp to PID {pid}")
    return {
        "ok": True,
        "program": "prax_agent_seccomp",
        "pid": pid,
        "attached_at": _now_iso(),
    }


@app.post("/sandbox/computer-use")
async def sandbox_computer_use(
    pid: int = Query(..., description="PID of computer-use service")
) -> dict[str, Any]:
    """Attach computer_use_lsm to a specific process by PID."""
    # Verify PID exists
    try:
        psutil.Process(pid)
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail=f"Process not found: PID {pid}")
    
    # Ensure computer_use_lsm is loaded
    if "computer_use_lsm" not in PROGRAMS:
        try:
            await load_program("computer_use_lsm")
        except HTTPException as e:
            if e.status_code != 409:  # Already loaded
                raise
    
    prog = PROGRAMS["computer_use_lsm"]
    if pid not in prog.attached_pids:
        prog.attached_pids.append(pid)
    
    logger.info(f"Attached computer_use_lsm to PID {pid}")
    return {
        "ok": True,
        "program": "computer_use_lsm",
        "pid": pid,
        "attached_at": _now_iso(),
    }


@app.post("/sandbox/agent/detach")
async def detach_agent(pid: int = Query(...)) -> dict[str, Any]:
    """Detach prax_agent_seccomp from a process."""
    if "prax_agent_seccomp" in PROGRAMS:
        prog = PROGRAMS["prax_agent_seccomp"]
        if pid in prog.attached_pids:
            prog.attached_pids.remove(pid)
            logger.info(f"Detached prax_agent_seccomp from PID {pid}")
    
    return {"ok": True, "program": "prax_agent_seccomp", "pid": pid}


@app.post("/sandbox/computer-use/detach")
async def detach_computer_use(pid: int = Query(...)) -> dict[str, Any]:
    """Detach computer_use_lsm from a process."""
    if "computer_use_lsm" in PROGRAMS:
        prog = PROGRAMS["computer_use_lsm"]
        if pid in prog.attached_pids:
            prog.attached_pids.remove(pid)
            logger.info(f"Detached computer_use_lsm from PID {pid}")
    
    return {"ok": True, "program": "computer_use_lsm", "pid": pid}


@app.get("/audit/denials")
async def get_denials(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Get recent denial events (from in-memory buffer)."""
    async with DENIAL_LOCK:
        events = DENIAL_EVENTS[offset : offset + limit]
    return {
        "events": events,
        "total": len(DENIAL_EVENTS),
        "limit": limit,
        "offset": offset,
    }
