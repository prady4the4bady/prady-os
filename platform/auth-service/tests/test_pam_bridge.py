from __future__ import annotations

import asyncio
import builtins
import types
from unittest.mock import MagicMock, patch

import pytest

import pam_bridge


@pytest.mark.asyncio
async def test_valid_creds_returns_true() -> None:
    fake_pam = MagicMock()
    fake_pam.authenticate.return_value = True
    fake_module = types.SimpleNamespace(pam=lambda: fake_pam)
    with patch.dict("sys.modules", {"pam": fake_module}):
        with patch("pam.pam", return_value=fake_pam):
            ok = await pam_bridge.validate_user_password("alice", "pass")
    assert ok is True


@pytest.mark.asyncio
async def test_invalid_creds_returns_false() -> None:
    fake_pam = MagicMock()
    fake_pam.authenticate.return_value = False
    fake_module = types.SimpleNamespace(pam=lambda: fake_pam)
    with patch.dict("sys.modules", {"pam": fake_module}):
        with patch("pam.pam", return_value=fake_pam):
            ok = await pam_bridge.validate_user_password("alice", "bad")
    assert ok is False


@pytest.mark.asyncio
async def test_pam_unavailable_raises_service_unavailable() -> None:
    orig_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "pam":
            raise ImportError("pam missing")
        return orig_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_fake_import):
        with pytest.raises(pam_bridge.ServiceUnavailableError):
            pam_bridge._sync_validate("alice", "pass", "kryos")


@pytest.mark.asyncio
async def test_async_wrapper_uses_run_in_executor() -> None:
    called = False

    async def run() -> bool:
        nonlocal called
        loop = asyncio.get_running_loop()

        def fake_run_in_executor(executor, func, *args):  # type: ignore[no-untyped-def]
            nonlocal called
            called = True
            fut = loop.create_future()
            fut.set_result(True)
            return fut

        with patch.object(loop, "run_in_executor", side_effect=fake_run_in_executor):
            return await pam_bridge.validate_user_password("alice", "pass")

    ok = await run()
    assert ok is True
    assert called
