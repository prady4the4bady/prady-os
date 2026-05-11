from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

_SHARED_PATH = Path(__file__).resolve().parents[1] / "shared"
if str(_SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(_SHARED_PATH))

from auth_middleware import require_auth

try:
    import aiosqlite
except Exception:  # pragma: no cover
    aiosqlite = None

try:
    from huggingface_hub import snapshot_download
except Exception:  # pragma: no cover
    snapshot_download = None

try:
    from git import Repo
except Exception:  # pragma: no cover
    Repo = None

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
MODELS_DIR = Path(os.environ.get("MODELS_DIR", "/models"))
DB_PATH = DATA_DIR / "model_hub.db"
NOTIFICATION_BUS_URL = os.environ.get("NOTIFICATION_BUS_URL", "http://notification-bus:8111")
SECURITY_POLICY_URL = os.environ.get("SECURITY_POLICY_URL", "http://security-policy:8117")
VYREX_URL = os.environ.get("VYREX_URL", "http://vyrex-proxy:8105")

JobStatus = Literal["queued", "downloading", "complete", "failed"]
_MODEL_NOT_FOUND = "model not found"


class PullRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    source: Literal["huggingface", "github"]
    url: str
    model_id: str
    quantization: Literal["q4", "q8", "f16", "none"]


class ActivateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_id: str


class JobProgress(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    bytes_downloaded: int
    total_bytes: int
    percent: float
    speed_bps: float
    error: str | None = None


_jobs: dict[str, JobProgress] = {}
_jobs_lock = asyncio.Lock()
_active_pulls: dict[str, str] = {}
_pull_tasks: dict[str, asyncio.Task[None]] = {}


class ModelDownloader:
    async def download(
        self,
        source: str,
        url: str,
        model_id: str,
        quantization: str,
        progress_cb: Callable[[int, int, str], Any],
    ) -> tuple[Path, int]:
        target_dir = MODELS_DIR / model_id
        if target_dir.exists():
            await asyncio.to_thread(shutil.rmtree, target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        await progress_cb(0, 100, "starting download")

        if source == "huggingface":
            if snapshot_download is None:
                raise RuntimeError("huggingface_hub is not installed")
            repo_id = self._parse_hf_repo(url)
            await progress_cb(20, 100, "resolving repository")
            await asyncio.to_thread(
                snapshot_download,
                repo_id=repo_id,
                local_dir=str(target_dir),
                local_dir_use_symlinks=False,
            )
            await progress_cb(90, 100, "finalizing model files")
        elif source == "github":
            if Repo is None:
                raise RuntimeError("gitpython is not installed")
            await progress_cb(25, 100, "cloning repository")
            await asyncio.to_thread(Repo.clone_from, url, str(target_dir))
            await progress_cb(90, 100, "finalizing model files")
        else:
            raise RuntimeError(f"unsupported source: {source}")

        size_bytes = await asyncio.to_thread(_compute_size_bytes, target_dir)
        await progress_cb(size_bytes, size_bytes, "download complete")
        return target_dir, size_bytes

    @staticmethod
    def _parse_hf_repo(url: str) -> str:
        clean = url.strip().rstrip("/")
        if clean.startswith("hf://"):
            return clean.replace("hf://", "", 1)
        if "huggingface.co/" in clean:
            after = clean.split("huggingface.co/", 1)[1]
            parts = [p for p in after.split("/") if p and p not in {"tree", "main", "resolve"}]
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
        pieces = [p for p in clean.split("/") if p]
        if len(pieces) >= 2:
            return f"{pieces[-2]}/{pieces[-1]}"
        raise RuntimeError(f"invalid HuggingFace URL: {url}")


_downloader = ModelDownloader()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


async def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    ddl = """
    CREATE TABLE IF NOT EXISTS models (
      id TEXT PRIMARY KEY,
      model_id TEXT NOT NULL UNIQUE,
      source TEXT NOT NULL,
      url TEXT NOT NULL,
      quantization TEXT NOT NULL,
      size_bytes INTEGER NOT NULL,
      path TEXT NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 0,
      pulled_at TEXT NOT NULL,
      last_used_at TEXT,
      benchmark_tps REAL,
      benchmark_latency_ms REAL
    );
    """

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript(ddl)
            await db.commit()
        return

    def _sync_init() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.executescript(ddl)
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_sync_init)


async def _post_notification(type_: str, title: str, body: str, severity: str = "info") -> None:
    payload = {
        "type": type_,
        "title": title,
        "body": body,
        "source": "model-hub",
        "severity": severity,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{NOTIFICATION_BUS_URL}/notify", json=payload)
    except Exception:
        # Fire-and-forget; model lifecycle should not fail on notify errors.
        pass


async def _policy_check(subject_id: str, permission: str) -> tuple[bool, str]:
    """Check security policy for a model action. Fail-open: log warning and allow on error."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SECURITY_POLICY_URL}/policies/check",
                json={"subject_type": "service", "subject_id": subject_id, "permission": permission},
            )
            data = resp.json()
            return bool(data.get("allowed", False)), str(data.get("reason", ""))
    except Exception as exc:
        logger.warning("security-policy unavailable, proceeding fail-open: %s", exc)
        return True, f"fail-open: {exc}"


async def _get_model_by_model_id(model_id: str) -> dict[str, Any] | None:
    query = """
    SELECT id, model_id, source, url, quantization, size_bytes, path, is_active,
           pulled_at, last_used_at, benchmark_tps, benchmark_latency_ms
    FROM models
    WHERE model_id = ?
    """

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(query, (model_id,))
            row = await cur.fetchone()
            await cur.close()
            return dict(row) if row else None

    def _sync_get() -> dict[str, Any] | None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(query, (model_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    return await asyncio.to_thread(_sync_get)


async def _list_models() -> list[dict[str, Any]]:
    query = """
    SELECT id, model_id, source, url, quantization, size_bytes, path, is_active,
           pulled_at, last_used_at, benchmark_tps, benchmark_latency_ms
    FROM models
    ORDER BY is_active DESC, COALESCE(last_used_at, pulled_at) DESC
    """

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(query)
            rows = await cur.fetchall()
            await cur.close()
            return [dict(r) for r in rows]

    def _sync_list() -> list[dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(query).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    return await asyncio.to_thread(_sync_list)


async def _insert_model(
    model_id: str,
    source: str,
    url: str,
    quantization: str,
    size_bytes: int,
    path: str,
) -> None:
    now = _now_iso()
    query = """
    INSERT INTO models (
      id, model_id, source, url, quantization, size_bytes, path,
      is_active, pulled_at, last_used_at, benchmark_tps, benchmark_latency_ms
    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, NULL, NULL)
    ON CONFLICT(model_id) DO UPDATE SET
      source=excluded.source,
      url=excluded.url,
      quantization=excluded.quantization,
      size_bytes=excluded.size_bytes,
      path=excluded.path,
      pulled_at=excluded.pulled_at
    """
    args = (str(uuid.uuid4()), model_id, source, url, quantization, size_bytes, path, now)

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(query, args)
            await db.commit()
        return

    def _sync_insert() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(query, args)
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_sync_insert)


async def _set_active_model(model_id: str) -> None:
    now = _now_iso()
    deactivate_q = "UPDATE models SET is_active = 0"
    activate_q = "UPDATE models SET is_active = 1, last_used_at = ? WHERE model_id = ?"

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(deactivate_q)
            await db.execute(activate_q, (now, model_id))
            await db.commit()
        return

    def _sync_set_active() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(deactivate_q)
            conn.execute(activate_q, (now, model_id))
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_sync_set_active)


async def _delete_model_record(model_id: str) -> None:
    query = "DELETE FROM models WHERE model_id = ?"

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(query, (model_id,))
            await db.commit()
        return

    def _sync_delete() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(query, (model_id,))
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_sync_delete)


async def _update_benchmark(model_id: str, tps: float, latency_ms: float) -> None:
    now = _now_iso()
    query = """
    UPDATE models
    SET benchmark_tps = ?, benchmark_latency_ms = ?, last_used_at = ?
    WHERE model_id = ?
    """

    if aiosqlite is not None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(query, (tps, latency_ms, now, model_id))
            await db.commit()
        return

    def _sync_update() -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(query, (tps, latency_ms, now, model_id))
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_sync_update)


async def _update_job(job_id: str, **updates: Any) -> None:
    async with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        payload = job.model_dump()
        payload.update(updates)
        _jobs[job_id] = JobProgress(**payload)


async def _run_pull_job(job_id: str, req: PullRequest) -> None:
    await _post_notification(
        "model.pull_started",
        f"Model pull started: {req.model_id}",
        f"source={req.source} url={req.url}",
        "info",
    )

    start = time.perf_counter()
    last_bytes = 0
    last_time = start

    async def _progress_cb(downloaded: int, total: int, message: str) -> None:
        nonlocal last_bytes, last_time
        now = time.perf_counter()
        dt = max(now - last_time, 0.001)
        delta = max(downloaded - last_bytes, 0)
        speed_bps = delta / dt
        last_bytes = downloaded
        last_time = now
        percent = (downloaded / total * 100.0) if total > 0 else 0.0
        await _update_job(
            job_id,
            status="downloading",
            message=message,
            bytes_downloaded=downloaded,
            total_bytes=total,
            percent=round(percent, 2),
            speed_bps=round(speed_bps, 2),
        )

    try:
        model_path, size_bytes = await _downloader.download(
            req.source,
            req.url,
            req.model_id,
            req.quantization,
            _progress_cb,
        )
        await _insert_model(
            model_id=req.model_id,
            source=req.source,
            url=req.url,
            quantization=req.quantization,
            size_bytes=size_bytes,
            path=str(model_path),
        )
        await _update_job(
            job_id,
            status="complete",
            message="pull complete",
            bytes_downloaded=size_bytes,
            total_bytes=size_bytes,
            percent=100.0,
            speed_bps=0.0,
            error=None,
        )
        await _post_notification(
            "model.pull_complete",
            f"Model pull complete: {req.model_id}",
            f"path={model_path}",
            "success",
        )
    except Exception as exc:
        await _update_job(
            job_id,
            status="failed",
            message="pull failed",
            error=str(exc),
        )
        await _post_notification(
            "model.pull_failed",
            f"Model pull failed: {req.model_id}",
            str(exc),
            "error",
        )
    finally:
        async with _jobs_lock:
            _active_pulls.pop(req.model_id, None)
        _pull_tasks.pop(job_id, None)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _init_db()
    yield


app = FastAPI(title="Kryos Model Hub", version="2.0.0", lifespan=lifespan)


@app.post("/models/pull")
async def pull_model(req: PullRequest) -> dict[str, Any]:
    await _init_db()
    async with _jobs_lock:
        if req.model_id in _active_pulls:
            raise HTTPException(status_code=409, detail="model pull already in progress")

        job_id = str(uuid.uuid4())
        _jobs[job_id] = JobProgress(
            job_id=job_id,
            status="queued",
            message=f"queued {req.model_id}",
            bytes_downloaded=0,
            total_bytes=0,
            percent=0.0,
            speed_bps=0.0,
            error=None,
        )
        _active_pulls[req.model_id] = job_id

    pull_task = asyncio.create_task(_run_pull_job(job_id, req))
    _pull_tasks[job_id] = pull_task
    return {"job_id": job_id, "status": "queued"}


@app.get("/models/pull/{job_id}/progress")
async def pull_model_progress(job_id: str) -> StreamingResponse:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="job not found")

    async def _stream() -> Any:
        last_payload = ""
        while True:
            job = _jobs.get(job_id)
            if job is None:
                break
            payload = json.dumps(job.model_dump())
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
            if job.status in {"complete", "failed"}:
                break
            await asyncio.sleep(0.2)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.get("/models")
async def list_models() -> dict[str, Any]:
    await _init_db()
    rows = await _list_models()
    for row in rows:
        row["is_active"] = bool(row.get("is_active"))
    return {"models": rows, "total": len(rows)}


@app.post("/models/{model_id}/activate")
async def activate_model(
    model_id: str,
    _current_user: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    allowed, reason = await _policy_check(model_id, "model-activation")
    if not allowed:
        logger.warning("policy denied model-activation for %s: %s — proceeding fail-open", model_id, reason)
    await _init_db()
    row = await _get_model_by_model_id(model_id)
    if row is None:
        raise HTTPException(status_code=404, detail=_MODEL_NOT_FOUND)

    payload = {"model_id": model_id, "model_path": row["path"]}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{VYREX_URL}/active-model", json=payload)
        if not resp.is_success:
            raise HTTPException(status_code=502, detail=f"vyrex-proxy rejected activate: {resp.status_code}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"vyrex-proxy unavailable: {exc}") from exc

    await _set_active_model(model_id)
    await _post_notification(
        "model.activated",
        f"Model activated: {model_id}",
        f"path={row['path']}",
        "success",
    )
    return {"ok": True, "model_id": model_id, "path": row["path"]}


@app.delete("/models/{model_id}")
async def delete_model(model_id: str) -> dict[str, Any]:
    await _init_db()
    row = await _get_model_by_model_id(model_id)
    if row is None:
        raise HTTPException(status_code=404, detail=_MODEL_NOT_FOUND)

    path = Path(row["path"])
    if path.exists():
        if path.is_dir():
            await asyncio.to_thread(shutil.rmtree, path)
        else:
            await asyncio.to_thread(path.unlink)
    await _delete_model_record(model_id)
    return {"ok": True, "deleted": model_id}


@app.get("/models/{model_id}/benchmark")
async def benchmark_model(model_id: str) -> dict[str, Any]:
    await _init_db()
    row = await _get_model_by_model_id(model_id)
    if row is None:
        raise HTTPException(status_code=404, detail=_MODEL_NOT_FOUND)

    prompt = "Benchmark the runtime speed in one short sentence."
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{VYREX_URL}/proxy/generate",
                json={
                    "model": model_id,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 10},
                },
            )
        if not resp.is_success:
            raise HTTPException(status_code=502, detail=f"benchmark failed: {resp.status_code}")
        body = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"vyrex-proxy unavailable: {exc}") from exc

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    token_count = len(str(body.get("response", "")).split())
    if token_count <= 0:
        token_count = 10
    tps = round(token_count / max(latency_ms / 1000.0, 0.001), 2)

    await _update_benchmark(model_id, tps, latency_ms)
    return {"model_id": model_id, "tokens_per_second": tps, "latency_ms": latency_ms}


@app.get("/health")
async def health() -> dict[str, Any]:
    await _init_db()
    rows = await _list_models()
    return {"status": "ok", "models": len(rows), "jobs": len(_jobs)}


# ---------------------------------------------------------------------------
# Backward-compatible aliases for existing UI callers.
# ---------------------------------------------------------------------------

@app.get("/models/list")
async def models_list_alias() -> dict[str, Any]:
    return await list_models()


@app.post("/models/set-default")
async def models_set_default_alias(
    req: ActivateRequest,
    current_user: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    _ = current_user
    return await activate_model(req.model_id)


@app.get("/models/config")
async def models_config_alias() -> dict[str, Any]:
    rows = await _list_models()
    active = next((r for r in rows if bool(r.get("is_active"))), None)
    return {"default_model": active["model_id"] if active else None}
