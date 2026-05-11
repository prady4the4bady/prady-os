from __future__ import annotations

import time

import bios_ai_service as svc
from filesystem_checker import CheckItem


def test_health_endpoint(test_client):
    resp = test_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "bios-ai"
    assert body["version"] == "1.0.0"


def test_status_endpoint_shape(test_client):
    resp = test_client.get("/bios-ai/status")
    assert resp.status_code == 200
    body = resp.json()
    expected = {
        "boot_decision",
        "stage1_ran",
        "stage2_complete",
        "repairs_made",
        "hardware_score",
        "last_boot_ts",
    }
    assert expected.issubset(set(body.keys()))


def test_hardware_endpoint_shape(test_client):
    resp = test_client.get("/bios-ai/hardware")
    assert resp.status_code == 200
    body = resp.json()
    assert "cpu" in body
    assert "memory" in body
    assert "disks" in body
    assert "gpu" in body
    assert "network" in body
    assert "bios" in body


def test_boot_history_endpoint(test_client):
    resp = test_client.get("/bios-ai/boot-history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_repair_scan_lifecycle(test_client, monkeypatch):
    async def fake_scan():
        return [
            CheckItem(
                item_id="item-1",
                path="/var/kryos/test.lock",
                issue_type="orphan_lock",
                action="remove_lock",
                zone="free",
            )
        ]

    monkeypatch.setattr(svc.app.state.fs_checker, "scan", fake_scan)

    start_resp = test_client.post("/bios-ai/repair/scan")
    assert start_resp.status_code == 200
    scan_id = start_resp.json()["scan_id"]

    for _ in range(200):
        status_resp = test_client.get(f"/bios-ai/repair/scan/{scan_id}")
        assert status_resp.status_code == 200
        payload = status_resp.json()
        if payload["status"] == "complete":
            break
        time.sleep(0.02)

    done_resp = test_client.get(f"/bios-ai/repair/scan/{scan_id}")
    body = done_resp.json()
    assert body["status"] == "complete"
    assert body["issues_found"] >= 1


def test_approve_unknown_item_returns_404(test_client):
    resp = test_client.post("/bios-ai/repair/approve/unknown")
    assert resp.status_code == 404


def test_reject_unknown_item_returns_404(test_client):
    resp = test_client.post("/bios-ai/repair/reject/unknown")
    assert resp.status_code == 404
