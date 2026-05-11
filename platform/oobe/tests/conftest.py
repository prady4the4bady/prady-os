from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
def temp_config_dir(tmp_path: Path) -> Path:
    os.environ["KRYOS_CONFIG_DIR"] = str(tmp_path / "config")
    os.environ["OOBE_DIST"] = str(tmp_path / "dist")
    (tmp_path / "dist").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dist" / "index.html").write_text("<html>oobe</html>", encoding="utf-8")
    return tmp_path / "config"


@pytest_asyncio.fixture()
async def client(temp_config_dir: Path) -> AsyncClient:
    platform_oobe = Path(__file__).resolve().parents[1]
    if str(platform_oobe) not in sys.path:
        sys.path.insert(0, str(platform_oobe))

    import oobe_service

    importlib.reload(oobe_service)
    app = oobe_service.app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
