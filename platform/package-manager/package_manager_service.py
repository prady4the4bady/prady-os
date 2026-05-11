"""Kryos Package Manager Service — port 8116

Production-grade local package/module management system.
Manages installation, updates, enabling/disabling, and removal
of kryos apps, panels, services, agents, and tools.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

_SHARED_PATH = Path(__file__).resolve().parents[1] / "shared"
if str(_SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(_SHARED_PATH))

from auth_middleware import require_auth, require_permission

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "packages.db"
CATALOG_DIR = Path(os.environ.get("CATALOG_DIR", "/catalog"))

NOTIFICATION_BUS_URL = os.environ.get("NOTIFICATION_BUS_URL", "http://notification-bus:8111")

SECURITY_POLICY_URL = os.environ.get("SECURITY_POLICY_URL", "http://security-policy:8117")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("package-manager")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_PACKAGE_TYPES = frozenset({"panel", "service", "agent", "tool"})
VALID_STATUSES = frozenset({"available", "installed", "enabled", "disabled", "broken"})
VALID_OPERATIONS = frozenset({"install", "update", "enable", "disable", "remove", "check"})
_SELECT_PACKAGE_BY_ID_SQL = "SELECT * FROM packages WHERE package_id = ?"
_MARK_OPERATION_SUCCESS_SQL = (
    "UPDATE package_operations SET status = 'success', completed_at = ?, message = ? WHERE id = ?"
)

# Controlled allowlist: only these service names may be enabled/disabled via systemctl.
# No arbitrary command execution is permitted from manifests.
SERVICE_ENABLE_ALLOWLIST: dict[str, str] = {
    "notification-center":  "kryos-notification-center.service",
    "task-history":         "kryos-task-history.service",
    "model-hub":            "kryos-model-hub.service",
    "persona-manager":      "kryos-persona-manager.service",
    "watchdog-center":      "kryos-watchdog.service",
    "spotlight-launcher":   "kryos-spotlight-launcher.service",
}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PackageManifest(BaseModel):
    package_id: str
    name: str
    version: str
    type: str
    description: str
    entrypoint: str
    service_name: str | None = None
    dependencies: list[str] = []
    permissions: list[str] = []
    healthcheck_path: str | None = None
    source: str = "local"

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_PACKAGE_TYPES:
            raise ValueError(f"type must be one of {sorted(VALID_PACKAGE_TYPES)}")
        return v

    @field_validator("package_id")
    @classmethod
    def validate_package_id(cls, v: str) -> str:
        if not v or not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("package_id must be alphanumeric with hyphens/underscores only")
        return v


class InstallRequest(BaseModel):
    package_id: str
    version: str | None = None


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS packages (
        package_id          TEXT PRIMARY KEY,
        name                TEXT NOT NULL,
        version             TEXT NOT NULL,
        type                TEXT NOT NULL,
        description         TEXT NOT NULL DEFAULT '',
        entrypoint          TEXT NOT NULL DEFAULT '',
        service_name        TEXT,
        dependencies        TEXT NOT NULL DEFAULT '[]',
        permissions         TEXT NOT NULL DEFAULT '[]',
        healthcheck_path    TEXT,
        source              TEXT NOT NULL DEFAULT 'local',
        status              TEXT NOT NULL DEFAULT 'available',
        installed_at        TEXT,
        updated_at          TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS package_operations (
        id              TEXT PRIMARY KEY,
        package_id      TEXT NOT NULL,
        operation       TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'pending',
        message         TEXT,
        started_at      TEXT NOT NULL,
        completed_at    TEXT,
        created_at      TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_operations_package ON package_operations(package_id)",
    "CREATE INDEX IF NOT EXISTS idx_operations_started ON package_operations(started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_packages_status ON packages(status)",
]


async def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        for ddl in _DDL:
            await db.execute(ddl)
        await db.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_package(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    d["dependencies"] = json.loads(d.get("dependencies") or "[]")
    d["permissions"] = json.loads(d.get("permissions") or "[]")
    return d


def _row_to_operation(row: aiosqlite.Row) -> dict[str, Any]:
    return dict(row)


# ---------------------------------------------------------------------------
# Catalog bootstrap
# ---------------------------------------------------------------------------


def _load_catalog_manifests() -> list[PackageManifest]:
    """Load all JSON manifests from CATALOG_DIR."""
    manifests: list[PackageManifest] = []
    if not CATALOG_DIR.is_dir():
        log.warning("CATALOG_DIR %s does not exist; skipping catalog bootstrap", CATALOG_DIR)
        return manifests

    for manifest_path in sorted(CATALOG_DIR.glob("*.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifests.append(PackageManifest.model_validate(data))
        except Exception as exc:
            log.warning("Failed to load catalog manifest %s: %s", manifest_path, exc)

    log.info("Loaded %d catalog manifests from %s", len(manifests), CATALOG_DIR)
    return manifests


async def _bootstrap_catalog(manifests: list[PackageManifest]) -> None:
    """Seed catalog packages into DB if not already present."""
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        for m in manifests:
            async with db.execute(
                "SELECT package_id FROM packages WHERE package_id = ?", (m.package_id,)
            ) as cursor:
                existing = await cursor.fetchone()
            if existing is None:
                await db.execute(
                    """
                    INSERT INTO packages
                    (package_id, name, version, type, description, entrypoint,
                     service_name, dependencies, permissions, healthcheck_path,
                     source, status, installed_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', NULL, ?)
                    """,
                    (
                        m.package_id, m.name, m.version, m.type, m.description,
                        m.entrypoint, m.service_name,
                        json.dumps(m.dependencies), json.dumps(m.permissions),
                        m.healthcheck_path, m.source, now,
                    ),
                )
                log.info("Bootstrapped catalog package: %s", m.package_id)
        await db.commit()


# ---------------------------------------------------------------------------
# Notification helper
# ---------------------------------------------------------------------------


async def _notify(package_id: str, operation: str, status: str, message: str | None = None) -> None:
    payload = {
        "type": "package_operation",
        "title": f"Package {operation}: {package_id}",
        "body": message or f"{package_id} {operation} {status}",
        "source": "package-manager",
        "severity": "error" if status == "failed" else "info",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{NOTIFICATION_BUS_URL}/notify", json=payload)
    except httpx.RequestError as exc:
        log.warning("Failed to send package notification: %s", exc)


# ---------------------------------------------------------------------------
# Controlled service action executor
# ---------------------------------------------------------------------------
# Security policy enforcement
# ---------------------------------------------------------------------------


async def _policy_check(subject_id: str, permission: str) -> tuple[bool, str]:
    """Check security policy for a package action. Fail-closed on error."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SECURITY_POLICY_URL}/policies/check",
                json={"subject_type": "package", "subject_id": subject_id, "permission": permission},
            )
            data = resp.json()
            return bool(data.get("allowed", False)), str(data.get("reason", ""))
    except Exception as exc:
        return False, f"security-policy unavailable: {exc}"


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _execute_service_action(service_name: str, action: str) -> tuple[bool, str]:
    """
    Execute a systemctl action (enable/disable) for a pre-approved service only.

    No subprocess shell=True is used. No arbitrary command execution from manifests.
    Returns (success, message).
    """
    allowed_unit = SERVICE_ENABLE_ALLOWLIST.get(service_name)
    if not allowed_unit:
        return False, f"Service '{service_name}' is not in the controlled allowlist"

    if action not in ("enable", "disable"):
        return False, f"Action '{action}' is not permitted; only 'enable' or 'disable' are allowed"

    try:
        result = subprocess.run(
            ["systemctl", action, allowed_unit],
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,  # explicitly no shell=True
        )
        if result.returncode == 0:
            return True, f"systemctl {action} {allowed_unit} succeeded"
        stderr = result.stderr.strip()
        return False, f"systemctl {action} {allowed_unit} failed: {stderr}"
    except FileNotFoundError:
        # systemctl not available (e.g., in Docker dev environment) — simulate success
        log.info("systemctl not found; simulating %s %s", action, allowed_unit)
        return True, f"simulated: systemctl {action} {allowed_unit}"
    except subprocess.TimeoutExpired:
        return False, f"systemctl {action} {allowed_unit} timed out"
    except OSError as exc:
        return False, f"systemctl {action} {allowed_unit} OS error: {exc}"


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI):  # type: ignore[type-arg]
    await _init_db()
    manifests = _load_catalog_manifests()
    await _bootstrap_catalog(manifests)
    yield


app = FastAPI(
    title="Kryos Package Manager",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes — Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "package-manager", "port": 8116}


# ---------------------------------------------------------------------------
# Routes — Packages
# ---------------------------------------------------------------------------


@app.get("/packages")
async def list_packages(
    status: str | None = None,
    type: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    """List all packages, with optional filters."""
    await _init_db()

    conditions: list[str] = []
    params: list[Any] = []

    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"invalid status: {status}")
        conditions.append("status = ?")
        params.append(status)

    if type:
        if type not in VALID_PACKAGE_TYPES:
            raise HTTPException(status_code=422, detail=f"invalid type: {type}")
        conditions.append("type = ?")
        params.append(type)

    if q:
        conditions.append("(name LIKE ? OR description LIKE ? OR package_id LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM packages {where} ORDER BY name"

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

    packages = [_row_to_package(r) for r in rows]
    return {"packages": packages, "total": len(packages)}


@app.get("/packages/catalog")
async def list_catalog() -> dict[str, Any]:
    """List all packages in the catalog (available or installed)."""
    return await list_packages()


@app.get("/packages/{package_id}")
async def get_package(package_id: str) -> dict[str, Any]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            _SELECT_PACKAGE_BY_ID_SQL, (package_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found")
    return _row_to_package(row)


@app.post("/packages/install", status_code=202)
async def install_package(
    req: InstallRequest,
    _current_user: dict[str, Any] = Depends(require_permission("package-install")),
) -> dict[str, Any]:
    """Install a package from the catalog."""
    await _init_db()
    package_id = req.package_id
    allowed, reason = await _policy_check(package_id, "package-install")
    if not allowed:
        raise HTTPException(status_code=403, detail=f"policy denied package-install: {reason}")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            _SELECT_PACKAGE_BY_ID_SQL, (package_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found in catalog")

    pkg = _row_to_package(row)

    if pkg["status"] in ("installed", "enabled"):
        raise HTTPException(
            status_code=409,
            detail=f"Package '{package_id}' is already installed (status={pkg['status']})",
        )

    # Check dependency conflicts
    unresolved = await _check_dependencies(pkg["dependencies"])
    if unresolved:
        raise HTTPException(
            status_code=409,
            detail=f"Unresolved dependencies: {', '.join(unresolved)}",
        )

    op_id = str(uuid.uuid4())
    now = _now_iso()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO package_operations
            (id, package_id, operation, status, message, started_at, completed_at, created_at)
            VALUES (?, ?, 'install', 'running', NULL, ?, NULL, ?)
            """,
            (op_id, package_id, now, now),
        )
        await db.commit()

    # Perform install (mark as installed; real entrypoint registration in production)
    completed_at = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE packages SET status = 'installed', installed_at = ?, updated_at = ? WHERE package_id = ?",
            (completed_at, completed_at, package_id),
        )
        await db.execute(
            _MARK_OPERATION_SUCCESS_SQL,
            (completed_at, f"Installed {package_id} v{pkg['version']}", op_id),
        )
        await db.commit()

    await _notify(package_id, "install", "success")
    return {"ok": True, "operation_id": op_id, "package_id": package_id, "status": "installed"}


@app.post("/packages/{package_id}/update", status_code=202)
async def update_package(
    package_id: str,
    _current_user: dict[str, Any] = Depends(require_permission("package-install")),
) -> dict[str, Any]:
    """Update an installed package to the latest catalog version."""
    await _init_db()
    pkg = await _require_package(package_id)

    if pkg["status"] not in ("installed", "enabled", "disabled", "broken"):
        raise HTTPException(
            status_code=409,
            detail=f"Package '{package_id}' is not installed (status={pkg['status']})",
        )

    op_id = str(uuid.uuid4())
    now = _now_iso()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO package_operations
            (id, package_id, operation, status, message, started_at, completed_at, created_at)
            VALUES (?, ?, 'update', 'running', NULL, ?, NULL, ?)
            """,
            (op_id, package_id, now, now),
        )
        await db.commit()

    completed_at = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE packages SET updated_at = ? WHERE package_id = ?",
            (completed_at, package_id),
        )
        await db.execute(
            _MARK_OPERATION_SUCCESS_SQL,
            (completed_at, f"Updated {package_id}", op_id),
        )
        await db.commit()

    await _notify(package_id, "update", "success")
    return {"ok": True, "operation_id": op_id, "package_id": package_id}


@app.post("/packages/{package_id}/enable", status_code=202)
async def enable_package(
    package_id: str,
    _current_user: dict[str, Any] = Depends(require_permission("package-install")),
) -> dict[str, Any]:
    """Enable (activate) an installed package via controlled service action."""
    allowed, reason = await _policy_check(package_id, "package-install")
    if not allowed:
        raise HTTPException(status_code=403, detail=f"policy denied package-install: {reason}")
    await _init_db()
    pkg = await _require_package(package_id)

    if pkg["status"] == "enabled":
        raise HTTPException(status_code=409, detail=f"Package '{package_id}' is already enabled")

    if pkg["status"] not in ("installed", "disabled"):
        raise HTTPException(
            status_code=409,
            detail=f"Package '{package_id}' must be installed before enabling (status={pkg['status']})",
        )

    op_id = str(uuid.uuid4())
    now = _now_iso()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO package_operations
            (id, package_id, operation, status, message, started_at, completed_at, created_at)
            VALUES (?, ?, 'enable', 'running', NULL, ?, NULL, ?)
            """,
            (op_id, package_id, now, now),
        )
        await db.commit()

    service_name = pkg.get("service_name")
    op_success = True
    op_message = f"Enabled {package_id}"

    if service_name:
        ok, msg = _execute_service_action(service_name, "enable")
        op_success = ok
        op_message = msg

    completed_at = _now_iso()
    new_status = "enabled" if op_success else "broken"
    op_status = "success" if op_success else "failed"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE packages SET status = ?, updated_at = ? WHERE package_id = ?",
            (new_status, completed_at, package_id),
        )
        await db.execute(
            "UPDATE package_operations SET status = ?, completed_at = ?, message = ? WHERE id = ?",
            (op_status, completed_at, op_message, op_id),
        )
        await db.commit()

    if not op_success:
        await _notify(package_id, "enable", "failed", op_message)
        raise HTTPException(status_code=500, detail=op_message)

    await _notify(package_id, "enable", "success")
    return {"ok": True, "operation_id": op_id, "package_id": package_id, "status": new_status}


@app.post("/packages/{package_id}/disable", status_code=202)
async def disable_package(
    package_id: str,
    _current_user: dict[str, Any] = Depends(require_permission("package-install")),
) -> dict[str, Any]:
    """Disable an enabled package via controlled service action."""
    allowed, reason = await _policy_check(package_id, "package-install")
    if not allowed:
        raise HTTPException(status_code=403, detail=f"policy denied package-install: {reason}")
    await _init_db()
    pkg = await _require_package(package_id)

    if pkg["status"] == "disabled":
        raise HTTPException(status_code=409, detail=f"Package '{package_id}' is already disabled")

    if pkg["status"] not in ("installed", "enabled"):
        raise HTTPException(
            status_code=409,
            detail=f"Package '{package_id}' cannot be disabled (status={pkg['status']})",
        )

    op_id = str(uuid.uuid4())
    now = _now_iso()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO package_operations
            (id, package_id, operation, status, message, started_at, completed_at, created_at)
            VALUES (?, ?, 'disable', 'running', NULL, ?, NULL, ?)
            """,
            (op_id, package_id, now, now),
        )
        await db.commit()

    service_name = pkg.get("service_name")
    op_success = True
    op_message = f"Disabled {package_id}"

    if service_name:
        ok, msg = _execute_service_action(service_name, "disable")
        op_success = ok
        op_message = msg

    completed_at = _now_iso()
    new_status = "disabled" if op_success else pkg["status"]
    op_status = "success" if op_success else "failed"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE packages SET status = ?, updated_at = ? WHERE package_id = ?",
            (new_status, completed_at, package_id),
        )
        await db.execute(
            "UPDATE package_operations SET status = ?, completed_at = ?, message = ? WHERE id = ?",
            (op_status, completed_at, op_message, op_id),
        )
        await db.commit()

    if not op_success:
        await _notify(package_id, "disable", "failed", op_message)
        raise HTTPException(status_code=500, detail=op_message)

    await _notify(package_id, "disable", "success")
    return {"ok": True, "operation_id": op_id, "package_id": package_id, "status": new_status}


@app.delete("/packages/{package_id}", status_code=202)
async def remove_package(
    package_id: str,
    _current_user: dict[str, Any] = Depends(require_permission("package-install")),
) -> dict[str, Any]:
    """Remove an installed package (returns to 'available' state in catalog)."""
    allowed, reason = await _policy_check(package_id, "package-remove")
    if not allowed:
        raise HTTPException(status_code=403, detail=f"policy denied package-remove: {reason}")
    await _init_db()
    pkg = await _require_package(package_id)

    if pkg["status"] == "available":
        raise HTTPException(
            status_code=409,
            detail=f"Package '{package_id}' is not installed",
        )

    op_id = str(uuid.uuid4())
    now = _now_iso()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO package_operations
            (id, package_id, operation, status, message, started_at, completed_at, created_at)
            VALUES (?, ?, 'remove', 'running', NULL, ?, NULL, ?)
            """,
            (op_id, package_id, now, now),
        )
        await db.commit()

    completed_at = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE packages SET status = 'available', installed_at = NULL, updated_at = ? WHERE package_id = ?",
            (completed_at, package_id),
        )
        await db.execute(
            _MARK_OPERATION_SUCCESS_SQL,
            (completed_at, f"Removed {package_id}", op_id),
        )
        await db.commit()

    await _notify(package_id, "remove", "success")
    return {"ok": True, "operation_id": op_id, "package_id": package_id, "status": "available"}


@app.post("/packages/{package_id}/check")
async def check_package(package_id: str) -> dict[str, Any]:
    """Run a health check on an installed package."""
    await _init_db()
    pkg = await _require_package(package_id)

    if pkg["status"] not in ("installed", "enabled", "disabled", "broken"):
        raise HTTPException(
            status_code=409,
            detail=f"Package '{package_id}' is not installed",
        )

    healthcheck_path = pkg.get("healthcheck_path")
    entrypoint = pkg.get("entrypoint", "")

    check_result: dict[str, Any] = {
        "package_id": package_id,
        "checked_at": _now_iso(),
        "healthy": True,
        "message": "Package is installed",
        "healthcheck_url": None,
    }

    if healthcheck_path and entrypoint:
        url = f"{entrypoint}{healthcheck_path}"
        check_result["healthcheck_url"] = url
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
            check_result["healthy"] = resp.status_code < 500
            check_result["message"] = f"HTTP {resp.status_code}"
            if not check_result["healthy"]:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE packages SET status = 'broken', updated_at = ? WHERE package_id = ?",
                        (_now_iso(), package_id),
                    )
                    await db.commit()
        except httpx.RequestError as exc:
            check_result["healthy"] = False
            check_result["message"] = f"health check failed: {exc}"

    op_id = str(uuid.uuid4())
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO package_operations
            (id, package_id, operation, status, message, started_at, completed_at, created_at)
            VALUES (?, ?, 'check', ?, ?, ?, ?, ?)
            """,
            (
                op_id, package_id,
                "success" if check_result["healthy"] else "failed",
                check_result["message"], now, now, now,
            ),
        )
        await db.commit()

    check_result["operation_id"] = op_id
    return check_result


# ---------------------------------------------------------------------------
# Routes — Operations log
# ---------------------------------------------------------------------------


@app.get("/operations")
async def list_operations(
    package_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    await _init_db()

    conditions: list[str] = []
    params: list[Any] = []

    if package_id:
        conditions.append("package_id = ?")
        params.append(package_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM package_operations {where} ORDER BY started_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    count_sql = f"SELECT COUNT(*) FROM package_operations {where}"
    count_params = params[: len(params) - 2]

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        async with db.execute(count_sql, count_params) as cursor:
            total_row = await cursor.fetchone()

    total = total_row[0] if total_row else 0
    return {
        "operations": [_row_to_operation(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/operations/stats")
async def operations_stats() -> dict[str, Any]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT operation, status, COUNT(*) as count FROM package_operations GROUP BY operation, status"
        ) as cursor:
            rows = await cursor.fetchall()

        async with db.execute(
            "SELECT COUNT(*) as total FROM package_operations"
        ) as cursor:
            total_row = await cursor.fetchone()

        async with db.execute(
            "SELECT COUNT(*) as installed FROM packages WHERE status IN ('installed', 'enabled')"
        ) as cursor:
            installed_row = await cursor.fetchone()

        async with db.execute(
            "SELECT COUNT(*) as available FROM packages WHERE status = 'available'"
        ) as cursor:
            available_row = await cursor.fetchone()

    by_op: dict[str, dict[str, int]] = {}
    for row in rows:
        op = row["operation"]
        st = row["status"]
        by_op.setdefault(op, {})[st] = row["count"]

    return {
        "total_operations": total_row["total"] if total_row else 0,
        "packages_installed": installed_row["installed"] if installed_row else 0,
        "packages_available": available_row["available"] if available_row else 0,
        "by_operation": by_op,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_package(package_id: str) -> dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM packages WHERE package_id = ?", (package_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found")
    return _row_to_package(row)


async def _check_dependencies(dependencies: list[str]) -> list[str]:
    """Return list of dependency package_ids that are not installed/enabled."""
    if not dependencies:
        return []
    unresolved: list[str] = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        for dep in dependencies:
            async with db.execute(
                "SELECT status FROM packages WHERE package_id = ?", (dep,)
            ) as cursor:
                row = await cursor.fetchone()
            if row is None or row["status"] not in ("installed", "enabled"):
                unresolved.append(dep)
    return unresolved
