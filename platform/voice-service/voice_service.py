"""Voice Service – FastAPI microservice for voice I/O (port 8012).

Provides speech-to-text, text-to-speech, and wake-word detection
with offline-first capabilities and Vyrex agent integration.
"""
from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

_SHARED_PATH = Path(__file__).resolve().parents[1] / "shared"
if str(_SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(_SHARED_PATH))

from auth_middleware import require_auth

from audio_router import AudioRouter, RouterResult, VoicePipelineError
from stt_engine import STTEngine
from tts_engine import TTSEngine
from wake_word_detector import WakeWordDetector

# ── Configuration ────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VYREX_URL = os.environ.get("VYREX_URL", "http://vyrex-proxy:8105")
SECURITY_POLICY_URL = os.environ.get("SECURITY_POLICY_URL", "http://security-policy:8117")
AUDIT_LOG_URL = os.environ.get("AUDIT_LOG_URL", "http://audit-log:8112")

WAKE_WORD = os.environ.get("WAKE_WORD", "hey_kryos")
WAKE_WORD_THRESHOLD = float(os.environ.get("WAKE_WORD_THRESHOLD", "0.5"))

DEFAULT_STT_MODEL = os.environ.get("DEFAULT_STT_MODEL", "base")
DEFAULT_TTS_VOICE = os.environ.get("DEFAULT_TTS_VOICE", "en_US-lessac-medium")

MODELS_DIR = Path(os.environ.get("MODELS_DIR", Path.home() / ".kryos" / "models"))


# ── State ────────────────────────────────────────────────────────────────────
_stt_engine = STTEngine(model_size=DEFAULT_STT_MODEL, models_dir=str(MODELS_DIR / "whisper"))
_tts_engine = TTSEngine(voice=DEFAULT_TTS_VOICE, models_dir=str(MODELS_DIR / "tts"))
_wake_detector = WakeWordDetector(wake_word=WAKE_WORD, threshold=WAKE_WORD_THRESHOLD)
_router = AudioRouter(VYREX_URL, _stt_engine, _tts_engine)

_listening = False
_wake_word_detections = 0
_last_transcript = ""
_last_response = ""


# ── Request/Response Models ──────────────────────────────────────────────────
class TranscribeRequest(BaseModel):
    audio_base64: str
    sample_rate: int = 16000


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = DEFAULT_TTS_VOICE


class PipelineRequest(BaseModel):
    audio_base64: str
    sample_rate: int = 16000
    system_prompt: str | None = None


class StatusResponse(BaseModel):
    listening: bool
    wake_word_detected: int
    last_transcript: str
    last_response: str


class TranscribeResponse(BaseModel):
    transcript: str
    confidence: float


class SynthesizeResponse(BaseModel):
    audio_base64: str
    duration_ms: int


class PipelineResponse(BaseModel):
    transcript: str
    response_text: str
    audio_base64: str
    total_latency_ms: int


class ModelSizeRequest(BaseModel):
    model_size: str


class VoiceRequest(BaseModel):
    voice: str


async def _emit_audit_event(event_type: str, data: dict[str, Any]) -> None:
    """Emit audit log event (fail-open)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {
                "event_type": f"voice_{event_type}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            }
            await client.post(f"{AUDIT_LOG_URL}/events", json=payload)
    except Exception as e:
        logger.warning(f"Failed to emit audit event: {e}")


async def _check_policy(permission: str) -> bool:
    """Check security policy (fail-open)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{SECURITY_POLICY_URL}/policies/check",
                json={"subject_type": "service", "subject_id": "voice-service", "permission": permission},
            )
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Policy check failed, allowing: {e}")
        return True


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Startup and shutdown."""
    logger.info("Voice service starting...")
    try:
        _stt_engine.load()
        _tts_engine.load()
        logger.info("Voice engines loaded successfully")
    except Exception as e:
        logger.warning(f"Failed to load engines: {e} (will retry on first use)")
    yield
    logger.info("Voice service shutting down...")


app = FastAPI(
    title="Kryos Voice Service",
    version="1.0.0",
    description="Speech-to-text, text-to-speech, and voice pipeline",
    lifespan=lifespan,
)


# ── Health & Status ──────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> JSONResponse:
    """Health check."""
    return JSONResponse({"status": "ok"})


@app.get("/voice/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Get voice service status."""
    return StatusResponse(
        listening=_listening,
        wake_word_detected=_wake_word_detections,
        last_transcript=_last_transcript,
        last_response=_last_response,
    )


# ── STT Endpoints ────────────────────────────────────────────────────────────
@app.post("/voice/transcribe", response_model=TranscribeResponse)
async def transcribe(
    req: TranscribeRequest,
    _current_user: dict[str, Any] = Depends(require_auth),
) -> TranscribeResponse:
    """Transcribe audio to text."""
    if not req.audio_base64:
        raise HTTPException(status_code=400, detail="audio_base64 required")

    try:
        audio_bytes = base64.b64decode(req.audio_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")

    try:
        result = _stt_engine.transcribe(audio_bytes, req.sample_rate)
        return TranscribeResponse(transcript=result.transcript, confidence=result.confidence)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")


# ── TTS Endpoints ────────────────────────────────────────────────────────────
@app.post("/voice/speak", response_model=SynthesizeResponse)
async def speak(
    req: SynthesizeRequest,
    _current_user: dict[str, Any] = Depends(require_auth),
) -> SynthesizeResponse:
    """Synthesize text to speech."""
    if not req.text:
        raise HTTPException(status_code=400, detail="text required")

    try:
        result = _tts_engine.synthesize(req.text)
        audio_b64 = base64.b64encode(result.audio_bytes).decode("utf-8")
        return SynthesizeResponse(audio_base64=audio_b64, duration_ms=result.duration_ms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {e}")


@app.post("/voice/synthesize", response_model=SynthesizeResponse)
async def synthesize_alias(
    req: SynthesizeRequest,
    current_user: dict[str, Any] = Depends(require_auth),
) -> SynthesizeResponse:
    _ = current_user
    return await speak(req)


# ── Pipeline Endpoint ────────────────────────────────────────────────────────
@app.post("/voice/pipeline", response_model=PipelineResponse)
async def pipeline(req: PipelineRequest) -> PipelineResponse:
    """One-shot: transcribe → agent → speak."""
    if not req.audio_base64:
        raise HTTPException(status_code=400, detail="audio_base64 required")

    try:
        audio_bytes = base64.b64decode(req.audio_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")

    try:
        route_result = _router.route(audio_bytes, req.sample_rate, req.system_prompt)
        resolved_result = await route_result if inspect.isawaitable(route_result) else route_result
        if callable(resolved_result) and not isinstance(resolved_result, RouterResult):
            maybe_next = resolved_result()
            resolved_result = await maybe_next if inspect.isawaitable(maybe_next) else maybe_next
        result = await resolved_result if inspect.isawaitable(resolved_result) else resolved_result
        audio_b64 = base64.b64encode(result.audio_bytes).decode("utf-8")

        # Emit audit event
        await _emit_audit_event(
            "pipeline_complete",
            {
                "transcript": result.transcript,
                "response_preview": result.agent_response[:50],
                "total_latency_ms": result.total_latency_ms,
                "stt_model": DEFAULT_STT_MODEL,
                "tts_voice": DEFAULT_TTS_VOICE,
            },
        )

        return PipelineResponse(
            transcript=result.transcript,
            response_text=result.agent_response,
            audio_base64=audio_b64,
            total_latency_ms=result.total_latency_ms,
        )
    except VoicePipelineError as e:
        await _emit_audit_event("pipeline_error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        await _emit_audit_event("pipeline_error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")


# ── Model Management ─────────────────────────────────────────────────────────
@app.get("/voice/models/stt")
async def list_stt_models() -> dict[str, list[str]]:
    """List available Whisper model sizes."""
    return {"models": ["tiny", "base", "small", "medium", "large"]}


@app.get("/voice/models/tts")
async def list_tts_models() -> dict[str, list[str]]:
    """List available Piper voices."""
    return {
        "models": [
            "en_US-lessac-medium",
            "en_US-amy-medium",
            "en_US-libritts_high-medium",
        ]
    }


@app.post("/voice/models/stt/activate")
async def activate_stt_model(req: ModelSizeRequest) -> JSONResponse:
    """Activate STT model."""
    valid_sizes = ["tiny", "base", "small", "medium", "large"]
    if req.model_size not in valid_sizes:
        raise HTTPException(status_code=422, detail=f"Invalid size: {req.model_size}")

    try:
        global _stt_engine
        _stt_engine = STTEngine(
            model_size=req.model_size,
            models_dir=str(MODELS_DIR / "whisper"),
        )
        _stt_engine.load()
        return JSONResponse({"model": req.model_size, "status": "loaded"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load model: {e}")


@app.post("/voice/models/tts/activate")
async def activate_tts_model(req: VoiceRequest) -> JSONResponse:
    """Activate TTS voice."""
    try:
        global _tts_engine
        _tts_engine = TTSEngine(
            voice=req.voice,
            models_dir=str(MODELS_DIR / "tts"),
        )
        _tts_engine.load()
        return JSONResponse({"voice": req.voice, "status": "loaded"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load voice: {e}")


# ── Wake Word Control ────────────────────────────────────────────────────────
@app.post("/voice/start")
async def start_listening() -> JSONResponse:
    """Start wake-word listener."""
    global _listening

    if not await _check_policy("voice-activation"):
        raise HTTPException(status_code=403, detail="Voice activation not allowed by policy")

    async def on_wake_detected(keyword: str) -> None:
        global _wake_word_detections
        _wake_word_detections += 1
        await _emit_audit_event("wake_word_detected", {"keyword": keyword, "confidence": 0.95})

    try:
        _wake_detector.start(on_wake_detected)
        _listening = True
        return JSONResponse({"status": "listening", "listening": True})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start listening: {e}")


@app.post("/voice/stop")
async def stop_listening() -> JSONResponse:
    """Stop wake-word listener."""
    global _listening
    try:
        _wake_detector.stop()
        _listening = False
        return JSONResponse({"status": "stopped", "listening": False})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop: {e}")


# ── WebSocket Streaming ──────────────────────────────────────────────────────
@app.websocket("/voice/stream")
async def websocket_stream(websocket: WebSocket) -> None:
    """WebSocket for streaming audio.

    Client sends: {type: "audio_chunk", data: "<base64 PCM>"}
    Server sends: {type: "transcript", text: "...", confidence: 0.95}
                  {type: "response", text: "..."}
                  {type: "audio", data: "<base64 WAV>"}
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "audio_chunk":
                try:
                    audio_b64 = msg.get("data", "")
                    audio_bytes = base64.b64decode(audio_b64)

                    # Transcribe
                    stt_result = _stt_engine.transcribe(audio_bytes, msg.get("sample_rate", 16000))
                    await websocket.send_text(
                        json.dumps({
                            "type": "transcript",
                            "text": stt_result.transcript,
                            "confidence": stt_result.confidence,
                        })
                    )
                except Exception as e:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": str(e)})
                    )
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close(code=1011, reason=str(e))
