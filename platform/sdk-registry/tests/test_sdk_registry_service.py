from __future__ import annotations

from pathlib import Path

import pytest
import respx

import sdk_registry_service as service


def _manifest() -> dict:
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


def test_get_sdk_apps_returns_list(test_client):
    response = test_client.get("/sdk/apps")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_post_install_valid_manifest_returns_200(test_client):
    response = test_client.post("/sdk/apps/install", json={"manifest_json": _manifest()})
    assert response.status_code == 200
    assert response.json()["status"] == "installed"


def test_post_install_invalid_manifest_returns_422(test_client):
    manifest = _manifest()
    manifest["version"] = "1.0"
    response = test_client.post("/sdk/apps/install", json={"manifest_json": manifest})
    assert response.status_code == 422


def test_post_install_missing_name_returns_422(test_client):
    manifest = _manifest()
    manifest.pop("name")
    response = test_client.post("/sdk/apps/install", json={"manifest_json": manifest})
    assert response.status_code == 422


def test_delete_unknown_app_returns_404(test_client):
    response = test_client.delete("/sdk/apps/missing-app")
    assert response.status_code == 404


def test_delete_known_app_returns_200(test_client):
    install = test_client.post("/sdk/apps/install", json={"manifest_json": _manifest()})
    app_id = install.json()["app_id"]
    response = test_client.delete(f"/sdk/apps/{app_id}")
    assert response.status_code == 200
    assert response.json()["uninstalled"] is True


def test_start_app_returns_container_id(test_client):
    app_id = test_client.post("/sdk/apps/install", json={"manifest_json": _manifest()}).json()["app_id"]
    response = test_client.post(f"/sdk/apps/{app_id}/start")
    assert response.status_code == 200
    assert response.json()["container_id"] == f"abc123"


def test_stop_app_returns_stopped(test_client):
    app_id = test_client.post("/sdk/apps/install", json={"manifest_json": _manifest()}).json()["app_id"]
    response = test_client.post(f"/sdk/apps/{app_id}/stop")
    assert response.status_code == 200
    assert response.json()["status"] == "stopped"


def test_status_returns_required_fields(test_client):
    app_id = test_client.post("/sdk/apps/install", json={"manifest_json": _manifest()}).json()["app_id"]
    response = test_client.get(f"/sdk/apps/{app_id}/status")
    body = response.json()
    assert response.status_code == 200
    for key in ["app_id", "status", "container_id", "uptime_seconds", "memory_used_mb", "cpu_pct"]:
        assert key in body


def test_delegate_no_match_returns_404(test_client):
    response = test_client.post("/sdk/delegate", json={"capability": "missing:cap", "payload": {}, "timeout_ms": 1000})
    assert response.status_code == 404


@pytest.mark.usefixtures("sample_manifest")
def test_delegate_matching_running_app_returns_200(test_client):
    install = test_client.post("/sdk/apps/install", json={"manifest_json": _manifest()})
    app_id = install.json()["app_id"]
    test_client.post(f"/sdk/apps/{app_id}/start")
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"http://kryos-sdk-{app_id}:8080/kryos/task").respond(json={"answer": "ok"}, status_code=200)
        response = test_client.post("/sdk/delegate", json={"capability": "search:web", "payload": {"q": "weather"}, "timeout_ms": 5000})
    assert response.status_code == 200
    assert response.json()["result"] == {"answer": "ok"}


def test_capabilities_returns_map(test_client):
    app_id = test_client.post("/sdk/apps/install", json={"manifest_json": _manifest()}).json()["app_id"]
    test_client.post(f"/sdk/apps/{app_id}/start")
    response = test_client.get("/sdk/capabilities")
    assert response.status_code == 200
    assert response.json()


def test_fs_write_traversal_returns_400(test_client):
    response = test_client.post("/sdk/fs/write", json={"app_id": "app", "path": "../etc/passwd", "content": "x"})
    assert response.status_code == 400


def test_fs_read_and_write_round_trip(test_client):
    app_id = test_client.post("/sdk/apps/install", json={"manifest_json": _manifest()}).json()["app_id"]
    write = test_client.post("/sdk/fs/write", json={"app_id": app_id, "path": "notes.txt", "content": "hello"})
    assert write.status_code == 200
    read = test_client.post("/sdk/fs/read", json={"app_id": app_id, "path": "notes.txt"})
    assert read.status_code == 200
    assert read.json()["content"] == "hello"


def test_health_returns_counts(test_client):
    install = test_client.post("/sdk/apps/install", json={"manifest_json": _manifest()})
    app_id = install.json()["app_id"]
    test_client.post(f"/sdk/apps/{app_id}/start")
    response = test_client.get("/health")
    body = response.json()
    assert response.status_code == 200
    assert body["service"] == "sdk-registry"
    assert body["installed_apps"] >= 1
    assert body["running_apps"] >= 1
