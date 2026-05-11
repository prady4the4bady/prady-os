"""Tests for TTS Engine."""
from __future__ import annotations

import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tts_engine import TTSEngine, TTSResult


@pytest.fixture
def tmp_models_dir(tmp_path):
    """Temporary models directory."""
    models_dir = tmp_path / "tts"
    models_dir.mkdir(parents=True)
    return str(models_dir)


@pytest.fixture
def tts_engine(tmp_models_dir):
    """TTS engine instance."""
    return TTSEngine(voice="en_US-amy-medium", models_dir=tmp_models_dir, bin_dir=str(Path(tmp_models_dir).parent))


def test_synthesize_returns_bytes(tts_engine):
    """Test synthesize returns bytes."""
    tts_engine.load()
    result = tts_engine.synthesize("hello world")

    assert isinstance(result, TTSResult)
    assert isinstance(result.audio_bytes, bytes)
    assert result.audio_bytes.startswith(b"RIFF")  # WAV header
    assert len(result.audio_bytes) >= 44  # Minimum WAV size


def test_piper_unavailable_returns_silence(tts_engine):
    """Test that missing piper returns silence WAV."""
    # Don't call load, so piper path is invalid
    result = tts_engine.synthesize("hello world")

    # Should return silence WAV (not raise)
    assert isinstance(result.audio_bytes, bytes)
    assert result.audio_bytes.startswith(b"RIFF")


def test_synthesize_never_raises(tts_engine):
    """Test synthesize never raises on any error."""
    tts_engine.load()

    # Try with various inputs that might cause issues
    try:
        result1 = tts_engine.synthesize("")
        assert isinstance(result1.audio_bytes, bytes)

        result2 = tts_engine.synthesize("test")
        assert isinstance(result2.audio_bytes, bytes)

        result3 = tts_engine.synthesize("a" * 10000)  # Very long text
        assert isinstance(result3.audio_bytes, bytes)
    except Exception as e:
        pytest.fail(f"synthesize() raised exception: {e}")


def test_synthesize_returns_tts_result():
    """Test synthesize returns all TTS result fields."""
    engine = TTSEngine()
    engine.load()
    result = engine.synthesize("test text")

    assert hasattr(result, "audio_bytes")
    assert hasattr(result, "duration_ms")
    assert hasattr(result, "voice")
    assert hasattr(result, "text_length")


def test_load_idempotent(tts_engine):
    """Test that load() is idempotent."""
    tts_engine.load()
    tts_engine.load()
    assert tts_engine._loaded is True


def test_empty_text_returns_empty_audio(tts_engine):
    """Test empty text returns empty audio bytes."""
    tts_engine.load()
    result = tts_engine.synthesize("")

    assert result.text_length == 0
    # WAV header should still be there
    assert result.audio_bytes.startswith(b"RIFF")


def test_voice_in_result(tts_engine):
    """Test voice name is included in result."""
    tts_engine.load()
    result = tts_engine.synthesize("hello")

    assert result.voice == "en_US-amy-medium"


def test_text_length_in_result(tts_engine):
    """Test text length is tracked in result."""
    tts_engine.load()
    text = "hello world"
    result = tts_engine.synthesize(text)

    assert result.text_length == len(text)


def test_duration_calculation(tts_engine):
    """Test duration is calculated from audio size."""
    tts_engine.load()
    result = tts_engine.synthesize("test")

    # Duration should be based on audio size
    # 22050 Hz, 16-bit = 2 bytes per sample
    # WAV header is 44 bytes
    pcm_bytes = result.audio_bytes[44:]
    expected_samples = len(pcm_bytes) // 2
    expected_duration_ms = int((expected_samples / 22050) * 1000)

    # Allow some tolerance
    assert abs(result.duration_ms - expected_duration_ms) <= 10


def test_raw_wav_format():
    """Test WAV wrapping format."""
    # Create test PCM data
    pcm = b"\x00\x00" * 1000  # 1000 samples of silence

    wav = TTSEngine._raw_wav(pcm)

    # Check WAV header format
    assert wav[:4] == b"RIFF"  # RIFF marker
    assert wav[8:12] == b"WAVE"  # WAVE marker
    assert b"fmt " in wav  # Format subchunk
    assert b"data" in wav  # Data subchunk

    # Check content is preserved
    assert wav[-len(pcm):] == pcm


def test_silence_wav():
    """Test silence WAV generation."""
    result = TTSEngine._silence_wav(0.1)

    assert result.audio_bytes.startswith(b"RIFF")
    assert result.duration_ms == 100
    assert result.voice == "silence"
    assert result.text_length == 0
    assert len(result.audio_bytes) > 44  # More than just header
