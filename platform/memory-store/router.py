"""FastAPI router for MemoryStore — agent memory CRUD and search."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .memory_store import MemoryStore

router = APIRouter(tags=["memory"])
_store: Optional[MemoryStore] = None


def get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store


class StoreRequest(BaseModel):
    agent_id: str
    content: str
    tags: List[str] = []


class SearchRequest(BaseModel):
    agent_id: str
    query: str
    top_k: int = 10


@router.post("/memory/store")
async def store_memory(body: StoreRequest) -> Dict[str, Any]:
    """Store a memory entry."""
    store = get_store()
    entry = await store.store(body.agent_id, body.content, body.tags)
    return entry.to_dict()


@router.post("/memory/search")
async def search_memory(body: SearchRequest) -> Dict[str, Any]:
    """Full-text search over agent memories."""
    store = get_store()
    results = await store.search(body.agent_id, body.query, body.top_k)
    return {"results": [e.to_dict() for e in results], "count": len(results)}


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str) -> Dict[str, Any]:
    """Delete a memory entry by ID."""
    store = get_store()
    ok = await store.delete(memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "id": memory_id}


@router.get("/memory/stats")
async def memory_stats() -> Dict[str, Any]:
    """Return MemoryStore statistics."""
    store = get_store()
    return await store.stats()
