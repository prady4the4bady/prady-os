"""Tests for RAGStore using real in-memory ChromaDB."""
from __future__ import annotations

import pytest

from app.rag_store import RAGStore

pytestmark = pytest.mark.anyio


@pytest.fixture()
def rag() -> RAGStore:
    return RAGStore(path=":memory:")


async def test_upsert_and_search(rag: RAGStore) -> None:
    await rag.upsert("test-ns", "key1", "The quick brown fox", metadata={"tag": "fox"})
    await rag.upsert("test-ns", "key2", "Machine learning is fun", metadata={"tag": "ml"})
    results = await rag.search("test-ns", "brown fox", top_k=2)
    assert len(results) >= 1
    assert any("fox" in r["content"] for r in results)


async def test_upsert_overwrites_same_key(rag: RAGStore) -> None:
    await rag.upsert("ns-overwrite", "k1", "original content", metadata={"tag": "v1"})
    await rag.upsert("ns-overwrite", "k1", "updated content", metadata={"tag": "v2"})
    results = await rag.search("ns-overwrite", "updated content", top_k=1)
    assert len(results) == 1
    assert results[0]["content"] == "updated content"


async def test_delete(rag: RAGStore) -> None:
    await rag.upsert("ns2", "del-key", "to be deleted")
    await rag.delete("ns2", "del-key")
    results = await rag.search("ns2", "to be deleted", top_k=5)
    assert all(r["content"] != "to be deleted" for r in results)


async def test_namespace_isolation(rag: RAGStore) -> None:
    await rag.upsert("ns-a", "k", "data in namespace A")
    await rag.upsert("ns-b", "k", "data in namespace B")
    results_a = await rag.search("ns-a", "namespace A", top_k=1)
    results_b = await rag.search("ns-b", "namespace B", top_k=1)
    assert results_a[0]["content"] == "data in namespace A"
    assert results_b[0]["content"] == "data in namespace B"


async def test_search_returns_distance(rag: RAGStore) -> None:
    await rag.upsert("ns3", "k1", "asyncio is Python async")
    results = await rag.search("ns3", "Python async", top_k=1)
    assert "distance" in results[0]
    assert isinstance(results[0]["distance"], float)
