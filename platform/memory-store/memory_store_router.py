"""Standalone FastAPI router for MemoryStore (no relative imports)."""
from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from memory_store import MemoryStore  # type: ignore[import-not-found]

router = APIRouter(tags=["memory"])
_store: Optional[MemoryStore] = None


def _ms() -> MemoryStore:
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
    entry = await _ms().store(body.agent_id, body.content, body.tags)
    return entry.to_dict()


@router.post("/memory/search")
async def search_memory(body: SearchRequest) -> Dict[str, Any]:
    results = await _ms().search(body.agent_id, body.query, body.top_k)
    return {"results": [e.to_dict() for e in results], "count": len(results)}


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str) -> Dict[str, Any]:
    ok = await _ms().delete(memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "id": memory_id}


@router.get("/memory/stats")
async def memory_stats() -> Dict[str, Any]:
    return await _ms().stats()
