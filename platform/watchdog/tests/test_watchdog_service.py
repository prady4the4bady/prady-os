"""Tests for watchdog_service.py — Phase 25 production watchdog."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).parents[3]
SERVICE_DIR = REPO_ROOT / "platform" / "watchdog"
sys.path.insert(0, str(SERVICE_DIR))

import watchdog_service as ws
from watchdog_service import app

TRANSPORT = ASGITransport(app=app)


# ---------------------------------------------------------------------------
# Fake HTTP machinery
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


class _FakeHTTPClient:
    """Minimal async context-manager replacement for httpx.AsyncClient."""

    def __init__(self, *, status_code: int = 200, raise_error: bool = False) -> None:
        self._status_code = status_code
        self._raise_error = raise_error

    async def __aenter__(self) -> "_FakeHTTPClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        """No-op async exit."""
        pass

    def get(self, url: str, **_: Any) -> _FakeResponse:
        if self._raise_error:
            raise httpx.RequestError(f"connection refused: {url}")
        return _FakeResponse(self._status_code)

    def post(self, url: str, **_: Any) -> _FakeResponse:
        return _FakeResponse(200)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ws, "DB_PATH", tmp_path / "watchdog.db")
    await ws._init_db()
    # Security-policy not running in tests — mock to allow all
    def _allow_all(*_a: Any, **_kw: Any) -> tuple[bool, str]:
        return True, "test-allowed"
    monkeypatch.setattr(ws, "_policy_check", _allow_all)


def _patch_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status_code: int = 200,
    raise_error: bool = False,
) -> None:
    monkeypatch.setattr(
        ws.httpx,
        "AsyncClient",
        lambda *a, **kw: _FakeHTTPClient(status_code=status_code, raise_error=raise_error),
    )


# ---------------------------------------------------------------------------
# Tests — basic endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_services_returns_all_monitored() -> None:
    """All monitored services appear even before any checks run."""
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/services")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == len(ws.SERVICES)
    names = {s["name"] for s in data["services"]}
    assert names == set(ws.SERVICES.keys())


@pytest.mark.asyncio
async def test_get_unknown_service_returns_404() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/services/nonexistent-svc")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_force_check_unknown_service_returns_404() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/services/nonexistent-svc/check")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — status transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_healthy_after_successful_check(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, status_code=200)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/services/agent-runtime/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["consecutive_failures"] == 0
    assert data["check_count"] == 1


@pytest.mark.asyncio
async def test_single_failure_keeps_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """One failure is insufficient to trigger degraded (threshold is 2)."""
    _patch_http(monkeypatch, status_code=200)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post("/services/agent-runtime/check")

    _patch_http(monkeypatch, raise_error=True)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/services/agent-runtime/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["consecutive_failures"] == 1


@pytest.mark.asyncio
async def test_two_failures_trigger_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, raise_error=True)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post("/services/persona-service/check")
        resp = await ac.post("/services/persona-service/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["consecutive_failures"] == 2


@pytest.mark.asyncio
async def test_four_failures_trigger_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, raise_error=True)
    svc = "notification-bus"
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        for _ in range(4):
            resp = await ac.post(f"/services/{svc}/check")
    assert resp.status_code == 200
    assert resp.json()["status"] == "down"


@pytest.mark.asyncio
async def test_recovery_resets_failures_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = "audit-log"
    _patch_http(monkeypatch, raise_error=True)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        for _ in range(4):
            await ac.post(f"/services/{svc}/check")

    _patch_http(monkeypatch, status_code=200)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(f"/services/{svc}/check")
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["consecutive_failures"] == 0


@pytest.mark.asyncio
async def test_high_latency_triggers_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful but extremely slow response should produce degraded status."""
    # Set threshold to -1 so any latency (even sub-ms) exceeds it
    monkeypatch.setattr(ws, "LATENCY_DEGRADED_MS", -1.0)
    _patch_http(monkeypatch, status_code=200)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/services/model-hub/check")
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# Tests — incidents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_incident_created_on_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, raise_error=True)
    svc = "task-scheduler"
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        for _ in range(2):
            await ac.post(f"/services/{svc}/check")
        resp = await ac.get("/incidents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    incident = data["incidents"][0]
    assert incident["service_name"] == svc
    assert incident["status"] == "degraded"
    assert incident["resolved_at"] is None


@pytest.mark.asyncio
async def test_incident_created_on_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, raise_error=True)
    svc = "memory-service"
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        for _ in range(4):
            await ac.post(f"/services/{svc}/check")
        resp = await ac.get("/incidents")
    data = resp.json()
    statuses = {inc["status"] for inc in data["incidents"]}
    assert "down" in statuses or "degraded" in statuses


@pytest.mark.asyncio
async def test_incident_resolved_on_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = "model-hub"
    _patch_http(monkeypatch, raise_error=True)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        for _ in range(2):
            await ac.post(f"/services/{svc}/check")

    _patch_http(monkeypatch, status_code=200)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post(f"/services/{svc}/check")
        resp = await ac.get("/incidents")
    data = resp.json()
    assert data["total"] >= 1
    # At least the most recent incident for this service should be resolved
    svc_incidents = [i for i in data["incidents"] if i["service_name"] == svc]
    assert any(i["resolved_at"] is not None for i in svc_incidents)


@pytest.mark.asyncio
async def test_incidents_stats_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, raise_error=True)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        for _ in range(2):
            await ac.post("/services/agent-runtime/check")
        resp = await ac.get("/incidents/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total"] >= 1
    assert stats["open"] >= 1
    assert stats["resolved"] == 0


@pytest.mark.asyncio
async def test_incidents_filter_by_service(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, raise_error=True)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        for _ in range(2):
            await ac.post("/services/agent-runtime/check")
        for _ in range(2):
            await ac.post("/services/persona-service/check")
        resp = await ac.get("/incidents?service=agent-runtime")
    data = resp.json()
    for inc in data["incidents"]:
        assert inc["service_name"] == "agent-runtime"


# ---------------------------------------------------------------------------
# Tests — scan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_all_services(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, status_code=200)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["scanned"] == len(ws.SERVICES)


# ---------------------------------------------------------------------------
# Tests — restart endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_unknown_service_returns_404() -> None:
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/services/nonexistent-svc/restart")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_restart_systemctl_not_available(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_systemctl(*args: Any, **kwargs: Any) -> None:
        raise FileNotFoundError("systemctl not found")

    monkeypatch.setattr(ws.subprocess, "run", _no_systemctl)
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/services/agent-runtime/restart")
    assert resp.status_code == 503
    assert "non-systemd" in resp.json()["error"]


@pytest.mark.asyncio
async def test_restart_systemctl_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""
    mock_result.stdout = ""
    monkeypatch.setattr(ws.subprocess, "run", lambda *a, **kw: mock_result)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/services/agent-runtime/restart")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["unit"] == "prax-agent-runtime.service"


@pytest.mark.asyncio
async def test_restart_systemctl_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Job for kryos-persona-service.service failed."
    mock_result.stdout = ""
    monkeypatch.setattr(ws.subprocess, "run", lambda *a, **kw: mock_result)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/services/persona-service/restart")
    assert resp.status_code == 500
    assert resp.json()["ok"] is False
