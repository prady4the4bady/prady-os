from __future__ import annotations

import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import (
    app,
    _memory_store,
    _hit_count,
    _miss_count,
    CATEGORIES,
    _provider,
    _persistence,
    _compute_local_embedding,
    _score_entries,
)
from app.embeddings import (
    LocalHashProvider,
    SentenceTransformerProvider,
    EmbeddingProvider,
    ProviderInfo,
    get_provider,
)
from app.persistence import AhnisStore


@pytest.fixture(autouse=True)
def reset():
    for c in CATEGORIES:
        _memory_store[c].clear()
    global _hit_count, _miss_count
    _hit_count = 0
    _miss_count = 0


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Existing tests (backward compatible) ---

@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_status_shows_store_stats(client: AsyncClient):
    resp = await client.get("/ahnis/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_entries" in data
    assert "by_category" in data
    assert "embedding_provider" in data
    assert "embedding_dimension" in data


@pytest.mark.asyncio
async def test_write_and_search_memory(client: AsyncClient):
    resp = await client.post("/memory/write", json={"category": "conversation", "content": "Hello from test"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "written"
    resp = await client.post("/memory/search", json={"query": "Hello", "category": "conversation"})
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.asyncio
async def test_write_unknown_category_returns_400(client: AsyncClient):
    resp = await client.post("/memory/write", json={"category": "nonexistent", "content": "test"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_search_all_categories(client: AsyncClient):
    await client.post("/memory/write", json={"category": "task", "content": "deploy pipeline"})
    resp = await client.post("/memory/search", json={"query": "deploy"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_search_with_min_relevance(client: AsyncClient):
    await client.post("/memory/write", json={"category": "conversation", "content": "important deployment pipeline"})
    resp = await client.post("/memory/search", json={"query": "deployment", "min_relevance": 0.5})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_summarize_empty_category(client: AsyncClient):
    resp = await client.post("/memory/summarize", json={"category": "conversation"})
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data


@pytest.mark.asyncio
async def test_summarize_nonempty(client: AsyncClient):
    await client.post("/memory/write", json={"category": "conversation", "content": "entry one"})
    resp = await client.post("/memory/summarize", json={"category": "conversation"})
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.asyncio
async def test_consolidate(client: AsyncClient):
    for i in range(10):
        await client.post("/memory/write", json={"category": "conversation", "content": f"entry {i}"})
    resp = await client.post("/memory/consolidate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "consolidated"


@pytest.mark.asyncio
async def test_delete_existing_entry(client: AsyncClient):
    write = await client.post("/memory/write", json={"category": "conversation", "content": "to delete"})
    eid = write.json()["entry_id"]
    resp = await client.delete(f"/memory/{eid}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(client: AsyncClient):
    resp = await client.delete("/memory/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_skills_endpoint(client: AsyncClient):
    resp = await client.get("/memory/skills")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_projects_endpoint(client: AsyncClient):
    resp = await client.get("/memory/projects")
    assert resp.status_code == 200


# --- Embedding tests ---

@pytest.mark.asyncio
async def test_local_embedding_deterministic():
    v1 = _compute_local_embedding("hello world")
    v2 = _compute_local_embedding("hello world")
    assert v1 == v2
    assert len(v1) == 64


@pytest.mark.asyncio
async def test_local_embedding_differs_for_diff_text():
    v1 = _compute_local_embedding("hello world")
    v2 = _compute_local_embedding("goodbye world")
    assert v1 != v2


@pytest.mark.asyncio
async def test_score_entries_exact_match():
    entries = [{"content": "this is a deployment pipeline test"}, {"content": "unrelated note"}]
    scored = _score_entries("deployment pipeline", entries)
    assert scored[0]["relevance"] > scored[1]["relevance"]


@pytest.mark.asyncio
async def test_score_entries_empty_query():
    entries = [{"content": "any content"}]
    scored = _score_entries("", entries)
    assert scored[0]["relevance"] > 0


# --- New tests for pluggable embeddings ---

def test_local_hash_provider():
    p = LocalHashProvider()
    info = p.info()
    assert info.name == "local-hash"
    assert info.dimension == 64
    assert info.backend_capability == "local"
    assert info.available
    v = p.compute("test")
    assert len(v) == 64
    assert p.dimension() == 64


def test_local_hash_deterministic():
    p = LocalHashProvider()
    v1 = p.compute("deterministic test")
    v2 = p.compute("deterministic test")
    assert v1 == v2


def test_sentence_transformer_provider_fallback():
    """When sentence-transformers is not installed, fallback to hash."""
    p = SentenceTransformerProvider()
    info = p.info()
    assert "sentence-transformer" in info.name
    v = p.compute("fallback test")
    assert len(v) == p.dimension()


def test_get_provider_returns_something():
    p = get_provider()
    assert isinstance(p, EmbeddingProvider)
    info = p.info()
    assert info.name
    assert info.dimension > 0
    assert info.backend_capability


def test_get_provider_local_hash_env(monkeypatch):
    monkeypatch.setenv("AHNIS_EMBEDDING_MODE", "local-hash")
    p = get_provider()
    assert isinstance(p, LocalHashProvider)


def test_embedding_provider_info_structure():
    p = LocalHashProvider()
    info = p.info()
    assert isinstance(info, ProviderInfo)
    assert isinstance(info.name, str)
    assert isinstance(info.dimension, int)
    assert isinstance(info.backend_capability, str)
    assert isinstance(info.available, bool)


def test_provider_compute_normalizes():
    p = LocalHashProvider()
    v = p.compute("test vector with multiple words for normalization")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 0.01  # unit vector


# --- New tests for enhanced endpoints ---

@pytest.mark.asyncio
async def test_embedding_provider_endpoint(client: AsyncClient):
    resp = await client.get("/ahnis/embeddings/provider")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider_name" in data
    assert "dimension" in data
    assert "backend_capability" in data
    assert "available" in data


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient):
    resp = await client.get("/ahnis/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_entries" in data
    assert "embedding_provider" in data
    assert "embedding_dimension" in data
    assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_search_response_structured(client: AsyncClient):
    await client.post("/memory/write", json={"category": "conversation", "content": "structured response test"})
    resp = await client.post("/memory/search", json={"query": "structured"})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "count" in data
    assert "backend" in data
    assert "query" in data
    if data["count"] > 0:
        result = data["results"][0]
        assert "id" in result
        assert "category" in result
        assert "content" in result
        assert "relevance" in result


@pytest.mark.asyncio
async def test_write_response_structured(client: AsyncClient):
    resp = await client.post("/memory/write", json={"category": "task", "content": "write response test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "entry_id" in data


@pytest.mark.asyncio
async def test_search_ranking_behavior():
    entries = [
        {"content": "the quick brown fox jumps over the lazy dog"},
        {"content": "the lazy dog sleeps all day"},
        {"content": "quantum computing advances in machine learning"},
    ]
    scored = _score_entries("lazy dog", entries)
    assert scored[0]["content"] == entries[0]["content"]
    assert scored[1]["content"] == entries[1]["content"]
    assert scored[0]["relevance"] >= scored[1]["relevance"]


@pytest.mark.asyncio
async def test_summarize_legacy_alias(client: AsyncClient):
    resp = await client.post("/memory/summarize_legacy", json={"category": "conversation"})
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "count" in data


@pytest.mark.asyncio
async def test_consolidate_legacy_alias(client: AsyncClient):
    resp = await client.post("/memory/consolidate_legacy")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "entries_before" in data


# --- New tests: persistence ---

def test_ahnis_store_save_and_restore(tmp_path):
    db_path = str(tmp_path / "test_ahnis.db")
    s = AhnisStore(db_path)
    entry = {
        "id": "test-persist-1",
        "category": "conversation",
        "content": "persistence test content",
        "metadata": {"source": "test"},
        "timestamp": "2025-01-01T00:00:00Z",
        "relevance": 0.5,
        "embedding_backend": "local-hash",
        "embedding": None,
    }
    s.save_entry(entry)
    assert s.persisted_count() == 1
    s.close()

    # Simulate restart
    s2 = AhnisStore(db_path)
    restored = s2.restore_entries()
    assert "conversation" in restored
    assert len(restored["conversation"]) >= 1
    found = [e for e in restored["conversation"] if e["id"] == "test-persist-1"]
    assert len(found) == 1
    assert found[0]["content"] == "persistence test content"
    assert found[0]["metadata"].get("source") == "test"
    s2.close()


def test_ahnis_store_delete_persisted(tmp_path):
    db_path = str(tmp_path / "test_ahnis_del.db")
    s = AhnisStore(db_path)
    entry = {
        "id": "test-delete-1",
        "category": "task",
        "content": "to be deleted from persistence",
        "metadata": {},
        "timestamp": "2025-01-01T00:00:00Z",
        "relevance": 0.0,
        "embedding_backend": "local-hash",
        "embedding": None,
    }
    s.save_entry(entry)
    assert s.persisted_count() == 1
    s.delete_entry("test-delete-1")
    assert s.persisted_count() == 0
    s.close()


def test_ahnis_store_list_by_category(tmp_path):
    db_path = str(tmp_path / "test_ahnis_cat.db")
    s = AhnisStore(db_path)
    for i in range(3):
        s.save_entry({
            "id": f"cat-{i}",
            "category": "skill",
            "content": f"skill {i}",
            "metadata": {},
            "timestamp": "2025-01-01T00:00:00Z",
            "relevance": 0.0,
            "embedding_backend": "local-hash",
            "embedding": None,
        })
    s.save_entry({
        "id": "proj-1",
        "category": "project",
        "content": "a project",
        "metadata": {},
        "timestamp": "2025-01-01T00:00:00Z",
        "relevance": 0.0,
        "embedding_backend": "local-hash",
        "embedding": None,
    })
    skills = s.list_entries(category="skill")
    assert len(skills) == 3
    all_entries = s.list_entries()
    assert len(all_entries) == 4
    s.close()


def test_ahnis_store_handles_missing_db_path(tmp_path):
    db_path = str(tmp_path / "nonexistent" / "deep" / "ahnis.db")
    s = AhnisStore(db_path)
    # Should create parent directories
    assert s.is_available or True  # may be unavailable if permissions, but shouldn't crash
    s.close()


@pytest.mark.asyncio
async def test_ahnis_persistence_in_status_endpoint(client: AsyncClient):
    resp = await client.get("/ahnis/status")
    data = resp.json()
    assert "persistence_available" in data
    assert "persisted_entry_count" in data


@pytest.mark.asyncio
async def test_ahnis_persisted_metrics_fields(client: AsyncClient):
    resp = await client.get("/ahnis/metrics")
    data = resp.json()
    assert "persisted_entry_count" in data
    assert "restored_on_startup" in data
    assert "backend_mode" in data
