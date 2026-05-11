from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = REPO_ROOT / "platform" / "bios-ai"


def pytest_configure() -> None:
    service_dir = str(SERVICE_DIR)
    if service_dir not in sys.path:
        sys.path.insert(0, service_dir)


@pytest.fixture()
def test_client(tmp_path: Path):
    import bios_ai_service as svc

    svc.DATA_DIR = tmp_path / "data"
    svc.DB_PATH = svc.DATA_DIR / "bios_ai.db"
    with TestClient(svc.app) as client:
        yield client
