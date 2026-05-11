"""Tests for MemoryStore."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
import pytest_asyncio

from memory_store import MemoryStore


@pytest.fixture
def tmp_store(tmp_path):
    """Return a MemoryStore backed by a temporary SQLite file."""
    return MemoryStore(db_path=tmp_path / "test_memory.db")


# ---------------------------------------------------------------------------
# store and search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_and_search(tmp_store):
    """store() persists an entry; search() retrieves it by keyword."""
    await tmp_store.store(
        agent_id="agent-1",
        content="The user prefers dark mode and vim keybindings.",
        tags=["preferences", "ui"],
    )

    results = await tmp_store.search("agent-1", "dark mode")
    assert len(results) >= 1
    assert any("dark mode" in r.content for r in results)


@pytest.mark.asyncio
async def test_store_multiple_and_search(tmp_store):
    """Multiple entries can be stored and independently searched."""
    await tmp_store.store("agent-1", "Python is a great language", tags=["lang"])
    await tmp_store.store("agent-1", "Rust is fast and safe", tags=["lang"])
    await tmp_store.store("agent-1", "Cats are warm and soft", tags=["pets"])

    results = await tmp_store.search("agent-1", "Python")
    assert any("Python" in r.content for r in results)
    # Unrelated entry should not dominate
    cats = await tmp_store.search("agent-1", "Cats")
    assert any("Cats" in r.content for r in cats)


# ---------------------------------------------------------------------------
# access_count increments on search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_increments_access_count(tmp_store):
    """Searching increments the access_count of returned entries."""
    await tmp_store.store("agent-2", "Important note about deployments", tags=[])

    results = await tmp_store.search("agent-2", "deployments")
    assert len(results) == 1
    assert results[0].access_count == 1  # just incremented

    # Search again
    results2 = await tmp_store.search("agent-2", "deployments")
    assert results2[0].access_count == 2


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_removes_entry(tmp_store):
    """delete() removes the entry; subsequent search returns nothing."""
    entry = await tmp_store.store("agent-3", "Temporary memory to delete", tags=[])
    deleted = await tmp_store.delete(entry.id)
    assert deleted is True

    results = await tmp_store.search("agent-3", "Temporary memory")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false(tmp_store):
    """delete() returns False for a non-existent memory ID."""
    result = await tmp_store.delete("00000000-0000-0000-0000-000000000000")
    assert result is False


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_reports_correct_counts(tmp_store):
    """stats() reflects the number of stored entries and agents."""
    await tmp_store.store("agent-a", "Memory A1", tags=[])
    await tmp_store.store("agent-a", "Memory A2", tags=[])
    await tmp_store.store("agent-b", "Memory B1", tags=[])

    stats = await tmp_store.stats()
    assert stats["total_entries"] == 3
    assert "agent-a" in stats["agents"]
    assert "agent-b" in stats["agents"]
    assert stats["db_size_mb"] >= 0


# ---------------------------------------------------------------------------
# auto-prune  (mocked threshold)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_prune_trims_low_access_entries(tmp_store, monkeypatch):
    """_maybe_prune() removes the lowest-access entries when DB exceeds limit."""
    # Monkeypatch the size limit to 0 so every call triggers prune
    import memory_store as ms_mod
    monkeypatch.setattr(ms_mod, "MAX_DB_SIZE_MB", 0)
    monkeypatch.setattr(ms_mod, "PRUNE_BATCH", 1)

    await tmp_store.store("prune-agent", "Entry one", tags=[])
    await tmp_store.store("prune-agent", "Entry two", tags=[])

    # Force a prune cycle
    await tmp_store._maybe_prune()

    stats = await tmp_store.stats()
    # At least one entry was removed
    assert stats["total_entries"] <= 1
