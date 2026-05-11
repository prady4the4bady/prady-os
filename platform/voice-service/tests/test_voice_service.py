"""Tests for Voice Service FastAPI endpoints."""
from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from audio_router import RouterResult
from stt_engine import STTResult
from tts_engine import TTSResult
from voice_service import app, _stt_engine, _tts_engine, _router, _wake_detector


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_stt_result():
    """Mock STT result."""
    return STTResult(
        transcript="hello world",
        confidence=0.95,
        language="en",
        duration_ms=1000,
    )


@pytest.fixture
def mock_tts_result():
    """Mock TTS result."""
    return TTSResult(
        audio_bytes=b"RIFF" + b"\x00" * 100,
        duration_ms=500,
        voice="en_US-amy-medium",
        text_length=11,
    )


@pytest.fixture
def audio_b64():
    """Base64 encoded audio chunk."""
    return base64.b64encode(b"\x00" * 1000).decode("utf-8")


def test_health_endpoint(client):
    """Test health endpoint."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_status_endpoint(client):
    """Test status endpoint returns correct schema."""
    resp = client.get("/voice/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "listening" in data
    assert "wake_word_detected" in data
    assert "last_transcript" in data
    assert "last_response" in data


def test_transcribe_endpoint(client, audio_b64, mock_stt_result):
    """Test transcribe endpoint."""
    with patch.object(_stt_engine, "transcribe", return_value=mock_stt_result):
        resp = client.post(
            "/voice/transcribe",
            json={"audio_base64": audio_b64, "sample_rate": 16000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["transcript"] == "hello world"
        assert data["confidence"] == pytest.approx(0.95)


def test_transcribe_empty_audio_rejected(client):
    """Test transcribe rejects empty audio."""
    resp = client.post("/voice/transcribe", json={"audio_base64": ""})
    assert resp.status_code == 400


def test_transcribe_invalid_base64_rejected(client):
    """Test transcribe rejects invalid base64."""
    resp = client.post(
        "/voice/transcribe",
        json={"audio_base64": "!!!invalid!!!"},
    )
    assert resp.status_code == 400


def test_speak_endpoint(client, mock_tts_result):
    """Test speak (TTS) endpoint."""
    with patch.object(_tts_engine, "synthesize", return_value=mock_tts_result):
        resp = client.post("/voice/speak", json={"text": "hello world"})
        assert resp.status_code == 200
        data = resp.json()
        assert "audio_base64" in data
        assert data["duration_ms"] == 500


def test_speak_empty_text_rejected(client):
    """Test speak rejects empty text."""
    resp = client.post("/voice/speak", json={"text": ""})
    assert resp.status_code == 400


def test_pipeline_endpoint(client, audio_b64):
    """Test full pipeline endpoint."""
    with patch.object(
        _router,
        "route",
        return_value=AsyncMock(
            return_value=RouterResult(
                transcript="set timer",
                agent_response="Timer set",
                audio_bytes=b"\x00" * 100,
                total_latency_ms=500,
                stt_latency_ms=100,
                agent_latency_ms=200,
                tts_latency_ms=200,
            )
        ),
    ):
        resp = client.post(
            "/voice/pipeline",
            json={"audio_base64": audio_b64, "sample_rate": 16000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["transcript"] == "set timer"
        assert data["response_text"] == "Timer set"
        assert "audio_base64" in data
        assert data["total_latency_ms"] == 500


def test_pipeline_empty_audio_rejected(client):
    """Test pipeline rejects empty audio."""
    resp = client.post("/voice/pipeline", json={"audio_base64": ""})
    assert resp.status_code == 400


def test_list_stt_models(client):
    """Test list STT models endpoint."""
    resp = client.get("/voice/models/stt")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "tiny" in data["models"]
    assert "base" in data["models"]
    assert "small" in data["models"]
    assert "medium" in data["models"]
    assert "large" in data["models"]


def test_list_tts_models(client):
    """Test list TTS models endpoint."""
    resp = client.get("/voice/models/tts")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert len(data["models"]) > 0


def test_activate_stt_model_valid(client):
    """Test activate STT model with valid size."""
    with patch("voice_service.STTEngine") as mock_engine_class:
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        resp = client.post("/voice/models/stt/activate", json={"model_size": "small"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "small"
        assert data["status"] == "loaded"


def test_activate_stt_model_invalid_size(client):
    """Test activate STT model with invalid size."""
    resp = client.post("/voice/models/stt/activate", json={"model_size": "xxl"})
    assert resp.status_code == 422


def test_activate_tts_voice(client):
    """Test activate TTS voice."""
    with patch("voice_service.TTSEngine") as mock_engine_class:
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        resp = client.post(
            "/voice/models/tts/activate",
            json={"voice": "en_US-lessac-medium"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["voice"] == "en_US-lessac-medium"
        assert data["status"] == "loaded"


def test_start_listening(client):
    """Test start listening endpoint."""
    with patch.object(_wake_detector, "start"):
        resp = client.post("/voice/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["listening"] is True


def test_stop_listening(client):
    """Test stop listening endpoint."""
    with patch.object(_wake_detector, "stop"):
        resp = client.post("/voice/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["listening"] is False


def test_websocket_stream(client, audio_b64, mock_stt_result):
    """Test WebSocket stream endpoint."""
    with patch.object(_stt_engine, "transcribe", return_value=mock_stt_result):
        with client.websocket_connect("/voice/stream") as websocket:
            # Send audio chunk
            websocket.send_text(
                json.dumps({
                    "type": "audio_chunk",
                    "data": audio_b64,
                    "sample_rate": 16000,
                })
            )

            # Receive transcript
            data = json.loads(websocket.receive_text())
            assert data["type"] == "transcript"
            assert data["text"] == "hello world"
            assert data["confidence"] == pytest.approx(0.95)


def test_websocket_error_handling(client):
    """Test WebSocket error handling."""
    with patch.object(_stt_engine, "transcribe", side_effect=Exception("transcription failed")):
        with client.websocket_connect("/voice/stream") as websocket:
            websocket.send_text(
                json.dumps({
                    "type": "audio_chunk",
                    "data": base64.b64encode(b"\x00" * 1000).decode("utf-8"),
                })
            )

            # Should receive error message
            data = json.loads(websocket.receive_text())
            assert data["type"] == "error"
            assert "failed" in data["message"].lower()


def test_transcribe_returns_confidence(client, audio_b64, mock_stt_result):
    """Test transcribe endpoint includes confidence."""
    with patch.object(_stt_engine, "transcribe", return_value=mock_stt_result):
        resp = client.post(
            "/voice/transcribe",
            json={"audio_base64": audio_b64},
        )
        assert resp.status_code == 200
        assert resp.json()["confidence"] == pytest.approx(0.95)


def test_models_list_non_empty(client):
    """Test model lists are non-empty."""
    resp_stt = client.get("/voice/models/stt")
    resp_tts = client.get("/voice/models/tts")

    assert len(resp_stt.json()["models"]) > 0
    assert len(resp_tts.json()["models"]) > 0
