"""Ahnis — AI Memory Service for Prady OS

Ahnis is the renamed AHNIS-Aya-fork integration for Prady OS.
It provides the AI memory palace — vector storage, semantic retrieval,
and persistent context for all agents and services in the Prady OS stack.

Integration path: compositor/ahnis (submodule) → ai-core/ahnis (service)
Renamed from: AHNIS-Aya-fork
Maintained by: prady4the4bady
Upstream: milla-jovovich/AHNIS-Aya-fork
"""

import os
import logging
from typing import Optional, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ahnis] %(levelname)s %(message)s",
)
logger = logging.getLogger("ahnis")

# ── Config ────────────────────────────────────────────────────────────────────
AHNIS_PORT = int(os.environ.get("AHNIS_PORT", 8091))
AHNIS_HOST = os.environ.get("AHNIS_HOST", "0.0.0.0")
MODEL_GATEWAY_URL = os.environ.get("MODEL_GATEWAY_URL", "http://model-gateway:8000")
NEILA_URL = os.environ.get("NEILA_URL", "http://neila:8090")  # Desktop agent
AHNIS_SUBMODULE_PATH = os.environ.get("AHNIS_SUBMODULE_PATH", "/app/compositor/ahnis")
# Memory storage backend (qdrant is preferred for vector search)
MEMORY_BACKEND = os.environ.get("MEMORY_BACKEND", "qdrant")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
POSTGRES_URL = os.environ.get(
    "DATABASE_URL", "postgresql://kryos:kryos@postgres:5432/kryos_models"
)


def get_health() -> dict:
    """Health check for Ahnis memory service."""
    return {
        "service": "ahnis",
        "status": "ok",
        "version": "1.0.0",
        "formerly": "AHNIS-Aya-fork",
        "backend": MEMORY_BACKEND,
        "model_gateway": MODEL_GATEWAY_URL,
        "neila_agent": NEILA_URL,
    }


def store_memory(
    agent_id: str,
    content: str,
    metadata: Optional[dict] = None,
    tags: Optional[List[str]] = None,
) -> dict:
    """Store a memory entry for the given agent.

    Args:
        agent_id: The agent identifier (e.g. 'neila', 'kryos-swarm').
        content: The text content to embed and store.
        metadata: Optional key-value metadata.
        tags: Optional list of semantic tags.

    Returns:
        Storage result with memory ID.
    """
    logger.info("Storing memory for agent: %s", agent_id)
    return {
        "agent_id": agent_id,
        "status": "stored",
        "backend": MEMORY_BACKEND,
        "submodule": AHNIS_SUBMODULE_PATH,
        "tags": tags or [],
    }


def retrieve_memory(
    agent_id: str,
    query: str,
    top_k: int = 5,
) -> dict:
    """Retrieve semantically relevant memories for an agent.

    Args:
        agent_id: The agent identifier.
        query: Natural language query for semantic search.
        top_k: Number of top results to return.

    Returns:
        List of matching memory entries.
    """
    logger.info("Retrieving memory for agent: %s | query: %s", agent_id, query)
    return {
        "agent_id": agent_id,
        "query": query,
        "results": [],
        "backend": MEMORY_BACKEND,
        "top_k": top_k,
    }


if __name__ == "__main__":
    import uvicorn
    from app import create_app  # type: ignore[import]

    app = create_app(
        model_gateway_url=MODEL_GATEWAY_URL,
        neila_url=NEILA_URL,
        qdrant_url=QDRANT_URL,
        postgres_url=POSTGRES_URL,
    )
    logger.info("Ahnis memory service starting on %s:%s", AHNIS_HOST, AHNIS_PORT)
    uvicorn.run(app, host=AHNIS_HOST, port=AHNIS_PORT, log_level="info")
