"""Tests for security_policy_service.py"""
from __future__ import annotations

import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(SERVICE_DIR))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import security_policy_service as svc


@pytest.fixture(autouse=True)
def _patch_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(svc, "DB_PATH", tmp_path / "security.db")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=svc.app), base_url="http://test"
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["port"] == 8117


# ---------------------------------------------------------------------------
# Grant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grant_sensitive_permission(client: AsyncClient) -> None:
    r = await client.post(
        "/policies/grant",
        json={
            "subject_type": "package",
            "subject_id": "my-plugin",
            "permission": "package-install",
            "scope": "global",
            "granted_by": "admin",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["ok"] is True
    assert data["permission"] == "package-install"
    assert data["subject_id"] == "my-plugin"


@pytest.mark.asyncio
async def test_grant_baseline_permission(client: AsyncClient) -> None:
    r = await client.post(
        "/policies/grant",
        json={
            "subject_type": "service",
            "subject_id": "watchdog",
            "permission": "notifications",
        },
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_grant_unknown_permission_rejected(client: AsyncClient) -> None:
    r = await client.post(
        "/policies/grant",
        json={
            "subject_type": "package",
            "subject_id": "bad-plugin",
            "permission": "unknown-perm",
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_grant_upsert(client: AsyncClient) -> None:
    """Granting the same permission twice should upsert, not error."""
    payload = {
        "subject_type": "persona",
        "subject_id": "persona-1",
        "permission": "persona-activation",
        "scope": "session",
    }
    r1 = await client.post("/policies/grant", json=payload)
    assert r1.status_code == 201
    payload["scope"] = "global"
    r2 = await client.post("/policies/grant", json=payload)
    assert r2.status_code == 201


# ---------------------------------------------------------------------------
# Check — allowed (grant present)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_allowed_after_grant(client: AsyncClient) -> None:
    await client.post(
        "/policies/grant",
        json={
            "subject_type": "service",
            "subject_id": "watchdog",
            "permission": "service-restart",
        },
    )
    r = await client.post(
        "/policies/check",
        json={
            "subject_type": "service",
            "subject_id": "watchdog",
            "permission": "service-restart",
        },
    )
    assert r.status_code == 200
    assert r.json()["allowed"] is True


# ---------------------------------------------------------------------------
# Check — denied (no grant)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_denied_no_grant(client: AsyncClient) -> None:
    r = await client.post(
        "/policies/check",
        json={
            "subject_type": "package",
            "subject_id": "untrusted-pkg",
            "permission": "shell-exec",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["allowed"] is False
    assert "no grant" in data["reason"]


# ---------------------------------------------------------------------------
# Check — baseline safe permissions always allowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_baseline_safe_always_allowed(client: AsyncClient) -> None:
    r = await client.post(
        "/policies/check",
        json={
            "subject_type": "package",
            "subject_id": "any-package",
            "permission": "models:read",
        },
    )
    assert r.status_code == 200
    assert r.json()["allowed"] is True


# ---------------------------------------------------------------------------
# Check — expired grant is denied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_denied_expired_grant(client: AsyncClient) -> None:
    await client.post(
        "/policies/grant",
        json={
            "subject_type": "package",
            "subject_id": "old-plugin",
            "permission": "computer-control",
            "expires_at": "2000-01-01T00:00:00+00:00",
        },
    )
    r = await client.post(
        "/policies/check",
        json={
            "subject_type": "package",
            "subject_id": "old-plugin",
            "permission": "computer-control",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["allowed"] is False
    assert "expired" in data["reason"]


# ---------------------------------------------------------------------------
# Revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_existing_grant(client: AsyncClient) -> None:
    await client.post(
        "/policies/grant",
        json={
            "subject_type": "service",
            "subject_id": "pkg-manager",
            "permission": "package-install",
        },
    )
    r = await client.post(
        "/policies/revoke",
        json={
            "subject_type": "service",
            "subject_id": "pkg-manager",
            "permission": "package-install",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Subsequent check must be denied
    r2 = await client.post(
        "/policies/check",
        json={
            "subject_type": "service",
            "subject_id": "pkg-manager",
            "permission": "package-install",
        },
    )
    assert r2.json()["allowed"] is False


@pytest.mark.asyncio
async def test_revoke_nonexistent_grant_returns_404(client: AsyncClient) -> None:
    r = await client.post(
        "/policies/revoke",
        json={
            "subject_type": "package",
            "subject_id": "ghost-pkg",
            "permission": "network",
        },
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_entries_recorded(client: AsyncClient) -> None:
    await client.post(
        "/policies/check",
        json={
            "subject_type": "package",
            "subject_id": "audit-test",
            "permission": "clipboard",
        },
    )
    r = await client.get("/audit")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(e["permission"] == "clipboard" for e in data["entries"])


@pytest.mark.asyncio
async def test_audit_stats(client: AsyncClient) -> None:
    # Trigger a deny
    await client.post(
        "/policies/check",
        json={
            "subject_type": "service",
            "subject_id": "test-svc",
            "permission": "shell-exec",
        },
    )
    r = await client.get("/audit/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "denied" in data
    assert data["denied"] >= 1


# ---------------------------------------------------------------------------
# List policies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_policies(client: AsyncClient) -> None:
    await client.post(
        "/policies/grant",
        json={
            "subject_type": "persona",
            "subject_id": "p1",
            "permission": "model-activation",
        },
    )
    r = await client.get("/policies")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_get_subject_policies(client: AsyncClient) -> None:
    await client.post(
        "/policies/grant",
        json={
            "subject_type": "package",
            "subject_id": "subject-pkg",
            "permission": "network",
        },
    )
    r = await client.get("/policies/package/subject-pkg")
    assert r.status_code == 200
    data = r.json()
    assert data["subject_id"] == "subject-pkg"
    assert len(data["grants"]) >= 1


# ---------------------------------------------------------------------------
# Sensitive deny-by-default (all SENSITIVE_PERMISSIONS should be denied without grant)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "permission",
    [
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
    ],
)
async def test_sensitive_deny_by_default(
    client: AsyncClient, permission: str
) -> None:
    r = await client.post(
        "/policies/check",
        json={
            "subject_type": "package",
            "subject_id": "untrusted",
            "permission": permission,
        },
    )
    assert r.status_code == 200
    assert r.json()["allowed"] is False
