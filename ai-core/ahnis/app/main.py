"""Ahnis — AHNIS-Aya memory and retrieval system for Prady OS.

Pluggable semantic memory with local embedding fallback.
Categories: conversation, task, skill, project, summary, failure_lesson.
Qdrant integration when available; in-memory fallback always works.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.embeddings import EmbeddingProvider, ProviderInfo, get_provider
from app.persistence import AhnisStore

VERSION = "1.2.0"
SERVICE_NAME = "ahnis"

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

AUDIT_URL = os.getenv("AUDIT_LOG_URL", "http://audit-log:8112")

# --- Memory Categories ---
CATEGORIES = {"conversation", "task", "skill", "project", "summary", "failure_lesson"}

# --- Scoring weights for retrieval ---
SCORE_EXACT_MATCH = 1.0
SCORE_TOKEN_OVERLAP = 0.7
SCORE_FUZZY = 0.4
SCORE_FALLBACK = 0.1

_provider: EmbeddingProvider = get_provider()
_memory_store: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
_consolidation_ts: str = ""
_hit_count = 0
_miss_count = 0
_uptime_start = time.time()
_restored_on_startup = 0

_persistence = AhnisStore()
_persistence_available = _persistence.is_available


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class WriteRequest(BaseModel):
    category: str = "conversation"
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class WriteResponse(BaseModel):
    status: str
    entry_id: str


class SearchRequest(BaseModel):
    query: str = ""
    category: str | None = None
    limit: int = 10
    min_relevance: float = 0.0
    include_embeddings: bool = False


class SearchResult(BaseModel):
    id: str
    category: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""
    relevance: float = 0.0


class SearchResponse(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    count: int = 0
    backend: str = ""
    query: str = ""


class SummarizeRequest(BaseModel):
    category: str = "conversation"


class SummarizeResponse(BaseModel):
    summary: str = ""
    count: int = 0
    entry_id: str = ""


class ConsolidateResponse(BaseModel):
    status: str
    entries_before: int
    entries_after: int
    ts: str


class DeleteResponse(BaseModel):
    status: str
    entry_id: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class EmbeddingInfo(BaseModel):
    provider_name: str
    dimension: int
    backend_capability: str
    available: bool


class AhnisStatusResponse(BaseModel):
    qdrant_available: bool
    backend: str
    embedding_provider: str
    embedding_dimension: int
    total_entries: int
    by_category: dict[str, int] = Field(default_factory=dict)
    last_consolidation_ts: str = ""
    hit_count: int = 0
    miss_count: int = 0
    persistence_available: bool = False
    persisted_entry_count: int = 0


class AuditEvent(BaseModel):
    event_type: str
    source: str = "ahnis"
    correlation_id: str = ""
    status: str = "success"
    detail: dict[str, Any] = Field(default_factory=dict)


class MetricsResponse(BaseModel):
    total_entries: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    hit_count: int = 0
    miss_count: int = 0
    consolidation_count: int = 0
    embedding_provider: str = ""
    embedding_dimension: int = 0
    uptime_seconds: float = 0.0
    persisted_entry_count: int = 0
    restored_on_startup: int = 0
    backend_mode: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _audit(event_type: str, detail: dict[str, Any], correlation_id: str = "", status: str = "success") -> None:
    try:
        event = AuditEvent(
            event_type=event_type,
            source="ahnis",
            correlation_id=correlation_id or str(uuid.uuid4()),
            status=status,
            detail=detail,
        )
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.post(f"{AUDIT_URL}/events", json=event.model_dump())
    except Exception:
        pass


def _compute_local_embedding(text: str) -> list[float]:
    return _provider.compute(text)


def _score_entries(query: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not query:
        return [{**e, "relevance": SCORE_FALLBACK} for e in entries]
    q_terms = set(re.findall(r'\w+', query.lower()))
    scored = []
    for entry in entries:
        content = entry.get("content", "")
        content_lower = content.lower()
        if query.lower() in content_lower:
            score = SCORE_EXACT_MATCH
        else:
            c_terms = set(re.findall(r'\w+', content_lower))
            if q_terms and c_terms:
                overlap = len(q_terms & c_terms)
                ratio = overlap / max(len(q_terms), 1)
                score = SCORE_TOKEN_OVERLAP * ratio
            else:
                score = SCORE_FALLBACK
        if score < SCORE_FUZZY and query.lower()[:3] in content_lower:
            score = SCORE_FUZZY
        scored.append({**entry, "relevance": round(min(score, 1.0), 4)})
    scored.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    return scored


def _provider_info() -> ProviderInfo:
    return _provider.info()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _provider, _memory_store, _restored_on_startup, _persistence_available
    pi = _provider_info()
    _persistence_available = _persistence.is_available
    if _persistence_available:
        restored = _persistence.restore_entries()
        _restored_on_startup = sum(len(v) for v in restored.values())
        if _restored_on_startup > 0:
            _memory_store = restored
            logger.info("Ahnis restored %d entries from persistence", _restored_on_startup)
    else:
        logger.warning("Ahnis persistence unavailable; running in-memory only")
    logger.info(
        "Ahnis embedding provider: %s (dim=%d, backend=%s, available=%s)",
        pi.name, pi.dimension, pi.backend_capability, pi.available,
    )
    await _audit("ahnis_startup", {
        "provider": pi.name,
        "dimension": pi.dimension,
        "backend": pi.backend_capability,
        "persistence_available": _persistence_available,
        "restored_entries": _restored_on_startup,
    })
    yield
    _persistence.close()


app = FastAPI(title="Prady OS Ahnis — Memory Palace", version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=VERSION)


@app.get("/ahnis/status", response_model=AhnisStatusResponse)
async def ahnis_status() -> AhnisStatusResponse:
    pi = _provider_info()
    total = sum(len(v) for v in _memory_store.values())
    return AhnisStatusResponse(
        qdrant_available=("qdrant" in pi.backend_capability),
        backend="qdrant" if "qdrant" in pi.backend_capability else f"in-memory ({pi.backend_capability})",
        embedding_provider=pi.name,
        embedding_dimension=pi.dimension,
        total_entries=total,
        by_category={k: len(v) for k, v in _memory_store.items()},
        last_consolidation_ts=_consolidation_ts,
        hit_count=_hit_count,
        miss_count=_miss_count,
        persistence_available=_persistence_available,
        persisted_entry_count=_persistence.persisted_count(),
    )


@app.get("/ahnis/embeddings/provider", response_model=EmbeddingInfo)
async def ahnis_embedding_provider() -> EmbeddingInfo:
    pi = _provider_info()
    return EmbeddingInfo(
        provider_name=pi.name,
        dimension=pi.dimension,
        backend_capability=pi.backend_capability,
        available=pi.available,
    )


@app.get("/ahnis/metrics", response_model=MetricsResponse)
async def ahnis_metrics() -> MetricsResponse:
    total = sum(len(v) for v in _memory_store.values())
    pi = _provider_info()
    return MetricsResponse(
        total_entries=total,
        by_category={k: len(v) for k, v in _memory_store.items()},
        hit_count=_hit_count,
        miss_count=_miss_count,
        embedding_provider=pi.name,
        embedding_dimension=pi.dimension,
        uptime_seconds=time.time() - _uptime_start,
        persisted_entry_count=_persistence.persisted_count(),
        restored_on_startup=_restored_on_startup,
        backend_mode=pi.backend_capability,
    )


@app.post("/memory/write", response_model=WriteResponse)
async def memory_write(req: WriteRequest) -> WriteResponse:
    if req.category not in CATEGORIES:
        raise HTTPException(400, f"Unknown category: {req.category}. Valid: {sorted(CATEGORIES)}")
    pi = _provider_info()
    emb = _provider.compute(req.content)
    entry_id = str(uuid.uuid4())
    entry = {
        "id": entry_id,
        "category": req.category,
        "content": req.content,
        "metadata": req.metadata,
        "timestamp": _utc_now(),
        "embedding": emb,
        "relevance": 0.0,
        "embedding_backend": pi.backend_capability,
    }
    _memory_store[req.category].append(entry)
    _persistence.save_entry(entry)
    cap = 10000
    if len(_memory_store[req.category]) > cap:
        _memory_store[req.category] = _memory_store[req.category][-5000:]
    await _audit("memory_write", {
        "category": req.category, "entry_id": entry_id,
        "content_length": len(req.content), "persistence": _persistence_available,
    })
    return WriteResponse(status="written", entry_id=entry_id)


@app.post("/memory/search", response_model=SearchResponse)
async def memory_search(req: SearchRequest) -> SearchResponse:
    global _hit_count, _miss_count
    pi = _provider_info()
    candidates = _memory_store.get(req.category, []) if req.category else [e for v in _memory_store.values() for e in v]
    scored = _score_entries(req.query, candidates)
    if req.min_relevance > 0:
        scored = [e for e in scored if e.get("relevance", 0) >= req.min_relevance]
    results = scored[:max(1, min(req.limit, 50))]
    if not req.include_embeddings:
        for r in results:
            r.pop("embedding", None)
    if results:
        _hit_count += 1
    else:
        _miss_count += 1
    backend_label = "qdrant" if "qdrant" in pi.backend_capability else f"in-memory ({pi.backend_capability})"
    return SearchResponse(
        results=[SearchResult(**r) for r in results],
        count=len(results),
        backend=backend_label,
        query=req.query,
    )


@app.post("/memory/summarize", response_model=SummarizeResponse)
async def memory_summarize(req: SummarizeRequest) -> SummarizeResponse:
    pi = _provider_info()
    entries = _memory_store.get(req.category, [])
    if not entries:
        return SummarizeResponse(summary="", count=0)
    summary_text = f"{len(entries)} entries in {req.category}. Latest: {entries[-1].get('content', '')[:300]}"
    entry_id = str(uuid.uuid4())
    summary_entry = {
        "id": entry_id,
        "category": "summary",
        "content": summary_text,
        "metadata": {"source_category": req.category, "count": len(entries)},
        "timestamp": _utc_now(),
        "embedding": _provider.compute(summary_text),
        "relevance": 0.0,
        "embedding_backend": pi.backend_capability,
    }
    _memory_store["summary"].append(summary_entry)
    _persistence.save_entry(summary_entry)
    await _audit("memory_summarize", {
        "category": req.category, "count": len(entries), "entry_id": entry_id,
        "persistence": _persistence_available,
    })
    return SummarizeResponse(summary=summary_text, count=len(entries), entry_id=entry_id)


@app.post("/memory/consolidate", response_model=ConsolidateResponse)
async def memory_consolidate() -> ConsolidateResponse:
    global _consolidation_ts
    total_before = sum(len(v) for v in _memory_store.values())
    for cat in CATEGORIES:
        if len(_memory_store[cat]) > 2000:
            _memory_store[cat] = _memory_store[cat][-1000:]
    _consolidation_ts = _utc_now()
    total_after = sum(len(v) for v in _memory_store.values())
    await _audit("memory_consolidated", {"entries_before": total_before, "entries_after": total_after})
    return ConsolidateResponse(status="consolidated", entries_before=total_before, entries_after=total_after, ts=_consolidation_ts)


@app.delete("/memory/{entry_id}", response_model=DeleteResponse)
async def memory_delete(entry_id: str) -> DeleteResponse:
    for cat in CATEGORIES:
        before = len(_memory_store[cat])
        _memory_store[cat] = [e for e in _memory_store[cat] if e.get("id") != entry_id]
        if len(_memory_store[cat]) < before:
            _persistence.delete_entry(entry_id)
            await _audit("memory_deleted", {
                "category": cat, "entry_id": entry_id,
                "persistence": _persistence_available,
            })
            return DeleteResponse(status="deleted", entry_id=entry_id)
    raise HTTPException(404, f"Entry {entry_id} not found")


@app.get("/memory/skills", response_model=list[dict[str, Any]])
async def memory_skills() -> list[dict[str, Any]]:
    return _memory_store.get("skill", [])


@app.get("/memory/projects", response_model=list[dict[str, Any]])
async def memory_projects() -> list[dict[str, Any]]:
    return _memory_store.get("project", [])


# ---------------------------------------------------------------------------
# Backward-compatible aliases (accept raw JSON body for summarize/consolidate)
# ---------------------------------------------------------------------------


@app.post("/memory/summarize_legacy")
async def memory_summarize_legacy(body: dict[str, Any]) -> dict[str, Any]:
    req = SummarizeRequest(category=body.get("category", "conversation"))
    result = await memory_summarize(req)
    return {"summary": result.summary, "count": result.count}


@app.post("/memory/consolidate_legacy")
async def memory_consolidate_legacy() -> dict[str, Any]:
    result = await memory_consolidate()
    return {"status": result.status, "entries_before": result.entries_before, "entries_after": result.entries_after, "ts": result.ts}
