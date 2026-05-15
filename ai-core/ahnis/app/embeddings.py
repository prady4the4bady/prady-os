"""Pluggable embedding providers for Ahnis memory system.

Each provider implements EmbeddingProvider and reports its capabilities.
Providers are loaded by convention -- add a new class in this module and
register it in get_provider() to extend.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProviderInfo:
    name: str
    dimension: int
    backend_capability: str  # "local" | "qdrant" | "sentence-transformer" | "cloud"
    available: bool = True


class EmbeddingProvider(ABC):
    @abstractmethod
    def compute(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def info(self) -> ProviderInfo:
        ...

    @abstractmethod
    def dimension(self) -> int:
        ...


class LocalHashProvider(EmbeddingProvider):
    """Deterministic hash-based embedding. No dependencies. Always available."""

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    def compute(self, text: str) -> list[float]:
        tokens = re.findall(r'\w+', text.lower())
        vec = [0.0] * self._dim
        if not tokens:
            return vec
        for token in tokens:
            h = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16)
            for i in range(self._dim):
                vec[i] += 1.0 if (h >> (i % 32)) & 1 else -1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="local-hash",
            dimension=self._dim,
            backend_capability="local",
            available=True,
        )

    def dimension(self) -> int:
        return self._dim


class SentenceTransformerProvider(EmbeddingProvider):
    """Wraps sentence-transformers for learned semantic embeddings.

    Falls back to LocalHashProvider when the library is not installed.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or os.getenv(
            "AHNIS_ST_MODEL", "all-MiniLM-L6-v2"
        )
        self._model = None
        self._dim = 384  # default for all-MiniLM-L6-v2
        self._available = False
        self._fallback = LocalHashProvider()
        self._init_model()

    def _init_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
            self._model = SentenceTransformer(self._model_name)
            self._dim = self._model.get_sentence_embedding_dimension() or 384
            self._available = True
            logger.info(
                "SentenceTransformer loaded: %s (dim=%d)",
                self._model_name, self._dim,
            )
        except Exception as exc:
            logger.warning(
                "SentenceTransformer unavailable (%s); using local-hash fallback",
                exc,
            )
            self._available = False

    def compute(self, text: str) -> list[float]:
        if self._available and self._model is not None:
            vec = self._model.encode(text).tolist()
            return [float(v) for v in vec]
        return self._fallback.compute(text)

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="sentence-transformer"
            if self._available
            else "sentence-transformer (fell back to local-hash)",
            dimension=self.dimension(),
            backend_capability="sentence-transformer",
            available=self._available,
        )

    def dimension(self) -> int:
        return self._fallback.dimension() if not self._available else self._dim


try:
    from qdrant_client import QdrantClient  # type: ignore[import-untyped]
except ImportError:
    QdrantClient = None  # type: ignore[assignment]


class QdrantProvider(EmbeddingProvider):
    """Optional Qdrant-backed vector storage.

    When Qdrant is not configured or unreachable, delegates to the
    wrapped inner provider (typically SentenceTransformerProvider).
    """

    def __init__(self, inner: EmbeddingProvider | None = None) -> None:
        self._inner = inner or SentenceTransformerProvider()
        self._host = os.getenv("QDRANT_HOST", "")
        self._port = int(os.getenv("QDRANT_PORT", "6333"))
        self._client: Any = None
        self._available = False
        self._collection_name = os.getenv("QDRANT_COLLECTION", "ahnis_memories")
        self._connect()

    def _connect(self) -> None:
        if not QdrantClient or not self._host:
            self._available = False
            return
        try:
            self._client = QdrantClient(host=self._host, port=self._port)
            self._client.get_collections()
            self._available = True
            logger.info(
                "Qdrant connected at %s:%d", self._host, self._port
            )
        except Exception as exc:
            logger.warning("Qdrant unreachable (%s); using inner provider", exc)
            self._available = False

    def compute(self, text: str) -> list[float]:
        return self._inner.compute(text)

    def info(self) -> ProviderInfo:
        inner_info = self._inner.info()
        dim = self.dimension()
        if self._available:
            return ProviderInfo(
                name="qdrant",
                dimension=dim,
                backend_capability="qdrant",
                available=True,
            )
        return ProviderInfo(
            name=f"qdrant-unavailable (inner: {inner_info.name})",
            dimension=dim,
            backend_capability="local",
            available=False,
        )

    def dimension(self) -> int:
        return self._inner.dimension()

    @property
    def client(self) -> Any:
        return self._client

    @property
    def inner(self) -> EmbeddingProvider:
        return self._inner

    @property
    def collection_name(self) -> str:
        return self._collection_name


def get_provider() -> EmbeddingProvider:
    """Factory that returns the best available embedding provider.

    Resolution order:
    1. QdrantProvider (wraps sentence-transformer or hash fallback)
    2. SentenceTransformerProvider (if sentence-transformers installed)
    3. LocalHashProvider (always available)
    """
    embedding_mode = os.getenv("AHNIS_EMBEDDING_MODE", "auto")

    if embedding_mode == "qdrant":
        inner = SentenceTransformerProvider()
        qp = QdrantProvider(inner=inner)
        if qp._available:
            return qp
        logger.warning("Qdrant requested but unavailable; falling back")
        return inner if inner._available else LocalHashProvider()

    if embedding_mode == "sentence-transformer":
        st = SentenceTransformerProvider()
        return st if st._available else LocalHashProvider()

    if embedding_mode == "local-hash":
        return LocalHashProvider()

    # auto: try qdrant first, then sentence-transformer, always fall back to hash
    if QdrantClient is not None:
        inner = SentenceTransformerProvider()
        qp = QdrantProvider(inner=inner)
        if qp._available:
            return qp
        if inner._available:
            return inner
    else:
        st = SentenceTransformerProvider()
        if st._available:
            return st

    return LocalHashProvider()
