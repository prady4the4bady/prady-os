"""Audio Router – STT → Vyrex → TTS pipeline."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from stt_engine import STTEngine, STTResult
from tts_engine import TTSEngine, TTSResult

logger = logging.getLogger(__name__)


class VoicePipelineError(Exception):
    """Voice pipeline error."""
    pass


@dataclass
class RouterResult:
    """Audio routing result."""
    transcript: str
    agent_response: str
    audio_bytes: bytes
    total_latency_ms: int
    stt_latency_ms: int
    agent_latency_ms: int
    tts_latency_ms: int


class AudioRouter:
    """Routes audio through STT → Agent → TTS pipeline."""

    def __init__(
        self,
        vyrex_url: str,
        stt: STTEngine,
        tts: TTSEngine,
    ):
        self.vyrex_url = vyrex_url
        self.stt = stt
        self.tts = tts

    async def route(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        system_prompt: str | None = None,
    ) -> RouterResult:
        """Route audio through full pipeline.

        Args:
            audio_bytes: Raw PCM audio
            sample_rate: Sample rate (Hz)
            system_prompt: Optional system prompt for agent

        Returns:
            RouterResult with transcript, response, audio, and latencies
        """
        start_time = time.time()

        # ── STT ─────────────────────────────────────────────────────────────
        try:
            stt_start = time.time()
            stt_result: STTResult = self.stt.transcribe(audio_bytes, sample_rate)
            stt_latency_ms = int((time.time() - stt_start) * 1000)
        except Exception as e:
            raise VoicePipelineError(f"STT failed: {e}") from e

        if not stt_result.transcript:
            raise VoicePipelineError("No speech detected")

        # ── Vyrex Agent ───────────────────────────────────────────────────
        try:
            agent_start = time.time()
            system = system_prompt or (
                "You are Kryos, a helpful AI OS assistant. "
                "Reply concisely in 1-2 sentences."
            )

            payload = {
                "model": "active",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": stt_result.transcript},
                ],
                "max_tokens": 150,
                "stream": False,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.vyrex_url}/v1/chat/completions",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            agent_response = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            agent_latency_ms = int((time.time() - agent_start) * 1000)
        except Exception as e:
            logger.error(f"Agent call failed: {e}")
            agent_response = f"[Error: {str(e)[:30]}]"
            agent_latency_ms = int((time.time() - agent_start) * 1000)

        # ── TTS ──────────────────────────────────────────────────────────────
        try:
            tts_start = time.time()
            tts_result: TTSResult = self.tts.synthesize(agent_response)
            tts_latency_ms = int((time.time() - tts_start) * 1000)
        except Exception as e:
            raise VoicePipelineError(f"TTS failed: {e}") from e

        total_latency_ms = int((time.time() - start_time) * 1000)

        return RouterResult(
            transcript=stt_result.transcript,
            agent_response=agent_response,
            audio_bytes=tts_result.audio_bytes,
            total_latency_ms=total_latency_ms,
            stt_latency_ms=stt_latency_ms,
            agent_latency_ms=agent_latency_ms,
            tts_latency_ms=tts_latency_ms,
        )
