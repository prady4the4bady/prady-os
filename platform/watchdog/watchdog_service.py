"""Kryos Watchdog Service — port 8115

Production-grade service health monitor.  Continuously polls all critical
platform services, detects unhealthy / degraded states, records incidents
in SQLite, triggers notifications, and exposes controlled recovery actions.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

_SHARED_PATH = Path(__file__).resolve().parents[1] / "shared"
if str(_SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(_SHARED_PATH))

from auth_middleware import require_auth

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "watchdog.db"

NOTIFICATION_BUS_URL = os.environ.get("NOTIFICATION_BUS_URL", "http://notification-bus:8111")

SECURITY_POLICY_URL = os.environ.get("SECURITY_POLICY_URL", "http://security-policy:8117")

OTA_SERVICE_URL = os.environ.get("OTA_SERVICE_URL")

POLL_INTERVAL_SECONDS = int(os.environ.get("WATCHDOG_POLL_INTERVAL", "15"))

# Consecutive-failure thresholds
DEGRADED_THRESHOLD = 2   # failures to enter degraded
DOWN_THRESHOLD = 4       # failures to enter down
LATENCY_DEGRADED_MS = 2000.0   # success at this latency → degraded

# ---------------------------------------------------------------------------
# Service registry
# ---------------------------------------------------------------------------


def _build_services() -> dict[str, str]:
    """Return mapping of service name → health-check URL from env vars."""
    base = {
        "agent-runtime":    os.environ.get("AGENT_RUNTIME_URL",    "http://agent-runtime:8100"),
        "notification-bus": os.environ.get("NOTIFICATION_BUS_URL", "http://notification-bus:8111"),
        "audit-log":        os.environ.get("AUDIT_LOG_URL",        "http://audit-log:8112"),
        "model-hub":        os.environ.get("MODEL_HUB_URL",        "http://model-hub:8113"),
        "persona-service":  os.environ.get("PERSONA_SERVICE_URL",  "http://persona-service:8114"),
        "task-scheduler":   os.environ.get("SCHEDULER_SERVICE_URL","http://task-scheduler:8110"),
        "memory-service":   os.environ.get("MEMORY_SERVICE_URL",   "http://memory-service:8108"),
        "voice-service":    os.environ.get("VOICE_SERVICE_URL",    "http://voice-service:8012"),
        "hardware-intel":   os.environ.get("HARDWARE_INTEL_URL",   "http://hardware-intel:8019"),
        "sdk-registry":     os.environ.get("SDK_REGISTRY_URL",     "http://sdk-registry:8020"),
    }
    return {name: f"{url}/health" for name, url in base.items()}


SERVICES: dict[str, str] = _build_services()

# Hardcoded allowlist: only these services may be restarted via this API.
RESTART_ALLOWLIST: dict[str, str] = {
    "agent-runtime":    "prax-agent-runtime.service",
    "notification-bus": "kryos-notification-bus.service",
    "audit-log":        "kryos-audit-log.service",
    "model-hub":        "kryos-model-hub.service",
    "persona-service":  "kryos-persona-service.service",
    "task-scheduler":   "kryos-task-scheduler.service",
    "memory-service":   "kryos-memory-service.service",
    "voice-service":    "kryos-voice-service.service",
    "hardware-intel":   "kryos-hardware-intel.service",
    "sdk-registry":     "kryos-sdk-registry.service",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("watchdog")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS service_status (
    name                TEXT PRIMARY KEY,
    status              TEXT NOT NULL DEFAULT 'unknown',
    last_check_at       TEXT,
    last_ok_at          TEXT,
    last_error          TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    latency_ms          REAL,
    check_count         INTEGER NOT NULL DEFAULT 0,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incidents (
    id           TEXT PRIMARY KEY,
    service_name TEXT NOT NULL,
    status       TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    resolved_at  TEXT,
    message      TEXT,
    created_at   TEXT NOT NULL
);
"""


async def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_DDL)
        await db.commit()


# ---------------------------------------------------------------------------
# Notification helper
# ---------------------------------------------------------------------------


async def _notify_incident(service_name: str, new_status: str, error_msg: str | None) -> None:
    severity = "error" if new_status == "down" else "warning"
    payload = {
        "type": "service_incident",
        "title": f"Service {new_status.upper()}: {service_name}",
        "body": error_msg or f"{service_name} entered {new_status} state",
        "source": "watchdog",
        "severity": severity,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response_or_awaitable = client.post(f"{NOTIFICATION_BUS_URL}/notify", json=payload)
            if inspect.isawaitable(response_or_awaitable):
                await response_or_awaitable
    except httpx.RequestError as exc:
        log.warning("Failed to send incident notification for %s: %s", service_name, exc)


async def _report_ota_health(success: bool, service: str) -> None:
    """Report boot/service health to OTA service. Fail-open by design."""
    if not OTA_SERVICE_URL:
        return
    payload = {"success": success, "service": service}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response_or_awaitable = client.post(f"{OTA_SERVICE_URL}/health-report", json=payload)
            if inspect.isawaitable(response_or_awaitable):
                await response_or_awaitable
    except Exception as exc:  # pragma: no cover
        log.warning("OTA health-report failed for %s: %s", service, exc)


# ---------------------------------------------------------------------------
# Core check logic
# ---------------------------------------------------------------------------


async def _policy_check(subject_type: str, subject_id: str, permission: str) -> tuple[bool, str]:
    """Check security policy. Fail-closed on error."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response_or_awaitable = client.post(
                f"{SECURITY_POLICY_URL}/policies/check",
                json={"subject_type": subject_type, "subject_id": subject_id, "permission": permission},
            )
            resp = (
                await response_or_awaitable
                if inspect.isawaitable(response_or_awaitable)
                else response_or_awaitable
            )
            data = resp.json()
            return bool(data.get("allowed", False)), str(data.get("reason", ""))
    except Exception as exc:
        return False, f"security-policy unavailable: {exc}"


def _compute_next_status(
    ok: bool,
    latency_ms: float | None,
    current_status: str,
    consecutive_failures: int,
) -> tuple[str, int]:
    if ok and latency_ms is not None and latency_ms > LATENCY_DEGRADED_MS:
        return "degraded", 0
    if ok:
        return "healthy", 0

    new_failures = consecutive_failures + 1
    if new_failures >= DOWN_THRESHOLD:
        return "down", new_failures
    if new_failures >= DEGRADED_THRESHOLD:
        return "degraded", new_failures
    if current_status in ("healthy", "unknown"):
        return "healthy", new_failures
    return current_status, new_failures


async def _insert_incident_if_needed(
    db: aiosqlite.Connection,
    *,
    name: str,
    current_status: str,
    new_status: str,
    now: str,
    error_msg: str | None,
) -> None:
    if current_status == new_status:
        return
    if new_status not in ("degraded", "down"):
        return

    incident_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO incidents "
        "(id, service_name, status, started_at, resolved_at, message, created_at) "
        "VALUES (?, ?, ?, ?, NULL, ?, ?)",
        (incident_id, name, new_status, now, error_msg or f"{name} entered {new_status} state", now),
    )
    await _notify_incident(name, new_status, error_msg)


async def _resolve_incidents_if_recovered(
    db: aiosqlite.Connection,
    *,
    name: str,
    current_status: str,
    new_status: str,
    now: str,
) -> None:
    if new_status != "healthy" or current_status not in ("degraded", "down"):
        return
    await db.execute(
        "UPDATE incidents SET resolved_at = ? "
        "WHERE service_name = ? AND resolved_at IS NULL",
        (now, name),
    )


async def _upsert_service_status(
    db: aiosqlite.Connection,
    *,
    row_exists: bool,
    name: str,
    new_status: str,
    now: str,
    ok: bool,
    error_msg: str | None,
    new_failures: int,
    latency_ms: float | None,
) -> None:
    if not row_exists:
        await db.execute(
            "INSERT INTO service_status "
            "(name, status, last_check_at, last_ok_at, last_error, "
            " consecutive_failures, latency_ms, check_count, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (name, new_status, now, now if ok else None, error_msg, new_failures, latency_ms, now),
        )
        return

    if ok:
        await db.execute(
            "UPDATE service_status SET "
            "status = ?, last_check_at = ?, last_ok_at = ?, last_error = NULL, "
            "consecutive_failures = 0, latency_ms = ?, check_count = check_count + 1, "
            "updated_at = ? WHERE name = ?",
            (new_status, now, now, latency_ms, now, name),
        )
        return

    await db.execute(
        "UPDATE service_status SET "
        "status = ?, last_check_at = ?, last_error = ?, "
        "consecutive_failures = ?, latency_ms = ?, check_count = check_count + 1, "
        "updated_at = ? WHERE name = ?",
        (new_status, now, error_msg, new_failures, latency_ms, now, name),
    )


async def _check_service(name: str, url: str) -> dict[str, Any]:
    """Check a single service, update DB, and return the updated status record."""
    await _init_db()

    start = time.monotonic()
    error_msg: str | None = None
    ok = False
    latency_ms: float | None = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
                response_or_awaitable = client.get(url)
                resp = (
                    await response_or_awaitable
                    if inspect.isawaitable(response_or_awaitable)
                    else response_or_awaitable
                )
        latency_ms = (time.monotonic() - start) * 1000.0
        ok = resp.status_code < 500
        if not ok:
            error_msg = f"HTTP {resp.status_code}"
    except httpx.RequestError as exc:
        latency_ms = (time.monotonic() - start) * 1000.0
        error_msg = str(exc)

    await _report_ota_health(ok, name)

    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT status, consecutive_failures, check_count FROM service_status WHERE name = ?",
            (name,),
        ) as cursor:
            row = await cursor.fetchone()

        current_status: str = row["status"] if row else "unknown"
        consecutive_failures: int = row["consecutive_failures"] if row else 0
        new_status, new_failures = _compute_next_status(ok, latency_ms, current_status, consecutive_failures)

        await _insert_incident_if_needed(
            db,
            name=name,
            current_status=current_status,
            new_status=new_status,
            now=now,
            error_msg=error_msg,
        )
        await _resolve_incidents_if_recovered(
            db,
            name=name,
            current_status=current_status,
            new_status=new_status,
            now=now,
        )
        await _upsert_service_status(
            db,
            row_exists=row is not None,
            name=name,
            new_status=new_status,
            now=now,
            ok=ok,
            error_msg=error_msg,
            new_failures=new_failures,
            latency_ms=latency_ms,
        )

        await db.commit()

        async with db.execute(
            "SELECT * FROM service_status WHERE name = ?", (name,)
        ) as cur:
            updated = await cur.fetchone()

    return dict(updated) if updated else {}


async def _scan_all() -> list[dict[str, Any]]:
    """Check all services and return results list (exceptions logged, not raised)."""
    import asyncio as _asyncio

    tasks = [_check_service(name, url) for name, url in SERVICES.items()]
    results = await _asyncio.gather(*tasks, return_exceptions=True)
    out: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, BaseException):
            log.error("Error during service scan: %s", r)
        else:
            out.append(r)  # type: ignore[arg-type]
    return out


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

_scheduler = AsyncIOScheduler()


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    await _init_db()
    _scheduler.add_job(_scan_all, "interval", seconds=POLL_INTERVAL_SECONDS, max_instances=1)
    _scheduler.start()
    try:
        yield
    finally:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)


app = FastAPI(title="Kryos Watchdog Service", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ServiceStatusResponse(BaseModel):
    name: str
    status: str
    last_check_at: str | None
    last_ok_at: str | None
    last_error: str | None
    consecutive_failures: int
    latency_ms: float | None
    check_count: int
    updated_at: str


class ServicesListResponse(BaseModel):
    services: list[ServiceStatusResponse]
    total: int


class IncidentResponse(BaseModel):
    id: str
    service_name: str
    status: str
    started_at: str
    resolved_at: str | None
    message: str | None
    created_at: str


class IncidentsListResponse(BaseModel):
    incidents: list[IncidentResponse]
    total: int
    limit: int
    offset: int


class IncidentsStatsResponse(BaseModel):
    total: int
    open: int
    resolved: int
    by_service: dict[str, int]
    by_status: dict[str, int]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_all_statuses() -> list[dict[str, Any]]:
    """Return status for every monitored service (including unchecked ones)."""
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM service_status ORDER BY name ASC"
        ) as cur:
            rows = await cur.fetchall()

    checked: dict[str, dict[str, Any]] = {r["name"]: dict(r) for r in rows}

    result: list[dict[str, Any]] = list(checked.values())

    # Append placeholder rows for services not yet checked
    now = datetime.now(timezone.utc).isoformat()
    for svc_name in SERVICES:
        if svc_name not in checked:
            result.append({
                "name": svc_name,
                "status": "unknown",
                "last_check_at": None,
                "last_ok_at": None,
                "last_error": None,
                "consecutive_failures": 0,
                "latency_ms": None,
                "check_count": 0,
                "updated_at": now,
            })

    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "watchdog", "port": 8115}


@app.get("/services", response_model=ServicesListResponse)
async def list_services() -> ServicesListResponse:
    statuses = await _get_all_statuses()
    return ServicesListResponse(
        services=[ServiceStatusResponse(**s) for s in statuses],
        total=len(statuses),
    )


@app.get("/services/{name}", response_model=ServiceStatusResponse)
async def get_service(name: str) -> ServiceStatusResponse:
    if name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {name!r} is not monitored")
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM service_status WHERE name = ?", (name,)
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        now = datetime.now(timezone.utc).isoformat()
        return ServiceStatusResponse(
            name=name, status="unknown", last_check_at=None, last_ok_at=None,
            last_error=None, consecutive_failures=0, latency_ms=None,
            check_count=0, updated_at=now,
        )
    return ServiceStatusResponse(**dict(row))


@app.post("/services/{name}/check", response_model=ServiceStatusResponse)
async def force_check(name: str) -> ServiceStatusResponse:
    if name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {name!r} is not monitored")
    result = await _check_service(name, SERVICES[name])
    return ServiceStatusResponse(**result)


@app.post("/services/{name}/restart")
async def restart_service(
    name: str,
    current_user: dict[str, Any] = Depends(require_auth),
) -> JSONResponse:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="insufficient permissions")
    if name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {name!r} is not monitored")
    unit = RESTART_ALLOWLIST.get(name)
    if not unit:
        raise HTTPException(status_code=403, detail=f"Service {name!r} is not in the restart allowlist")
    policy_result = _policy_check("service", name, "service-restart")
    allowed, reason = (
        await policy_result if inspect.isawaitable(policy_result) else policy_result
    )
    if not allowed:
        raise HTTPException(status_code=403, detail=f"policy denied service-restart: {reason}")
    try:
        process = await asyncio.to_thread(
            subprocess.run,
            ["systemctl", "restart", unit],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if process.returncode == 0:
            return JSONResponse(
                content={"ok": True, "service": name, "unit": unit, "message": "restart command sent"}
            )
        return JSONResponse(
            status_code=500,
            content={
                "ok": False, "service": name, "unit": unit,
                "error": process.stderr or process.stdout or "systemctl returned non-zero",
            },
        )
    except FileNotFoundError:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False, "service": name, "unit": unit,
                "error": "systemctl not available (non-systemd environment)",
            },
        )
    except TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"ok": False, "service": name, "unit": unit, "error": "restart timed out"},
        )


@app.get("/incidents", response_model=IncidentsListResponse)
async def list_incidents(
    limit: int = 50,
    offset: int = 0,
    service: str | None = None,
) -> IncidentsListResponse:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if service:
            async with db.execute(
                "SELECT COUNT(*) FROM incidents WHERE service_name = ?", (service,)
            ) as cur:
                total: int = (await cur.fetchone())[0]
            async with db.execute(
                "SELECT * FROM incidents WHERE service_name = ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (service, limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute("SELECT COUNT(*) FROM incidents") as cur:
                total = (await cur.fetchone())[0]
            async with db.execute(
                "SELECT * FROM incidents ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ) as cur:
                rows = await cur.fetchall()

    return IncidentsListResponse(
        incidents=[IncidentResponse(**dict(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/incidents/stats", response_model=IncidentsStatsResponse)
async def incidents_stats() -> IncidentsStatsResponse:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT COUNT(*) FROM incidents") as cur:
            total: int = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM incidents WHERE resolved_at IS NULL"
        ) as cur:
            open_count: int = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM incidents WHERE resolved_at IS NOT NULL"
        ) as cur:
            resolved_count: int = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT service_name, COUNT(*) AS cnt FROM incidents GROUP BY service_name"
        ) as cur:
            by_service = {r["service_name"]: r["cnt"] for r in await cur.fetchall()}
        async with db.execute(
            "SELECT status, COUNT(*) AS cnt FROM incidents GROUP BY status"
        ) as cur:
            by_status = {r["status"]: r["cnt"] for r in await cur.fetchall()}

    return IncidentsStatsResponse(
        total=total,
        open=open_count,
        resolved=resolved_count,
        by_service=by_service,
        by_status=by_status,
    )


@app.post("/scan")
async def scan_all_services() -> dict[str, Any]:
    results = await _scan_all()
    return {"scanned": len(results), "services": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8115)
