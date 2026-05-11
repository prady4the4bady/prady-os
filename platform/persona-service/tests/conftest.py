from __future__ import annotations

from typing import Any

import pytest

import persona_service


async def _mock_auth() -> dict[str, Any]:
    return {"username": "test-user", "role": "admin", "session_id": "test-session"}


@pytest.fixture(autouse=True)
def _override_auth_dependency() -> None:
    persona_service.app.dependency_overrides[persona_service.require_auth] = _mock_auth
    yield
    persona_service.app.dependency_overrides.pop(persona_service.require_auth, None)
