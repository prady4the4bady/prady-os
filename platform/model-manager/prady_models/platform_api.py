from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import requests
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from prady_models.benchmarking import run_benchmark
from prady_models.db import ModelRecord, SessionLocal, init_db
from prady_models.download import Downloader
from prady_models.metadata import extract_metadata
from prady_models.quantization import quantize_if_needed
from prady_models.schemas_api import BenchmarkResponse, ModelResponse, PullRequest

MODEL_STORAGE_DIR = Path(os.getenv("MODEL_STORAGE_DIR", str(Path.home() / ".nemos" / "models")))
MODEL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MODEL_GATEWAY_URL = os.getenv("MODEL_GATEWAY_URL", "http://localhost:11430")
_MODEL_NOT_FOUND = "model not found"


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _read_registry_fallback() -> list[dict[str, object]]:
    reg = Path(os.getenv("MODEL_REGISTRY_PATH", ""))
    if not reg.exists():
        return []
    with reg.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    return list(payload.get("models") or [])


def _extract_repo_file_hf(source: str) -> tuple[str, str, str | None]:
    """Return (repo, file_name, expected_sha)."""
    repo = source.removeprefix("hf://").strip("/")
    if not repo:
        raise ValueError("Invalid HuggingFace source")

    session = requests.Session()
    response = session.get(f"https://huggingface.co/api/models/{repo}", timeout=30)
    if response.status_code != 200:
        raise ValueError(f"HuggingFace repo not found: {repo}")
    payload = response.json()
    siblings = payload.get("siblings") or []

    preferred = next((s for s in siblings if str(s.get("rfilename", "")).lower().endswith(".gguf")), None)
    fallback = siblings[0] if siblings else None
    pick = preferred or fallback
    if pick is None:
        raise ValueError(f"No downloadable files found in {repo}")

    file_name = str(pick.get("rfilename"))
    lfs = pick.get("lfs") or {}
    expected = lfs.get("oid") if isinstance(lfs.get("oid"), str) else None
    return repo, file_name, expected.lower() if expected else None


def _parse_github_expected_sha(source: str) -> tuple[str, str | None]:
    if "#sha256=" in source:
        url, fragment = source.split("#sha256=", 1)
        return url, fragment.strip().lower() or None
    return source, None


def _serialize_model(record: ModelRecord) -> ModelResponse:
    return ModelResponse(
        model_id=record.model_id,
        name=record.name,
        source=record.source,
        file_path=record.file_path,
        sha256=record.sha256,
        quantization=record.quantization,
        size_gb=record.size_gb,
        pulled_at=record.pulled_at,
        status=record.status,
        benchmark_score=record.benchmark_score,
        tokens_per_sec=record.tokens_per_sec,
    )


def _build_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()
        yield

    return FastAPI(lifespan=lifespan)


app = _build_app()


def create_app() -> FastAPI:
    return app


downloader = Downloader()


async def _pull_model_events(body: PullRequest) -> AsyncGenerator[str, None]:
    source = body.source.strip()
    if not source:
        yield _sse("error", {"message": "source is required"})
        return

    session = SessionLocal()
    record: ModelRecord | None = None
    try:
        yield _sse("status", {"stage": "downloading", "progress": 1})

        expected_sha: str | None = None
        if source.startswith("hf://"):
            repo, file_name, expected_sha = _extract_repo_file_hf(source)
            spec = downloader.resolve_hf(repo, file_name)
            spec.expected_sha256 = expected_sha
        elif source.startswith("https://github.com/"):
            github_url, expected_sha = _parse_github_expected_sha(source)
            spec = downloader.resolve_github(github_url, expected_sha)
            if spec.expected_sha256 is None:
                raise ValueError("GitHub source must include #sha256=<digest>")
        else:
            raise ValueError("source must be hf://... or https://github.com/...")

        model_id = f"local-{re.sub(r'[^a-zA-Z0-9._:-]+', '-', spec.file_name.lower()).strip('-')}"
        record = ModelRecord(
            model_id=model_id,
            name=spec.file_name,
            source=source,
            file_path=str(MODEL_STORAGE_DIR / spec.file_name),
            sha256="",
            quantization="unknown",
            size_gb=0.0,
            pulled_at=datetime.now(timezone.utc),
            status="downloading",
        )
        session.merge(record)
        session.commit()

        downloaded, actual_sha = await asyncio.to_thread(downloader.download_file, spec, MODEL_STORAGE_DIR)
        if spec.expected_sha256 and actual_sha != spec.expected_sha256.lower():
            raise ValueError("SHA256 mismatch after download")

        meta = extract_metadata(downloaded, spec.repo_hint)
        record = session.get(ModelRecord, model_id)
        if record is None:
            raise RuntimeError("record disappeared")
        record.file_path = str(downloaded)
        record.sha256 = actual_sha
        record.size_gb = round(downloaded.stat().st_size / (1024**3), 4)
        record.quantization = meta.quantization
        record.status = "quantizing"
        session.commit()

        yield _sse("status", {"stage": "quantizing", "progress": 60, "model_id": model_id})
        quantized = await quantize_if_needed(downloaded)

        record.file_path = str(quantized)
        record.quantization = os.getenv("QUANTIZATION_FORMAT", "Q4_K_M") if quantized != downloaded else meta.quantization
        session.commit()

        yield _sse("status", {"stage": "benchmarking", "progress": 80, "model_id": model_id})
        score, tps = await asyncio.to_thread(run_benchmark, quantized)
        record.benchmark_score = score
        record.tokens_per_sec = tps
        record.status = "ready"
        session.commit()

        yield _sse(
            "complete",
            {
                "progress": 100,
                "model_id": model_id,
                "status": "ready",
                "benchmark_score": score,
                "tokens_per_sec": tps,
            },
        )
    except Exception as exc:  # noqa: BLE001
        if record is not None:
            record.status = "failed"
            session.merge(record)
            session.commit()
        yield _sse("error", {"message": str(exc)})
    finally:
        session.close()


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/models/pull")
async def pull_model(body: PullRequest) -> StreamingResponse:
    return StreamingResponse(_pull_model_events(body), media_type="text/event-stream")


@app.get("/models/list", response_model=list[ModelResponse])
async def list_models() -> list[ModelResponse]:
    with SessionLocal() as session:
        rows = session.query(ModelRecord).order_by(ModelRecord.pulled_at.desc()).all()
        if rows:
            return [_serialize_model(r) for r in rows]

    legacy = _read_registry_fallback()
    result: list[ModelResponse] = []
    for item in legacy:
        result.append(
            ModelResponse(
                model_id=str(item.get("id", "unknown")),
                name=str(item.get("id", "unknown")),
                source="legacy",
                file_path=str(item.get("file_path", "")),
                sha256=str(item.get("sha256", "")),
                quantization=str(item.get("quantization", "unknown")),
                size_gb=float(item.get("ram_estimate_gb", 0.0)),
                pulled_at=datetime.now(timezone.utc),
                status=str(item.get("status", "installed")),
                benchmark_score=None,
                tokens_per_sec=None,
            )
        )
    return result


@app.get("/models/{model_id}", response_model=ModelResponse)
async def get_model(model_id: str) -> ModelResponse:
    with SessionLocal() as session:
        model = session.get(ModelRecord, model_id)
        if model is None:
            raise HTTPException(status_code=404, detail=_MODEL_NOT_FOUND)
        return _serialize_model(model)


@app.get("/models/{model_id}/benchmark", response_model=BenchmarkResponse)
async def get_benchmark(model_id: str) -> BenchmarkResponse:
    with SessionLocal() as session:
        model = session.get(ModelRecord, model_id)
        if model is None:
            raise HTTPException(status_code=404, detail=_MODEL_NOT_FOUND)
        return BenchmarkResponse(
            model_id=model.model_id,
            benchmark_score=model.benchmark_score,
            tokens_per_sec=model.tokens_per_sec,
        )


@app.delete("/models/{model_id}")
async def delete_model(model_id: str) -> dict[str, object]:
    with SessionLocal() as session:
        model = session.get(ModelRecord, model_id)
        if model is None:
            raise HTTPException(status_code=404, detail=_MODEL_NOT_FOUND)
        path = Path(model.file_path)
        if path.exists():
            path.unlink(missing_ok=True)
        session.delete(model)
        session.commit()
    return {"ok": True, "model_id": model_id}


@app.post("/models/{model_id}/activate")
async def activate_model(model_id: str) -> dict[str, object]:
    response = requests.post(f"{MODEL_GATEWAY_URL}/models/{model_id}/activate", timeout=20)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"model-gateway activate failed: {response.text}")
    return {"ok": True, "model_id": model_id}
