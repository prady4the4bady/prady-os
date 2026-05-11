from __future__ import annotations

import asyncio
import builtins
from concurrent.futures import Executor


class ServiceUnavailableError(RuntimeError):
    """Raised when PAM bindings are unavailable."""


def _load_pam_module():
    try:
        return builtins.__import__("pam")
    except Exception as exc:  # pragma: no cover
        raise ServiceUnavailableError("python-pam unavailable") from exc


def _sync_validate(username: str, password: str, service: str) -> bool:
    pam_module = _load_pam_module()
    authenticator = pam_module.pam()
    return bool(authenticator.authenticate(username, password, service=service))


async def validate_user_password(
    username: str,
    password: str,
    service: str = "kryos",
    executor: Executor | None = None,
) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, _sync_validate, username, password, service)
