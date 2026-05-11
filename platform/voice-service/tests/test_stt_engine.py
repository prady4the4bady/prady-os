"""Tests for STT Engine."""
from __future__ import annotations

import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stt_engine import STTEngine, STTResult


@pytest.fixture
def tmp_models_dir(tmp_path):
    """Temporary models directory."""
    models_dir = tmp_path / "whisper"
    models_dir.mkdir(parents=True)
    return str(models_dir)


@pytest.fixture
def stt_engine(tmp_models_dir):
    """STT engine instance."""
    return STTEngine(model_size="base", models_dir=tmp_models_dir)


def test_load_model(stt_engine):
    """Test loading Whisper model."""
    with patch("stt_engine.WhisperModel") as mock_model:
        mock_instance = MagicMock()
        mock_model.return_value = mock_instance

        stt_engine.load()

        assert stt_engine._loaded is True
        assert stt_engine._model is not None
        mock_model.assert_called_once()


def test_load_model_idempotent(stt_engine):
    """Test that load() is idempotent."""
    with patch("stt_engine.WhisperModel") as mock_model:
        mock_instance = MagicMock()
        mock_model.return_value = mock_instance

        stt_engine.load()
        stt_engine.load()

        # Should only be called once
        assert mock_model.call_count == 1


def test_transcribe_returns_text(stt_engine, tmp_models_dir):
    """Test transcription returns text."""
    # Create sample audio (1 second of silence)
    sample_rate = 16000
    duration_s = 1.0
    num_samples = int(sample_rate * duration_s)
    audio_int16 = np.zeros(num_samples, dtype=np.int16)
    audio_bytes = audio_int16.tobytes()

    with patch("stt_engine.WhisperModel") as mock_model_class:
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model

        # Mock transcribe to return fake segment
        mock_segment = MagicMock()
        mock_segment.text = "hello world"
        mock_segment.no_speech_prob = 0.1

        mock_info = MagicMock()
        mock_info.language = "en"

        mock_model.transcribe.return_value = ([mock_segment], mock_info)

        stt_engine.load()
        result = stt_engine.transcribe(audio_bytes, sample_rate)

        assert isinstance(result, STTResult)
        assert "hello world" in result.transcript
        assert result.confidence > 0.0
        assert result.language == "en"
        assert result.duration_ms > 0


def test_transcribe_empty_audio(stt_engine):
    """Test transcription with empty audio."""
    with patch("stt_engine.WhisperModel") as mock_model_class:
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model

        stt_engine.load()
        result = stt_engine.transcribe(b"", 16000)

        assert result.transcript == ""
        assert result.confidence == pytest.approx(0.0)
        assert result.duration_ms == 0


def test_transcribe_before_load_raises(stt_engine):
    """Test transcription before loading raises error."""
    audio_bytes = b"\x00" * 1000
    with pytest.raises(RuntimeError, match="not loaded"):
        stt_engine.transcribe(audio_bytes)


def test_transcribe_confidence_calculation(stt_engine):
    """Test confidence is calculated from segments."""
    sample_rate = 16000
    audio_bytes = b"\x00" * (sample_rate * 2)  # 1 second silence

    with patch("stt_engine.WhisperModel") as mock_model_class:
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model

        # Create multiple segments with different confidence
        seg1 = MagicMock()
        seg1.text = "segment"
        seg1.no_speech_prob = 0.1  # 90% confidence

        seg2 = MagicMock()
        seg2.text = "two"
        seg2.no_speech_prob = 0.2  # 80% confidence

        mock_info = MagicMock()
        mock_info.language = "en"

        mock_model.transcribe.return_value = ([seg1, seg2], mock_info)

        stt_engine.load()
        result = stt_engine.transcribe(audio_bytes, sample_rate)

        # Average should be (0.9 + 0.8) / 2 = 0.85
        assert result.confidence == pytest.approx(0.85, abs=0.01)


def test_stt_result_fields():
    """Test STTResult has all required fields."""
    result = STTResult(
        transcript="test",
        confidence=0.95,
        language="en",
        duration_ms=1000,
    )
    assert result.transcript == "test"
    assert result.confidence == pytest.approx(0.95)
    assert result.language == "en"
    assert result.duration_ms == 1000


def test_model_size_in_cache_path(tmp_models_dir):
    """Test model size is used in cache path."""
    engine_small = STTEngine(model_size="small", models_dir=tmp_models_dir)
    engine_large = STTEngine(model_size="large", models_dir=tmp_models_dir)

    assert "small" in str(engine_small.models_dir)
    assert "large" in str(engine_large.models_dir)


def test_transcribe_handles_model_error(stt_engine):
    """Test transcribe handles model errors gracefully."""
    with patch("stt_engine.WhisperModel") as mock_model_class:
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        mock_model.transcribe.side_effect = RuntimeError("Model error")

        stt_engine.load()
        with pytest.raises(RuntimeError):
            stt_engine.transcribe(b"\x00" * 1000)
