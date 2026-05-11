"""
Headless tests for vyrex_proxy.py
All subprocess / httpx / GPU dependencies are monkeypatched.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── path bootstrap ────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parents[3]
PROXY_DIR = REPO_ROOT / "platform" / "vyrex-proxy"
sys.path.insert(0, str(PROXY_DIR))

import vyrex_proxy as np_mod
from vyrex_proxy import app

TRANSPORT = ASGITransport(app=app)

# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clear_state():
    np_mod._metrics.clear()
    np_mod._action_timestamps.clear()
    yield
    np_mod._metrics.clear()
    np_mod._action_timestamps.clear()


@pytest.fixture
def _stub_policy(monkeypatch):
    """Return a permissive policy that never blocks."""
    policy = {
        "max_prompt_tokens": 4096,
        "max_requests_per_minute": 600,
        "blocked_models": [],
        "require_model_allowlist": False,
        "allowed_models": [],
        "stream_allowed": True,
        "vram_limit_mb": 0,
    }
    monkeypatch.setattr(np_mod, "_load_policy", lambda: policy)
    return policy


def _make_ollama_mock(return_json: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.is_success = True
    resp.status_code = 200
    resp.json.return_value = return_json
    resp.raise_for_status = MagicMock()
    return resp


# ── tests ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_generate_success(_stub_policy, monkeypatch):
    ollama_resp = {"response": "hello world from ollama", "done": True}
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_make_ollama_mock(ollama_resp))

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/proxy/generate", json={"model": "llama3", "prompt": "Hello!"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "hello world from ollama"
    assert len(np_mod._metrics) == 1
    assert np_mod._metrics[0].status == "success"


@pytest.mark.asyncio
async def test_generate_token_budget_exceeded(monkeypatch):
    policy = {
        "max_prompt_tokens": 2,  # very small budget
        "max_requests_per_minute": 600,
        "blocked_models": [],
    }
    monkeypatch.setattr(np_mod, "_load_policy", lambda: policy)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/proxy/generate",
            json={"model": "llama3", "prompt": "This is a long prompt exceeding budget"},
        )

    assert resp.status_code == 422
    assert "token budget" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_generate_blocked_model(monkeypatch):
    policy = {
        "max_prompt_tokens": 4096,
        "max_requests_per_minute": 600,
        "blocked_models": ["badmodel*"],
    }
    monkeypatch.setattr(np_mod, "_load_policy", lambda: policy)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/proxy/generate",
            json={"model": "badmodel-v1", "prompt": "test"},
        )

    assert resp.status_code == 403
    assert "blocked" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_chat_success(_stub_policy, monkeypatch):
    ollama_resp = {"message": {"role": "assistant", "content": "Hi there"}, "done": True}
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_make_ollama_mock(ollama_resp))

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post(
            "/proxy/chat",
            json={"model": "llama3", "messages": [{"role": "user", "content": "Hello"}]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"]["content"] == "Hi there"
    assert len(np_mod._metrics) == 1


@pytest.mark.asyncio
async def test_models_list(_stub_policy, monkeypatch):
    ollama_resp = {
        "models": [
            {"name": "llama3:latest", "size": 4_000_000_000, "digest": "abc123"}
        ]
    }
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=_make_ollama_mock(ollama_resp))

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/proxy/models")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["models"]) == 1
    assert body["models"][0]["status"] == "ready"
    assert "size_mb" in body["models"][0]


@pytest.mark.asyncio
async def test_model_pull(_stub_policy, monkeypatch):
    def _fake_stream(*args, **kwargs):
        class FakeStreamCtx:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                # No cleanup needed for this in-memory async stream test double.
                pass
            async def aiter_bytes(self):
                yield b'{"status":"pulling"}\n'
                yield b'{"status":"success"}\n'
        return FakeStreamCtx()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = _fake_stream

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/proxy/models/pull", json={"name": "llama3"})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_metrics_empty():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/proxy/metrics")
    assert resp.status_code == 200
    assert resp.json()["requests"] == []


@pytest.mark.asyncio
async def test_metrics_populated_after_generate(_stub_policy, monkeypatch):
    ollama_resp = {"response": "ok", "done": True}
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_make_ollama_mock(ollama_resp))

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post("/proxy/generate", json={"model": "llama3", "prompt": "hi"})
        resp = await ac.get("/proxy/metrics")

    assert resp.status_code == 200
    records = resp.json()["requests"]
    assert len(records) == 1
    assert records[0]["model"] == "llama3"
    assert records[0]["status"] == "success"
    assert "latency_ms" in records[0]


@pytest.mark.asyncio
async def test_metrics_summary(_stub_policy, monkeypatch):
    ollama_resp = {"response": "word1 word2 word3", "done": True}
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_make_ollama_mock(ollama_resp))

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)
    monkeypatch.setattr(np_mod, "_read_vram", lambda: {"vram_used_mb": 0, "vram_total_mb": 0, "vram_source": "unavailable"})

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post("/proxy/generate", json={"model": "llama3", "prompt": "hello world"})
        resp = await ac.get("/proxy/metrics/summary")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_requests"] == 1
    assert "avg_latency_ms" in body
    assert "p95_latency_ms" in body
    assert "tokens_per_second_avg" in body
    assert "active_models" in body
    assert "llama3" in body["active_models"]


@pytest.mark.asyncio
async def test_health_ollama_reachable(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.is_success = True

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/proxy/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["ollama_reachable"] is True
    assert body["proxy_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_health_ollama_unreachable(monkeypatch):
    import httpx

    async def _raise(*a, **kw):
        raise httpx.ConnectError("refused")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = _raise

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.get("/proxy/health")

    assert resp.status_code == 200
    assert resp.json()["ollama_reachable"] is False


@pytest.mark.asyncio
async def test_rate_limit_exceeded(monkeypatch):
    policy = {
        "max_prompt_tokens": 4096,
        "max_requests_per_minute": 2,
        "blocked_models": [],
    }
    monkeypatch.setattr(np_mod, "_load_policy", lambda: policy)
    # Pre-fill timestamps to simulate 3 recent requests
    now = time.time()
    for _ in range(3):
        np_mod._action_timestamps.append(now)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        resp = await ac.post("/proxy/generate", json={"model": "llama3", "prompt": "hi"})

    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_active_model_hot_swap_endpoints():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        set_resp = await ac.post(
            "/active-model",
            json={"model_id": "hot-model", "model_path": "/models/hot-model"},
        )
        get_resp = await ac.get("/active-model")

    assert set_resp.status_code == 200
    assert get_resp.status_code == 200
    assert get_resp.json()["model_id"] == "hot-model"
    assert get_resp.json()["model_path"] == "/models/hot-model"


@pytest.mark.asyncio
async def test_generate_uses_hot_swapped_model_when_request_model_missing(_stub_policy, monkeypatch):
    class _Resp:
        is_success = True
        status_code = 200
        def json(self):
            return {"response": "ok", "done": True}
        def raise_for_status(self):
            return None

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_Resp())

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as ac:
        await ac.post(
            "/active-model",
            json={"model_id": "runtime-hot", "model_path": "/models/runtime-hot"},
        )
        resp = await ac.post("/proxy/generate", json={"prompt": "hello"})

    assert resp.status_code == 200
    _, kwargs = mock_client.post.call_args
    assert kwargs["json"]["model"] == "runtime-hot"
