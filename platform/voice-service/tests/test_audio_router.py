"""Tests for Audio Router."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from audio_router import AudioRouter, RouterResult, VoicePipelineError
from stt_engine import STTEngine, STTResult
from tts_engine import TTSEngine, TTSResult


@pytest.fixture
def mock_stt():
    """Mock STT engine."""
    mock = MagicMock(spec=STTEngine)
    mock.transcribe.return_value = STTResult(
        transcript="set a timer for 5 minutes",
        confidence=0.92,
        language="en",
        duration_ms=1200,
    )
    return mock


@pytest.fixture
def mock_tts():
    """Mock TTS engine."""
    mock = MagicMock(spec=TTSEngine)
    mock.synthesize.return_value = TTSResult(
        audio_bytes=b"\x00" * 4410,
        duration_ms=100,
        voice="en_US-amy-medium",
        text_length=20,
    )
    return mock


@pytest.fixture
def router(mock_stt, mock_tts):
    """Audio router instance."""
    return AudioRouter("http://vyrex-proxy:8105", mock_stt, mock_tts)


@pytest.mark.asyncio
async def test_route_calls_all_stages(router, mock_stt, mock_tts):
    """Test route calls STT, agent, and TTS."""
    with patch("audio_router.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Timer set for 5 minutes."}}]
        }
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await router.route(b"\x00" * 1000, 16000)

        assert isinstance(result, RouterResult)
        mock_stt.transcribe.assert_called_once()
        mock_client.post.assert_called_once()
        mock_tts.synthesize.assert_called_once()


@pytest.mark.asyncio
async def test_route_returns_latencies(router, mock_stt, mock_tts):
    """Test route includes latency fields."""
    with patch("audio_router.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "response"}}]
        }
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await router.route(b"\x00" * 1000, 16000)

        assert result.stt_latency_ms >= 0
        assert result.agent_latency_ms >= 0
        assert result.tts_latency_ms >= 0
        assert result.total_latency_ms >= 0
        # Total should be >= sum of parts (roughly)
        assert result.total_latency_ms >= (
            result.stt_latency_ms + result.agent_latency_ms + result.tts_latency_ms - 100
        )


@pytest.mark.asyncio
async def test_route_stt_failure_raises(router, mock_stt, mock_tts):
    """Test STT failure raises VoicePipelineError."""
    mock_stt.transcribe.side_effect = RuntimeError("STT error")

    with pytest.raises(VoicePipelineError, match="STT failed"):
        await router.route(b"\x00" * 1000, 16000)


@pytest.mark.asyncio
async def test_route_tts_failure_raises(router, mock_stt, mock_tts):
    """Test TTS failure raises VoicePipelineError."""
    mock_tts.synthesize.side_effect = RuntimeError("TTS error")

    with patch("audio_router.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "response"}}]
        }
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(VoicePipelineError, match="TTS failed"):
            await router.route(b"\x00" * 1000, 16000)


@pytest.mark.asyncio
async def test_route_empty_transcript_raises(router, mock_stt, mock_tts):
    """Test empty transcript raises error."""
    mock_stt.transcribe.return_value = STTResult(
        transcript="", confidence=0.0, language="", duration_ms=0
    )

    with pytest.raises(VoicePipelineError, match="No speech"):
        await router.route(b"\x00" * 1000, 16000)


@pytest.mark.asyncio
async def test_route_custom_system_prompt(router, mock_stt, mock_tts):
    """Test custom system prompt passed to agent."""
    with patch("audio_router.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "response"}}]
        }
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        custom_prompt = "Be concise"
        await router.route(b"\x00" * 1000, 16000, system_prompt=custom_prompt)

        # Check that custom prompt was included in POST
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        system_msg = payload["messages"][0]["content"]
        assert custom_prompt in system_msg


@pytest.mark.asyncio
async def test_route_agent_http_error_doesnt_crash(router, mock_stt, mock_tts):
    """Test agent HTTP error doesn't crash, includes error in response."""
    with patch("audio_router.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.HTTPError("Agent unreachable")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await router.route(b"\x00" * 1000, 16000)

        # Should include error message in agent_response
        assert "[Error:" in result.agent_response
        assert result.agent_latency_ms >= 0


@pytest.mark.asyncio
async def test_route_transcript_included(router, mock_stt, mock_tts):
    """Test route result includes transcript."""
    with patch("audio_router.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "response"}}]
        }
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await router.route(b"\x00" * 1000, 16000)

        assert result.transcript == "set a timer for 5 minutes"


@pytest.mark.asyncio
async def test_route_response_included(router, mock_stt, mock_tts):
    """Test route result includes agent response."""
    with patch("audio_router.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Agent response text"}}]
        }
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await router.route(b"\x00" * 1000, 16000)

        assert result.agent_response == "Agent response text"


@pytest.mark.asyncio
async def test_route_audio_bytes_included(router, mock_stt, mock_tts):
    """Test route result includes TTS audio bytes."""
    with patch("audio_router.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "response"}}]
        }
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await router.route(b"\x00" * 1000, 16000)

        assert result.audio_bytes == b"\x00" * 4410
