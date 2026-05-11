from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sandbox_manager import SANDBOX_NETWORK, SandboxManager


@pytest.fixture
def manifest_with_network() -> dict:
    return {
        "name": "test-app",
        "version": "1.0.0",
        "permissions": ["network"],
        "sandbox": {"memory_mb": 512, "cpu_shares": 256, "network_isolated": False, "read_only_root": True},
    }


@pytest.fixture
def manifest_without_network() -> dict:
    return {
        "name": "test-app",
        "version": "1.0.0",
        "permissions": ["notifications"],
        "sandbox": {"memory_mb": 512, "cpu_shares": 256, "network_isolated": True, "read_only_root": True},
    }


def _manager(mock_docker, tmp_path) -> SandboxManager:
    return SandboxManager(docker_client=mock_docker, workspace_base=str(tmp_path / "apps"))


def test_start_app_calls_run_with_correct_args(mock_docker, manifest_with_network, tmp_path):
    manager = _manager(mock_docker, tmp_path)
    info = manager.start_app("app1", manifest_with_network)
    assert info.container_id == "abc123"
    mock_docker.containers.run.assert_called_once()


def test_start_app_disables_network_when_permission_missing(mock_docker, manifest_without_network, tmp_path):
    manager = _manager(mock_docker, tmp_path)
    manager.start_app("app2", manifest_without_network)
    kwargs = mock_docker.containers.run.call_args.kwargs
    assert kwargs["network_mode"] == "none"
    assert "network" not in kwargs


def test_start_app_sets_mem_limit(mock_docker, manifest_with_network, tmp_path):
    manager = _manager(mock_docker, tmp_path)
    manager.start_app("app3", manifest_with_network)
    kwargs = mock_docker.containers.run.call_args.kwargs
    assert kwargs["mem_limit"] == "512m"


def test_start_app_creates_workspace_dir(mock_docker, manifest_with_network, tmp_path):
    manager = _manager(mock_docker, tmp_path)
    info = manager.start_app("app4", manifest_with_network)
    assert Path(info.workspace_path).exists()


def test_stop_app_calls_container_stop(mock_docker, tmp_path):
    manager = _manager(mock_docker, tmp_path)
    assert manager.stop_app("app5") is True
    mock_docker.containers.get.return_value.stop.assert_called_once_with(timeout=10)


def test_stop_app_returns_false_when_missing(tmp_path):
    mock_docker = MagicMock()
    mock_docker.containers.get.side_effect = Exception("missing")
    manager = _manager(mock_docker, tmp_path)
    assert manager.stop_app("missing") is False


def test_remove_app_calls_stop_then_remove(mock_docker, manifest_with_network, tmp_path):
    manager = _manager(mock_docker, tmp_path)
    assert manager.remove_app("app6") is True
    mock_docker.containers.get.return_value.stop.assert_called_once_with(timeout=10)
    mock_docker.containers.get.return_value.remove.assert_called_once_with(force=True)


def test_get_status_returns_stopped_when_missing(tmp_path):
    mock_docker = MagicMock()
    mock_docker.containers.get.side_effect = Exception("missing")
    manager = _manager(mock_docker, tmp_path)
    status = manager.get_status("app7")
    assert status.status == "stopped"


def test_get_status_reports_cpu_and_memory(mock_docker, tmp_path):
    manager = _manager(mock_docker, tmp_path)
    status = manager.get_status("app8")
    assert status.status == "running"
    assert status.memory_used_mb > 0
    assert status.cpu_pct >= 0


def test_ensure_network_creates_missing_network(mock_docker, tmp_path):
    mock_docker.networks.list.return_value = []
    manager = _manager(mock_docker, tmp_path)
    manager.ensure_network()
    mock_docker.networks.create.assert_called_once_with(SANDBOX_NETWORK, driver="bridge", internal=False)
