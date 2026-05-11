"""Tests for watchdog service."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from watchdog import app, _status, SERVICES


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_status_returns_all_services(client: TestClient) -> None:
    resp = client.get("/api/watchdog/status")
    assert resp.status_code == 200
    data = resp.json()
    names = {s["name"] for s in data["services"]}
    assert "kryos-swarm" in names
    assert "model-gateway" in names


def test_restart_unknown_service(client: TestClient) -> None:
    resp = client.post("/api/watchdog/restart/nonexistent-svc")
    assert resp.status_code == 200
    assert resp.json()["restarted"] is False


def test_restart_known_service_success(client: TestClient) -> None:
    with patch("watchdog._restart_container", return_value=True):
        resp = client.post("/api/watchdog/restart/kryos-swarm")
    assert resp.status_code == 200
    assert resp.json()["restarted"] is True
    assert _status["kryos-swarm"]["status"] == "restarting"


def test_restart_known_service_failure(client: TestClient) -> None:
    with patch("watchdog._restart_container", return_value=False):
        resp = client.post("/api/watchdog/restart/model-gateway")
    assert resp.status_code == 200
    assert resp.json()["restarted"] is False


@pytest.mark.asyncio
async def test_check_service_healthy() -> None:
    from watchdog import _check_service
    svc = {"url": "http://example.com/health"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        result = await _check_service(svc)
    assert result is True


@pytest.mark.asyncio
async def test_check_service_unhealthy() -> None:
    from watchdog import _check_service
    svc = {"url": "http://example.com/health"}
    with patch("httpx.AsyncClient.get", side_effect=Exception("timeout")):
        result = await _check_service(svc)
    assert result is False
