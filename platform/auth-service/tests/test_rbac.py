from __future__ import annotations

import pytest
from fastapi import HTTPException

from rbac import has_permission, require_permission


def test_admin_has_all_permissions() -> None:
    assert has_permission("admin", "package-install")
    assert has_permission("admin", "anything")


def test_operator_has_model_activation() -> None:
    assert has_permission("operator", "model-activation")


def test_guest_no_package_install() -> None:
    assert not has_permission("guest", "package-install")


@pytest.mark.asyncio
async def test_require_permission_raises_403_for_insufficient_role() -> None:
    @require_permission("package-install")
    async def handler(current_user: dict[str, str]) -> dict[str, str]:
        return {"ok": "true"}

    with pytest.raises(HTTPException) as exc:
        await handler(current_user={"role": "guest"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_permission_passes_for_correct_role() -> None:
    @require_permission("voice-use")
    async def handler(current_user: dict[str, str]) -> dict[str, str]:
        return {"ok": "true"}

    res = await handler(current_user={"role": "operator"})
    assert res["ok"] == "true"


@pytest.mark.asyncio
async def test_missing_token_raises_401() -> None:
    @require_permission("voice-use")
    async def handler() -> dict[str, str]:
        return {"ok": "true"}

    with pytest.raises(HTTPException) as exc:
        await handler()
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_semantics_401() -> None:
    # Decorator expects auth middleware to surface invalid/expired token as missing user context.
    @require_permission("voice-use")
    async def handler(current_user: dict[str, str] | None = None) -> dict[str, str]:
        return {"ok": "true"}

    with pytest.raises(HTTPException) as exc:
        await handler(current_user=None)
    assert exc.value.status_code == 401


def test_unknown_role_denied() -> None:
    assert not has_permission("unknown", "voice-use")
