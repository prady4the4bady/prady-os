"""Tests for platform/package-manager/package_manager_service.py"""
from __future__ import annotations

import json
import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Ensure service directory is importable (avoids collision with built-in `platform`)
# ---------------------------------------------------------------------------
SERVICE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(SERVICE_DIR))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    cat = tmp_path / "catalog"
    cat.mkdir()
    manifests = [
        {
            "package_id": "notification-center",
            "name": "Notification Center",
            "version": "1.0.0",
            "type": "panel",
            "description": "Real-time notification stream",
            "entrypoint": "http://localhost:8100",
            "service_name": "notification-center",
            "dependencies": [],
            "permissions": ["notifications:read"],
            "healthcheck_path": "/api/notifications/health",
            "source": "kryos-core",
        },
        {
            "package_id": "task-history",
            "name": "Task History",
            "version": "1.0.0",
            "type": "panel",
            "description": "Audit log viewer",
            "entrypoint": "http://localhost:8100",
            "service_name": "task-history",
            "dependencies": [],
            "permissions": ["audit:read"],
            "healthcheck_path": "/api/audit/health",
            "source": "kryos-core",
        },
        {
            "package_id": "persona-manager",
            "name": "Persona Manager",
            "version": "1.0.0",
            "type": "panel",
            "description": "Create and manage agent personas",
            "entrypoint": "http://localhost:8114",
            "service_name": "persona-manager",
            "dependencies": ["model-hub"],
            "permissions": ["personas:read"],
            "healthcheck_path": "/health",
            "source": "kryos-core",
        },
        {
            "package_id": "model-hub",
            "name": "Model Hub",
            "version": "1.0.0",
            "type": "panel",
            "description": "Manage local LLM models",
            "entrypoint": "http://localhost:8113",
            "service_name": "model-hub",
            "dependencies": [],
            "permissions": ["models:read"],
            "healthcheck_path": "/health",
            "source": "kryos-core",
        },
    ]
    for m in manifests:
        (cat / f"{m['package_id']}.json").write_text(json.dumps(m), encoding="utf-8")
    return cat


@pytest_asyncio.fixture()
async def app_client(tmp_path: Path, catalog_dir: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    """Create a test client with isolated DB and catalog paths."""
    import package_manager_service as svc  # type: ignore[import]

    monkeypatch.setattr(svc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(svc, "DB_PATH", tmp_path / "packages.db")
    monkeypatch.setattr(svc, "CATALOG_DIR", catalog_dir)
    # Security-policy not running in tests — mock to allow all
    async def _allow_all(*_a: Any, **_kw: Any) -> tuple[bool, str]:
        await asyncio.sleep(0)
        return True, "test-allowed"
    monkeypatch.setattr(svc, "_policy_check", _allow_all)

    # Re-create app with patched paths by triggering lifespan
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def patched_lifespan(application: Any):  # type: ignore[type-arg]
        await svc._init_db()
        manifests = svc._load_catalog_manifests()
        await svc._bootstrap_catalog(manifests)
        yield

    svc.app.router.lifespan_context = patched_lifespan  # type: ignore[attr-defined]

    transport = ASGITransport(app=svc.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Manually trigger startup
        await svc._init_db()
        manifests = svc._load_catalog_manifests()
        await svc._bootstrap_catalog(manifests)
        yield client  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health(app_client: AsyncClient) -> None:
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "package-manager"
    assert data["port"] == 8116


# ---------------------------------------------------------------------------
# Catalog bootstrap & list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_packages_returns_catalog(app_client: AsyncClient) -> None:
    resp = await app_client.get("/packages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    ids = {p["package_id"] for p in data["packages"]}
    assert "notification-center" in ids
    assert "task-history" in ids
    assert "persona-manager" in ids
    assert "model-hub" in ids


@pytest.mark.asyncio
async def test_list_packages_filter_type(app_client: AsyncClient) -> None:
    resp = await app_client.get("/packages?type=panel")
    assert resp.status_code == 200
    data = resp.json()
    assert all(p["type"] == "panel" for p in data["packages"])


@pytest.mark.asyncio
async def test_list_packages_filter_status(app_client: AsyncClient) -> None:
    resp = await app_client.get("/packages?status=available")
    assert resp.status_code == 200
    data = resp.json()
    assert all(p["status"] == "available" for p in data["packages"])


@pytest.mark.asyncio
async def test_list_packages_search(app_client: AsyncClient) -> None:
    resp = await app_client.get("/packages?q=notification")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["packages"][0]["package_id"] == "notification-center"


@pytest.mark.asyncio
async def test_list_packages_invalid_type(app_client: AsyncClient) -> None:
    resp = await app_client.get("/packages?type=invalid")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_package(app_client: AsyncClient) -> None:
    resp = await app_client.get("/packages/notification-center")
    assert resp.status_code == 200
    data = resp.json()
    assert data["package_id"] == "notification-center"
    assert data["name"] == "Notification Center"
    assert isinstance(data["dependencies"], list)
    assert isinstance(data["permissions"], list)


@pytest.mark.asyncio
async def test_get_package_not_found(app_client: AsyncClient) -> None:
    resp = await app_client.get("/packages/does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_package(app_client: AsyncClient) -> None:
    resp = await app_client.post("/packages/install", json={"package_id": "notification-center"})
    assert resp.status_code == 202
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "installed"
    assert "operation_id" in data

    # Verify status changed
    pkg_resp = await app_client.get("/packages/notification-center")
    assert pkg_resp.json()["status"] == "installed"


@pytest.mark.asyncio
async def test_install_package_not_found(app_client: AsyncClient) -> None:
    resp = await app_client.post("/packages/install", json={"package_id": "ghost-package"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_install_package_already_installed(app_client: AsyncClient) -> None:
    await app_client.post("/packages/install", json={"package_id": "notification-center"})
    resp = await app_client.post("/packages/install", json={"package_id": "notification-center"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_install_package_dependency_conflict(app_client: AsyncClient) -> None:
    """persona-manager depends on model-hub; install should fail if model-hub not installed."""
    resp = await app_client.post("/packages/install", json={"package_id": "persona-manager"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "model-hub" in detail


@pytest.mark.asyncio
async def test_install_package_with_dep_resolved(app_client: AsyncClient) -> None:
    """persona-manager installs OK once model-hub is installed."""
    await app_client.post("/packages/install", json={"package_id": "model-hub"})
    resp = await app_client.post("/packages/install", json={"package_id": "persona-manager"})
    assert resp.status_code == 202
    assert resp.json()["status"] == "installed"


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_package(app_client: AsyncClient) -> None:
    await app_client.post("/packages/install", json={"package_id": "notification-center"})
    resp = await app_client.post("/packages/notification-center/update")
    assert resp.status_code == 202
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_update_package_not_installed(app_client: AsyncClient) -> None:
    resp = await app_client.post("/packages/notification-center/update")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Enable / Disable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enable_package(app_client: AsyncClient) -> None:
    import package_manager_service as svc

    await app_client.post("/packages/install", json={"package_id": "notification-center"})

    with patch.object(svc, "_execute_service_action", return_value=(True, "simulated: ok")):
        resp = await app_client.post("/packages/notification-center/enable")

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "enabled"

    pkg_resp = await app_client.get("/packages/notification-center")
    assert pkg_resp.json()["status"] == "enabled"


@pytest.mark.asyncio
async def test_enable_package_already_enabled(app_client: AsyncClient) -> None:
    import package_manager_service as svc

    await app_client.post("/packages/install", json={"package_id": "notification-center"})
    with patch.object(svc, "_execute_service_action", return_value=(True, "ok")):
        await app_client.post("/packages/notification-center/enable")
        resp = await app_client.post("/packages/notification-center/enable")

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_enable_package_service_action_fails(app_client: AsyncClient) -> None:
    import package_manager_service as svc

    await app_client.post("/packages/install", json={"package_id": "notification-center"})
    with patch.object(svc, "_execute_service_action", return_value=(False, "systemctl failed")):
        resp = await app_client.post("/packages/notification-center/enable")

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_disable_package(app_client: AsyncClient) -> None:
    import package_manager_service as svc

    await app_client.post("/packages/install", json={"package_id": "notification-center"})
    with patch.object(svc, "_execute_service_action", return_value=(True, "ok")):
        await app_client.post("/packages/notification-center/enable")
        resp = await app_client.post("/packages/notification-center/disable")

    assert resp.status_code == 202
    assert resp.json()["status"] == "disabled"


@pytest.mark.asyncio
async def test_disable_package_not_installed(app_client: AsyncClient) -> None:
    resp = await app_client.post("/packages/notification-center/disable")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_package(app_client: AsyncClient) -> None:
    await app_client.post("/packages/install", json={"package_id": "notification-center"})
    resp = await app_client.delete("/packages/notification-center")
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "available"

    pkg_resp = await app_client.get("/packages/notification-center")
    assert pkg_resp.json()["status"] == "available"


@pytest.mark.asyncio
async def test_remove_package_not_installed(app_client: AsyncClient) -> None:
    resp = await app_client.delete("/packages/notification-center")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_package_no_healthcheck(app_client: AsyncClient) -> None:
    """notification-center has a healthcheck_path; but with no real server it will use fallback."""
    await app_client.post("/packages/install", json={"package_id": "notification-center"})
    resp = await app_client.post("/packages/notification-center/check")
    # Does not raise; returns check result (may be unhealthy if endpoint not reachable)
    assert resp.status_code == 200
    data = resp.json()
    assert "healthy" in data
    assert "package_id" in data


@pytest.mark.asyncio
async def test_check_package_not_installed(app_client: AsyncClient) -> None:
    resp = await app_client.post("/packages/notification-center/check")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Operations log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operations_log(app_client: AsyncClient) -> None:
    await app_client.post("/packages/install", json={"package_id": "notification-center"})
    resp = await app_client.get("/operations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    ops = data["operations"]
    assert any(op["operation"] == "install" for op in ops)


@pytest.mark.asyncio
async def test_operations_filter_by_package(app_client: AsyncClient) -> None:
    await app_client.post("/packages/install", json={"package_id": "notification-center"})
    await app_client.post("/packages/install", json={"package_id": "task-history"})

    resp = await app_client.get("/operations?package_id=notification-center")
    assert resp.status_code == 200
    data = resp.json()
    assert all(op["package_id"] == "notification-center" for op in data["operations"])


@pytest.mark.asyncio
async def test_operations_stats(app_client: AsyncClient) -> None:
    await app_client.post("/packages/install", json={"package_id": "notification-center"})
    resp = await app_client.get("/operations/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_operations" in data
    assert "packages_installed" in data
    assert "packages_available" in data
    assert "by_operation" in data
    assert data["packages_installed"] >= 1


# ---------------------------------------------------------------------------
# Catalog endpoint alias
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catalog_endpoint(app_client: AsyncClient) -> None:
    resp = await app_client.get("/packages/catalog")
    assert resp.status_code == 200
    assert resp.json()["total"] == 4


# ---------------------------------------------------------------------------
# Service action allowlist
# ---------------------------------------------------------------------------


def test_execute_service_action_not_in_allowlist() -> None:
    import package_manager_service as svc

    ok, msg = svc._execute_service_action("not-allowed-service", "enable")
    assert ok is False
    assert "allowlist" in msg


def test_execute_service_action_invalid_action() -> None:
    import package_manager_service as svc

    ok, msg = svc._execute_service_action("notification-center", "restart")
    assert ok is False
    assert "not permitted" in msg


def test_execute_service_action_simulated_success() -> None:
    """When systemctl is not available it simulates success."""
    import package_manager_service as svc

    with patch("subprocess.run", side_effect=FileNotFoundError("systemctl not found")):
        ok, msg = svc._execute_service_action("notification-center", "enable")
    assert ok is True
    assert "simulated" in msg
