"""RAGStore: ChromaDB-backed shared semantic memory for swarm agents."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import anyio
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class RAGStore:
    """Wraps a ChromaDB client, providing namespace-isolated semantic memory."""

    def __init__(self, path: str = "/opt/kryos/chromadb") -> None:
        if path == ":memory:":
            # Ephemeral in-process client (no persistence, no pydantic Settings issue)
            self._client = chromadb.EphemeralClient()
        else:
            settings = Settings(
                is_persistent=True,
                persist_directory=path,
                anonymized_telemetry=False,
            )
            self._client = chromadb.Client(settings)
        self._collections: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collection(self, namespace: str) -> Any:
        if namespace not in self._collections:
            self._collections[namespace] = self._client.get_or_create_collection(
                name=namespace,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[namespace]

    # ------------------------------------------------------------------
    # Public API (async surface; ChromaDB is sync under the hood)
    # ------------------------------------------------------------------

    async def upsert(
        self,
        namespace: str,
        key: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store or update a document in the given namespace."""
        await anyio.sleep(0)
        col = self._collection(namespace)
        # chromadb requires non-empty metadata dicts
        effective_meta = metadata if metadata else {"_source": "kryos-swarm"}
        col.upsert(
            ids=[key],
            documents=[content],
            metadatas=[effective_meta],
        )
        logger.debug("RAGStore.upsert namespace=%s key=%s", namespace, key)

    async def search(
        self,
        namespace: str,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantic similarity search; returns top_k results with distance."""
        await anyio.sleep(0)
        col = self._collection(namespace)
        results = col.query(
            query_texts=[query],
            n_results=min(top_k, col.count() or 1),
            include=["documents", "metadatas", "distances"],
        )
        hits: List[Dict[str, Any]] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append({"content": doc, "metadata": meta, "distance": dist})
        return hits

    async def delete(self, namespace: str, key: str) -> None:
        """Delete a single document by key from the given namespace."""
        await anyio.sleep(0)
        col = self._collection(namespace)
        col.delete(ids=[key])
        logger.debug("RAGStore.delete namespace=%s key=%s", namespace, key)
