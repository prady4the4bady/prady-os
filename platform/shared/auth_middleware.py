from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any
from typing import cast

import httpx
from fastapi import Depends, Header, HTTPException, Request

AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth-service:8013")

OPERATOR_PERMISSIONS = {
    "model-activation",
    "persona-activation",
    "task-execute",
    "voice-use",
    "package-install",
    "service-restart",
    "screen-automation",
    "ota-apply",
}

GUEST_PERMISSIONS = {
    "task-execute",
    "voice-use",
}


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing bearer token")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid authorization header")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return token


async def _verify_token_with_auth_service(token: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{AUTH_SERVICE_URL}/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="invalid or expired token")
        data = resp.json()
        return {
            "username": data.get("username") or data.get("sub"),
            "role": data.get("role", "guest"),
            "session_id": data.get("session_id"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"auth-service unavailable: {exc}") from exc


async def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = _extract_bearer(authorization)
    user = await _verify_token_with_auth_service(token)
    request.state.current_user = user
    return user


async def optional_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any] | None:
    if not authorization:
        return None
    token = _extract_bearer(authorization)
    user = await _verify_token_with_auth_service(token)
    request.state.current_user = user
    return user


def get_current_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "current_user", None)
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="missing token")
    return cast(dict[str, Any], user)


def has_permission(role: str, permission: str) -> bool:
    if role == "admin":
        return True
    if role == "operator":
        return permission in OPERATOR_PERMISSIONS
    if role == "guest":
        return permission in GUEST_PERMISSIONS
    return False


def require_permission(permission: str) -> Callable[..., dict[str, Any]]:
    def _dependency(current_user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
        if not has_permission(str(current_user.get("role", "")), permission):
            raise HTTPException(status_code=403, detail="insufficient permissions")
        return current_user

    return _dependency
