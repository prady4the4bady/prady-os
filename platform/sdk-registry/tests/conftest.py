from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def pytest_configure() -> None:
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


@pytest.fixture
async def db(tmp_path):
    import sdk_registry_service as service

    database = service.RegistryDB(db_path=str(tmp_path / "registry.db"))
    await database.init()
    yield database
    await database.close()


@pytest.fixture
def sample_manifest() -> dict[str, object]:
    return {
        "name": "test-app",
        "display_name": "Test App",
        "version": "1.0.0",
        "description": "A test SDK app",
        "author": "Test Author",
        "license": "MIT",
        "entry_point": "main.py",
        "icon": "icon.png",
        "permissions": ["model-inference", "notifications"],
        "capabilities": ["search:web", "send:notification"],
        "sandbox": {"memory_mb": 512, "cpu_shares": 256, "network_isolated": False, "read_only_root": True},
        "ui": {"type": "window", "width": 800, "height": 600, "resizable": True},
        "min_kryos_version": "1.0.0",
    }


@pytest.fixture
def mock_docker():
    mock = MagicMock()
    container = MagicMock()
    container.id = "abc123"
    container.status = "running"
    container.attrs = {"State": {"StartedAt": "2026-05-11T00:00:00Z"}}
    container.stats.return_value = {
        "memory_stats": {"usage": 52428800},
        "cpu_stats": {"cpu_usage": {"total_usage": 1000000}, "system_cpu_usage": 10000000},
        "precpu_stats": {"cpu_usage": {"total_usage": 900000}, "system_cpu_usage": 9000000},
    }
    mock.containers.run.return_value = container
    mock.containers.get.return_value = container
    mock.networks.list.return_value = []
    mock.networks.create.return_value = MagicMock()
    return mock


@pytest.fixture
def test_client(tmp_path, monkeypatch, mock_docker):
    import sandbox_manager as sandbox_module
    import sdk_registry_service as service

    monkeypatch.setattr(service, "DB_PATH", str(tmp_path / "registry.db"))
    monkeypatch.setattr(service, "WORKSPACE_BASE", str(tmp_path / "apps"))
    monkeypatch.setattr(sandbox_module.docker, "from_env", lambda: mock_docker)
    with TestClient(service.app) as client:
        yield client
