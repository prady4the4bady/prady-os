from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Awaitable, Callable, Literal

from fastapi import HTTPException

Role = Literal["admin", "operator", "guest"]

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


def has_permission(role: str, permission: str) -> bool:
    if role == "admin":
        return True
    if role == "operator":
        return permission in OPERATOR_PERMISSIONS
    if role == "guest":
        return permission in GUEST_PERMISSIONS
    return False


def require_permission(permission: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        sig = inspect.signature(func)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = sig.bind_partial(*args, **kwargs)
            current_user = bound.arguments.get("current_user")

            if current_user is None:
                request = bound.arguments.get("request")
                if request is not None:
                    current_user = getattr(request.state, "current_user", None)

            if not current_user:
                raise HTTPException(status_code=401, detail="missing token")

            role = str(current_user.get("role", ""))
            if not has_permission(role, permission):
                raise HTTPException(status_code=403, detail="insufficient permissions")

            return await func(*args, **kwargs)

        return wrapper

    return decorator
