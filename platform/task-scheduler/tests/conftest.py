from __future__ import annotations

from typing import Any

import pytest

import scheduler_service as ss


async def _mock_auth() -> dict[str, Any]:
    return {"username": "test-user", "role": "admin", "session_id": "test-session"}


@pytest.fixture(autouse=True)
def _override_auth_dependency() -> None:
    ss.app.dependency_overrides[ss.require_auth] = _mock_auth
    yield
    ss.app.dependency_overrides.pop(ss.require_auth, None)
