"""TTS Engine – piper-tts text-to-speech wrapper."""
from __future__ import annotations

import logging
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TTSResult:
    """Text-to-speech result."""
    audio_bytes: bytes
    duration_ms: int
    voice: str
    text_length: int


class TTSEngine:
    """Piper TTS engine."""

    def __init__(
        self,
        voice: str = "en_US-lessac-medium",
        models_dir: str | None = None,
        bin_dir: str | None = None,
    ):
        self.voice = voice
        self.models_dir = Path(models_dir or Path.home() / ".kryos" / "models" / "tts")
        self.bin_dir = Path(bin_dir or Path.home() / ".kryos" / "bin")
        self._loaded = False
        self._piper_path = self.bin_dir / "piper"

    def load(self) -> None:
        """Check piper binary and model availability."""
        if self._loaded:
            return

        # Check piper binary exists (in docker it will)
        if not self._piper_path.exists():
            logger.warning(f"Piper binary not found at {self._piper_path}, will fail gracefully on synthesize()")
            # Don't raise here - fail-open on synthesize
            self._loaded = True
            return

        # Check model file exists
        model_path = self.models_dir / f"{self.voice}.onnx"
        if not model_path.exists():
            logger.warning(f"Piper model not found: {model_path}")
            # Fail-open: we'll return silence WAV on synthesize

        self._loaded = True
        logger.info(f"TTS engine ready with voice: {self.voice}")

    def synthesize(self, text: str) -> TTSResult:
        """Synthesize text to audio.

        Never raises - returns silence WAV on any error (fail-open).

        Args:
            text: Text to synthesize

        Returns:
            TTSResult with audio_bytes (WAV format, 22050 Hz, 16-bit mono)
        """
        if not self._loaded:
            logger.warning("TTS not loaded, returning silence")
            return self._silence_wav(text_length=len(text), voice=self.voice)

        if not text:
            return TTSResult(audio_bytes=self._raw_wav(b""), duration_ms=0, voice=self.voice, text_length=0)

        try:
            model_path = self.models_dir / f"{self.voice}.onnx"
            
            # Call piper
            result = subprocess.run(
                [str(self._piper_path), "--model", str(model_path), "--output_raw"],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=10.0,
            )

            if result.returncode != 0:
                logger.warning(f"Piper failed: {result.stderr.decode('utf-8', errors='ignore')}")
                return self._silence_wav(text_length=len(text), voice=self.voice)

            # result.stdout is raw PCM (22050 Hz, 16-bit mono, little-endian)
            audio_bytes = self._raw_wav(result.stdout)
            duration_ms = len(result.stdout) // 2 // 22050 * 1000  # 16-bit = 2 bytes per sample

            return TTSResult(
                audio_bytes=audio_bytes,
                duration_ms=duration_ms,
                voice=self.voice,
                text_length=len(text),
            )
        except Exception as e:
            logger.warning(f"Synthesis failed: {e}, returning silence")
            return self._silence_wav(text_length=len(text), voice=self.voice)

    @staticmethod
    def _raw_wav(pcm_data: bytes) -> bytes:
        """Wrap raw PCM in WAV header (22050 Hz, 16-bit mono, little-endian)."""
        sample_rate = 22050
        channels = 1
        bytes_per_sample = 2
        byte_rate = sample_rate * channels * bytes_per_sample
        block_align = channels * bytes_per_sample

        # WAV header
        wav_header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + len(pcm_data),
            b"WAVE",
            b"fmt ",
            16,  # subchunk1size
            1,  # PCM
            channels,
            sample_rate,
            byte_rate,
            block_align,
            16,  # bits per sample
            b"data",
            len(pcm_data),
        )
        return wav_header + pcm_data

    @staticmethod
    def _silence_wav(
        duration_seconds: float = 1.0,
        *,
        text_length: int = 0,
        voice: str = "silence",
    ) -> TTSResult:
        """Generate silence WAV (~100ms)."""
        sample_rate = 22050
        duration_ms = 100
        samples = int((duration_ms / 1000.0) * sample_rate)
        silence_pcm = b"\x00" * (samples * 2)

        return TTSResult(
            audio_bytes=TTSEngine._raw_wav(silence_pcm),
            duration_ms=duration_ms,
            voice=voice,
            text_length=text_length,
        )
