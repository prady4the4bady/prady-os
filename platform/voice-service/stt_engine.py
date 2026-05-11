"""STT Engine – faster-whisper speech-to-text wrapper."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore


@dataclass
class STTResult:
    """Speech-to-text result."""
    transcript: str
    confidence: float
    language: str
    duration_ms: int


class STTEngine:
    """Faster-Whisper STT engine."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        models_dir: str | None = None,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.base_models_dir = Path(models_dir or Path.home() / ".kryos" / "models" / "whisper")
        self.models_dir = self.base_models_dir / self.model_size
        self._model = None
        self._loaded = False

    def load(self) -> None:
        """Load the Whisper model."""
        if self._loaded:
            return

        if WhisperModel is None:
            raise RuntimeError("faster-whisper not installed")

        cache_dir = self.models_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(self.base_models_dir),
            )
            self._loaded = True
            logger.info(f"Loaded Whisper model: {self.model_size}")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise RuntimeError(f"Failed to load Whisper model: {e}") from e

    def transcribe(
        self, audio_bytes: bytes, sample_rate: int = 16000
    ) -> STTResult:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw PCM audio data (int16 LE)
            sample_rate: Sample rate of audio (default 16000 Hz)

        Returns:
            STTResult with transcript, confidence, language, duration
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        if not audio_bytes:
            return STTResult(transcript="", confidence=0.0, language="", duration_ms=0)

        # Convert bytes to numpy float32 array
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        # Transcribe
        try:
            segments, info = self._model.transcribe(audio_float32, fp16=False, language="en")
            segments_list = list(segments)

            if not segments_list:
                return STTResult(transcript="", confidence=0.0, language=info.language or "", duration_ms=0)

            # Combine all segments
            transcript = " ".join(seg.text for seg in segments_list)
            
            # Calculate average confidence from segment probabilities
            if segments_list and hasattr(segments_list[0], 'no_speech_prob'):
                confidence = float(
                    np.mean([1.0 - seg.no_speech_prob for seg in segments_list])
                )
            else:
                confidence = 0.95  # Default high confidence if not available

            duration_ms = int((len(audio_float32) / sample_rate) * 1000)

            return STTResult(
                transcript=transcript.strip(),
                confidence=confidence,
                language=info.language or "en",
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}") from e
