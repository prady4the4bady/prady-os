from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ota_service as svc  # noqa: E402
from slot_manager import SlotManager  # noqa: E402


@pytest.fixture(autouse=True)
def reset_runtime(tmp_path: Path):
    svc.STAGING_DIR = tmp_path / "staging"
    svc.SLOTS_DIR = tmp_path / "slots"
    svc.STAGING_DIR.mkdir(parents=True, exist_ok=True)
    for slot in ("slot_a", "slot_b"):
        slot_dir = svc.SLOTS_DIR / slot
        slot_dir.mkdir(parents=True, exist_ok=True)
        (slot_dir / "rootfs.bin").write_bytes(b"")

    svc.SLOT_MANAGER = SlotManager(tmp_path / "slot_state.db", tmp_path / "grubenv")
    svc.LAST_CHECK_TS = None
    svc.LAST_MANIFEST = None
    svc.DOWNLOADS.clear()
    svc.DOWNLOAD_TASKS.clear()

    yield


@pytest.fixture
def app_client():
    return TestClient(svc.app)


def _manifest(version: str = "1.0.1") -> dict:
    return {
        "version": version,
        "slot": "b",
        "sha256_full": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "sha256_delta": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "size_full": 0,
        "size_delta": 128,
        "delta_base_version": "1.0.0",
        "changelog": ["Bug fixes"],
        "min_version": "1.0.0",
        "released_at": "2026-05-10T00:00:00Z",
    }


class TestOTAService:
    def test_status(self, app_client):
        res = app_client.get("/status")
        assert res.status_code == 200
        data = res.json()
        assert data["active_slot"] == "a"
        assert data["version"] == "1.0.0"

    @patch("ota_service._fetch_manifest")
    def test_check_update_available(self, mock_fetch, app_client):
        mock_fetch.return_value = svc.VALIDATOR.validate(_manifest("1.0.2"))
        res = app_client.post("/check")
        assert res.status_code == 200
        data = res.json()
        assert data["update_available"] is True
        assert data["version"] == "1.0.2"

    @patch("ota_service._fetch_manifest")
    def test_check_same_version_no_update(self, mock_fetch, app_client):
        mock_fetch.return_value = svc.VALIDATOR.validate(_manifest("1.0.0"))
        res = app_client.post("/check")
        assert res.status_code == 200
        assert res.json()["update_available"] is False

    @patch("ota_service._fetch_manifest")
    def test_download_returns_download_id(self, mock_fetch, app_client):
        mock_fetch.return_value = svc.VALIDATOR.validate(_manifest())
        app_client.post("/check")
        res = app_client.post("/download")
        assert res.status_code == 200
        assert "download_id" in res.json()

    @patch("ota_service._fetch_manifest")
    def test_download_progress_sse_contains_percent(self, mock_fetch, app_client):
        mock_fetch.return_value = svc.VALIDATOR.validate(_manifest())
        app_client.post("/check")
        download_id = app_client.post("/download").json()["download_id"]
        res = app_client.get(f"/download/{download_id}/progress")
        assert res.status_code == 200
        assert "percent" in res.text

    @patch("ota_service._fetch_manifest")
    @patch("ota_service.PATCHER.apply_patch", return_value=True)
    def test_apply_returns_applied(self, _mock_apply, mock_fetch, app_client):
        mock_fetch.return_value = svc.VALIDATOR.validate(_manifest())
        app_client.post("/check")
        download_id = app_client.post("/download").json()["download_id"]
        svc.DOWNLOADS[download_id]["done"] = True
        svc.DOWNLOADS[download_id]["path"] = str(svc.STAGING_DIR / "mock.delta")
        Path(svc.DOWNLOADS[download_id]["path"]).write_bytes(b"x")

        res = app_client.post("/apply")
        assert res.status_code == 200
        assert res.json()["status"] == "applied"

    @patch("ota_service._fetch_manifest")
    @patch("ota_service.PATCHER.apply_patch", return_value=True)
    def test_commit_returns_next_slot(self, _mock_apply, mock_fetch, app_client):
        mock_fetch.return_value = svc.VALIDATOR.validate(_manifest())
        app_client.post("/check")
        download_id = app_client.post("/download").json()["download_id"]
        svc.DOWNLOADS[download_id]["done"] = True
        svc.DOWNLOADS[download_id]["path"] = str(svc.STAGING_DIR / "mock.delta")
        Path(svc.DOWNLOADS[download_id]["path"]).write_bytes(b"x")
        app_client.post("/apply")

        res = app_client.post("/commit")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "committed"
        assert data["next_slot"] == "b"

    def test_rollback(self, app_client):
        res = app_client.post("/rollback")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "rolled_back"
        assert data["active_slot"] == "a"

    @patch("ota_service._fetch_manifest")
    def test_history_has_entries(self, mock_fetch, app_client):
        mock_fetch.return_value = svc.VALIDATOR.validate(_manifest())
        app_client.post("/check")
        app_client.post("/commit")

        res = app_client.get("/history")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data["history"], list)
        assert len(data["history"]) >= 1

    def test_health_report_three_failures_trigger_rollback(self, app_client):
        svc.SLOT_MANAGER.set_standby_version("1.0.1")
        svc.SLOT_MANAGER.switch_slot()  # move active to b for rollback path

        for _ in range(2):
            res = app_client.post("/health-report", json={"success": False, "service": "watchdog"})
            assert res.status_code == 200

        final = app_client.post("/health-report", json={"success": False, "service": "watchdog"})
        assert final.status_code == 200
        body = final.json()
        assert body["rolled_back"] is True
        assert body["active_slot"] == "a"
