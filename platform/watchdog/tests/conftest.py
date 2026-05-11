from __future__ import annotations

from typing import Any

import pytest

import watchdog_service


async def _mock_auth() -> dict[str, Any]:
    return {"username": "test-user", "role": "admin", "session_id": "test-session"}


@pytest.fixture(autouse=True)
def _override_auth_dependency() -> None:
    watchdog_service.app.dependency_overrides[watchdog_service.require_auth] = _mock_auth
    yield
    watchdog_service.app.dependency_overrides.pop(watchdog_service.require_auth, None)
