from __future__ import annotations

from pathlib import Path
import sys

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture()
async def client() -> AsyncClient:
    service_dir = Path(__file__).resolve().parents[1]
    if str(service_dir) not in sys.path:
        sys.path.insert(0, str(service_dir))

    import system_health_service

    transport = ASGITransport(app=system_health_service.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
