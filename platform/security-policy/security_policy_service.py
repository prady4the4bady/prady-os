"""Kryos Security Policy Service — port 8117

Enforces least-privilege access control for all platform services.
Deny-by-default for sensitive permissions; every check is audit-logged.
"""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import aiosqlite
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "security.db"

EBPF_HARDENING_URL = os.environ.get("EBPF_HARDENING_URL", "http://ebpf-hardening:8118")

# Permissions that require an explicit grant — deny-by-default
SENSITIVE_PERMISSIONS: frozenset[str] = frozenset({
    "network",
    "filesystem-write",
    "filesystem-read-sensitive",
    "model-activation",
    "persona-activation",
    "service-restart",
    "package-install",
    "package-remove",
    "computer-control",
    "shell-exec",
    "clipboard",
    "task-replay",
    "kernel-sandbox",
})

# Permissions allowed for any subject without an explicit grant
BASELINE_SAFE_PERMISSIONS: frozenset[str] = frozenset({
    "notifications",
    "audit:read",
    "watchdog:read",
    "models:read",
    "personas:read",
})

ALL_KNOWN_PERMISSIONS: frozenset[str] = SENSITIVE_PERMISSIONS | BASELINE_SAFE_PERMISSIONS

SubjectType = Literal["package", "persona", "service"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("security-policy")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS policy_grants (
        id           TEXT PRIMARY KEY,
        subject_type TEXT NOT NULL,
        subject_id   TEXT NOT NULL,
        permission   TEXT NOT NULL,
        scope        TEXT NOT NULL DEFAULT 'global',
        expires_at   TEXT,
        granted_by   TEXT NOT NULL DEFAULT 'system',
        created_at   TEXT NOT NULL,
        UNIQUE(subject_type, subject_id, permission)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS policy_audit (
        id           TEXT PRIMARY KEY,
        subject_type TEXT NOT NULL,
        subject_id   TEXT NOT NULL,
        permission   TEXT NOT NULL,
        action       TEXT NOT NULL,
        allowed      INTEGER NOT NULL,
        reason       TEXT NOT NULL,
        created_at   TEXT NOT NULL
    )
    """,
]


async def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        for stmt in _DDL:
            await db.execute(stmt)
        await db.commit()


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    await _init_db()
    yield


app = FastAPI(title="Kryos Security Policy Service", version="1.0.0", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class GrantRequest(BaseModel):
    subject_type: SubjectType
    subject_id: str
    permission: str
    scope: str = "global"
    expires_at: str | None = None
    granted_by: str = "system"

    @field_validator("permission")
    @classmethod
    def validate_permission(cls, v: str) -> str:
        if v not in ALL_KNOWN_PERMISSIONS:
            raise ValueError(
                f"unknown permission: {v!r}. Must be one of {sorted(ALL_KNOWN_PERMISSIONS)}"
            )
        return v


class RevokeRequest(BaseModel):
    subject_type: SubjectType
    subject_id: str
    permission: str


class CheckRequest(BaseModel):
    subject_type: SubjectType
    subject_id: str
    permission: str


class CheckResponse(BaseModel):
    allowed: bool
    reason: str
    subject_type: str
    subject_id: str
    permission: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_expired(expires_at: str | None) -> bool:
    """Return True if the timestamp is in the past."""
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > exp
    except Exception:
        return False


async def _audit(
    subject_type: str,
    subject_id: str,
    permission: str,
    action: str,
    allowed: bool,
    reason: str,
) -> None:
    """Append an audit record (fire-and-forget style; errors are logged, not raised)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO policy_audit "
                "(id, subject_type, subject_id, permission, action, allowed, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    subject_type,
                    subject_id,
                    permission,
                    action,
                    int(allowed),
                    reason,
                    _now_iso(),
                ),
            )
            await db.commit()
    except Exception as exc:  # pragma: no cover
        log.error("audit write failed: %s", exc)


async def _check_kernel_sandbox(subject_id: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{EBPF_HARDENING_URL}/programs/{subject_id}/stats")
    except Exception as exc:
        log.warning("ebpf-hardening check failed, deny-by-default: %s", exc)
        return False, f"kernel-sandbox unavailable: {exc}"

    if resp.status_code == 404:
        return False, f"kernel sandbox program not loaded for {subject_id}"
    if resp.status_code != 200:
        return False, f"ebpf-hardening service error: {resp.status_code}"

    stats = resp.json()
    denial_count = stats.get("denial_count", 0)
    if denial_count < 10:
        return True, f"kernel-sandbox active (denials: {denial_count})"
    return False, f"kernel-sandbox has too many denials ({denial_count})"


async def _find_grant(subject_type: str, subject_id: str, permission: str) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM policy_grants "
            "WHERE subject_type = ? AND subject_id = ? AND permission = ?",
            (subject_type, subject_id, permission),
        ) as cur:
            return await cur.fetchone()


async def _check_permission(
    subject_type: str,
    subject_id: str,
    permission: str,
) -> tuple[bool, str]:
    """Core policy check. Returns (allowed, reason)."""
    # Baseline safe permissions are always allowed without a grant
    if permission in BASELINE_SAFE_PERMISSIONS:
        return True, "baseline-safe permission"

    # Kernel-sandbox permission: check with ebpf-hardening service
    if permission == "kernel-sandbox":
        return await _check_kernel_sandbox(subject_id)

    # Sensitive permissions require an explicit, non-expired grant
    if permission not in SENSITIVE_PERMISSIONS:
        return False, f"unknown permission: {permission!r}"

    row = await _find_grant(subject_type, subject_id, permission)
    if row is None:
        return False, f"no grant found for {subject_type}:{subject_id} → {permission}"
    if _is_expired(row["expires_at"]):
        return False, f"grant for {subject_type}:{subject_id} → {permission} has expired"
    return True, f"grant found (scope={row['scope']})"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "security-policy", "port": 8117}


@app.get("/policies")
async def list_policies() -> dict[str, Any]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM policy_grants ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
    grants = []
    for r in rows:
        g = dict(r)
        g["active"] = not _is_expired(g.get("expires_at"))
        grants.append(g)
    return {"grants": grants, "total": len(grants)}


@app.get("/policies/{subject_type}/{subject_id}")
async def get_subject_policies(subject_type: str, subject_id: str) -> dict[str, Any]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM policy_grants "
            "WHERE subject_type = ? AND subject_id = ? ORDER BY created_at DESC",
            (subject_type, subject_id),
        ) as cur:
            rows = await cur.fetchall()
    grants = [dict(r) for r in rows]
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "grants": grants,
        "total": len(grants),
    }


@app.post("/policies/grant", status_code=201)
async def grant_policy(req: GrantRequest) -> dict[str, Any]:
    await _init_db()
    now = _now_iso()
    grant_id = str(uuid.uuid4())

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO policy_grants "
                "(id, subject_type, subject_id, permission, scope, expires_at, granted_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    grant_id,
                    req.subject_type,
                    req.subject_id,
                    req.permission,
                    req.scope,
                    req.expires_at,
                    req.granted_by,
                    now,
                ),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            # Upsert: update existing grant
            await db.execute(
                "UPDATE policy_grants SET scope = ?, expires_at = ?, granted_by = ? "
                "WHERE subject_type = ? AND subject_id = ? AND permission = ?",
                (
                    req.scope,
                    req.expires_at,
                    req.granted_by,
                    req.subject_type,
                    req.subject_id,
                    req.permission,
                ),
            )
            await db.commit()
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id FROM policy_grants "
                "WHERE subject_type = ? AND subject_id = ? AND permission = ?",
                (req.subject_type, req.subject_id, req.permission),
            ) as cur:
                row = await cur.fetchone()
            if row:
                grant_id = row["id"]

    await _audit(
        req.subject_type,
        req.subject_id,
        req.permission,
        "grant",
        True,
        f"granted by {req.granted_by}",
    )
    log.info(
        "GRANT %s:%s → %s (scope=%s)",
        req.subject_type,
        req.subject_id,
        req.permission,
        req.scope,
    )

    return {
        "ok": True,
        "grant_id": grant_id,
        "subject_type": req.subject_type,
        "subject_id": req.subject_id,
        "permission": req.permission,
        "scope": req.scope,
        "expires_at": req.expires_at,
    }


@app.post("/policies/revoke")
async def revoke_policy(req: RevokeRequest) -> dict[str, Any]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM policy_grants "
            "WHERE subject_type = ? AND subject_id = ? AND permission = ?",
            (req.subject_type, req.subject_id, req.permission),
        )
        affected = cur.rowcount
        await db.commit()

    if affected == 0:
        raise HTTPException(status_code=404, detail="no matching grant found")

    await _audit(
        req.subject_type,
        req.subject_id,
        req.permission,
        "revoke",
        False,
        "grant revoked",
    )
    log.info("REVOKE %s:%s → %s", req.subject_type, req.subject_id, req.permission)

    return {
        "ok": True,
        "revoked": req.permission,
        "subject_type": req.subject_type,
        "subject_id": req.subject_id,
    }


@app.post("/policies/check", response_model=CheckResponse)
async def check_policy(req: CheckRequest) -> CheckResponse:
    await _init_db()
    allowed, reason = await _check_permission(
        req.subject_type, req.subject_id, req.permission
    )
    action = "check:allow" if allowed else "check:deny"
    await _audit(req.subject_type, req.subject_id, req.permission, action, allowed, reason)
    if not allowed:
        log.warning(
            "DENY %s:%s → %s (%s)",
            req.subject_type,
            req.subject_id,
            req.permission,
            reason,
        )

    return CheckResponse(
        allowed=allowed,
        reason=reason,
        subject_type=req.subject_type,
        subject_id=req.subject_id,
        permission=req.permission,
    )


@app.get("/audit")
async def list_audit(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) FROM policy_audit") as cur:
            total: int = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT * FROM policy_audit ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
    entries = []
    for r in rows:
        d = dict(r)
        d["allowed"] = bool(d["allowed"])
        entries.append(d)
    return {"entries": entries, "total": total, "limit": limit, "offset": offset}


@app.get("/audit/stats")
async def audit_stats() -> dict[str, Any]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) FROM policy_audit") as cur:
            total: int = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM policy_audit WHERE allowed = 1"
        ) as cur:
            allowed_count: int = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM policy_audit WHERE allowed = 0"
        ) as cur:
            denied_count: int = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT permission, COUNT(*) AS cnt FROM policy_audit "
            "WHERE allowed = 0 GROUP BY permission ORDER BY cnt DESC LIMIT 10"
        ) as cur:
            top_denied = {r["permission"]: r["cnt"] for r in await cur.fetchall()}
        async with db.execute("SELECT COUNT(*) FROM policy_grants") as cur:
            grant_count: int = (await cur.fetchone())[0]

    return {
        "total": total,
        "allowed": allowed_count,
        "denied": denied_count,
        "grant_count": grant_count,
        "top_denied_permissions": top_denied,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8117)
