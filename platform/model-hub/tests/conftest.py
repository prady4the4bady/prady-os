from __future__ import annotations

from typing import Any

import pytest

import model_hub_service as mh


async def _mock_auth() -> dict[str, Any]:
    return {"username": "test-user", "role": "admin", "session_id": "test-session"}


@pytest.fixture(autouse=True)
def _override_auth_dependency() -> None:
    mh.app.dependency_overrides[mh.require_auth] = _mock_auth
    yield
    mh.app.dependency_overrides.pop(mh.require_auth, None)
