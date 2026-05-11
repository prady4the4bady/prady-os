from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).parents[3]
MODEL_HUB_DIR = REPO_ROOT / "platform" / "model-hub"
sys.path.insert(0, str(MODEL_HUB_DIR))

import model_hub_service as mh
from model_hub_service import app

TRANSPORT = ASGITransport(app=app)


class FakeDownloader:
    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path

    async def download(self, source, url, model_id, quantization, progress_cb):
        model_dir = self.tmp_path / "models" / model_id
        model_dir.mkdir(parents=True, exist_ok=True)
        blob = model_dir / "weights.bin"

        await progress_cb(100, 1000, "starting")
        await progress_cb(700, 1000, "downloading")

        blob.write_bytes(b"x" * 1024)
        size = sum(p.stat().st_size for p in model_dir.rglob("*") if p.is_file())

        await progress_cb(size, size, "complete")
        await asyncio.sleep(0)
        return model_dir, size


@pytest_asyncio.fixture(autouse=True)
async def _reset_state(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    models_dir = tmp_path / "models"
    db_path = data_dir / "model_hub.db"

    monkeypatch.setattr(mh, "DATA_DIR", data_dir)
    monkeypatch.setattr(mh, "MODELS_DIR", models_dir)
    monkeypatch.setattr(mh, "DB_PATH", db_path)

    mh._jobs.clear()
    mh._active_pulls.clear()
    monkeypatch.setattr(mh, "_post_notification", AsyncMock(return_value=None))
    monkeypatch.setattr(mh, "_downloader", FakeDownloader(tmp_path))

    await mh._init_db()


@pytest.mark.asyncio
async def test_health_initial():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["models"] == 0


@pytest.mark.asyncio
async def test_pull_queued():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/models/pull",
            json={
                "source": "huggingface",
                "url": "https://huggingface.co/foo/bar",
                "model_id": "foo-bar",
                "quantization": "q4",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_pull_invalid_source_422():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/models/pull",
            json={
                "source": "ollama",
                "url": "x",
                "model_id": "x",
                "quantization": "q4",
            },
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_pull_progress_sse_streams_and_finishes():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test", timeout=10) as ac:
        queued = await ac.post(
            "/models/pull",
            json={
                "source": "github",
                "url": "https://github.com/org/repo",
                "model_id": "repo-model",
                "quantization": "q8",
            },
        )
        job_id = queued.json()["job_id"]
        progress = await ac.get(f"/models/pull/{job_id}/progress")

    assert progress.status_code == 200
    assert '"job_id":' in progress.text
    assert '"percent":' in progress.text
    assert '"bytes_downloaded":' in progress.text
    assert '"status": "complete"' in progress.text


@pytest.mark.asyncio
async def test_pull_progress_missing_job_404():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/models/pull/does-not-exist/progress")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_models_after_pull_has_metadata():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post(
            "/models/pull",
            json={
                "source": "huggingface",
                "url": "https://huggingface.co/foo/bar",
                "model_id": "meta-model",
                "quantization": "f16",
            },
        )
        await asyncio.sleep(0.05)
        resp = await ac.get("/models")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    row = body["models"][0]
    assert row["model_id"] == "meta-model"
    assert row["quantization"] == "f16"
    assert isinstance(row["size_bytes"], int)
    assert row["is_active"] is False


@pytest.mark.asyncio
async def test_activate_model_calls_vyrex(monkeypatch):
    class _Resp:
        is_success = True

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_Resp())
    monkeypatch.setattr(mh.httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post(
            "/models/pull",
            json={
                "source": "huggingface",
                "url": "https://huggingface.co/foo/bar",
                "model_id": "active-model",
                "quantization": "q4",
            },
        )
        await asyncio.sleep(0.05)
        resp = await ac.post("/models/active-model/activate")

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_activate_model_404():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/models/missing/activate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_model_removes_row_and_files():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post(
            "/models/pull",
            json={
                "source": "github",
                "url": "https://github.com/org/repo",
                "model_id": "delete-me",
                "quantization": "none",
            },
        )
        await asyncio.sleep(0.05)
        delete_resp = await ac.delete("/models/delete-me")
        list_resp = await ac.get("/models")

    assert delete_resp.status_code == 200
    assert list_resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_model_404():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.delete("/models/nope")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_benchmark_updates_metrics(monkeypatch):
    class _Resp:
        is_success = True
        def json(self):
            return {"response": "one two three four five six seven eight nine ten"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_Resp())
    monkeypatch.setattr(mh.httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post(
            "/models/pull",
            json={
                "source": "huggingface",
                "url": "https://huggingface.co/foo/bar",
                "model_id": "bench-model",
                "quantization": "q4",
            },
        )
        await asyncio.sleep(0.05)
        bench = await ac.get("/models/bench-model/benchmark")

    assert bench.status_code == 200
    payload = bench.json()
    assert payload["model_id"] == "bench-model"
    assert payload["tokens_per_second"] > 0
    assert payload["latency_ms"] > 0


@pytest.mark.asyncio
async def test_benchmark_404():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        bench = await ac.get("/models/missing/benchmark")
    assert bench.status_code == 404


@pytest.mark.asyncio
async def test_legacy_alias_models_list():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/models/list")
    assert resp.status_code == 200
    assert "models" in resp.json()


@pytest.mark.asyncio
async def test_legacy_alias_set_default_and_config(monkeypatch):
    class _Resp:
        is_success = True

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_Resp())
    monkeypatch.setattr(mh.httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post(
            "/models/pull",
            json={
                "source": "github",
                "url": "https://github.com/org/repo",
                "model_id": "legacy-default",
                "quantization": "q4",
            },
        )
        await asyncio.sleep(0.05)
        set_resp = await ac.post("/models/set-default", json={"model_id": "legacy-default"})
        cfg = await ac.get("/models/config")

    assert set_resp.status_code == 200
    assert cfg.status_code == 200
    assert cfg.json()["default_model"] == "legacy-default"
