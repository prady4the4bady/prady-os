from __future__ import annotations

from typing import Any

import pytest

import package_manager_service as pms


async def _mock_auth() -> dict[str, Any]:
    return {"username": "test-user", "role": "admin", "session_id": "test-session"}


@pytest.fixture(autouse=True)
def _override_auth_dependency() -> None:
    pms.app.dependency_overrides[pms.require_auth] = _mock_auth
    yield
    pms.app.dependency_overrides.pop(pms.require_auth, None)
