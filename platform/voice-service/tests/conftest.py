"""Pytest configuration for voice-service tests."""

from __future__ import annotations

from typing import Any

import pytest

import voice_service

_ORIGINAL_STT_ENGINE = voice_service._stt_engine
_ORIGINAL_TTS_ENGINE = voice_service._tts_engine


async def _mock_auth() -> dict[str, Any]:
	return {"username": "test-user", "role": "admin", "session_id": "test-session"}


@pytest.fixture(autouse=True)
def _override_auth_dependency() -> None:
	voice_service._stt_engine = _ORIGINAL_STT_ENGINE
	voice_service._tts_engine = _ORIGINAL_TTS_ENGINE
	voice_service._router.stt = voice_service._stt_engine
	voice_service._router.tts = voice_service._tts_engine
	voice_service.app.dependency_overrides[voice_service.require_auth] = _mock_auth
	yield
	voice_service.app.dependency_overrides.pop(voice_service.require_auth, None)
	voice_service._stt_engine = _ORIGINAL_STT_ENGINE
	voice_service._tts_engine = _ORIGINAL_TTS_ENGINE
	voice_service._router.stt = voice_service._stt_engine
	voice_service._router.tts = voice_service._tts_engine
