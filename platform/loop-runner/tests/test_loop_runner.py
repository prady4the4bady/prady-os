"""Tests for loop runner service."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


@pytest.fixture
def client():
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    with patch("loop_runner._loop", new_callable=AsyncMock):
        from loop_runner import app
        return TestClient(app)


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_status_initial(client: TestClient) -> None:
    resp = client.get("/api/loop/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert "paused" in data
    assert "tasks_processed" in data


def test_pause(client: TestClient) -> None:
    resp = client.post("/api/loop/pause")
    assert resp.status_code == 200
    assert resp.json()["paused"] is True


def test_resume(client: TestClient) -> None:
    client.post("/api/loop/pause")
    resp = client.post("/api/loop/resume")
    assert resp.status_code == 200
    assert resp.json()["paused"] is False


def test_pause_then_status(client: TestClient) -> None:
    client.post("/api/loop/pause")
    resp = client.get("/api/loop/status")
    assert resp.json()["paused"] is True
    client.post("/api/loop/resume")
    resp = client.get("/api/loop/status")
    assert resp.json()["paused"] is False
