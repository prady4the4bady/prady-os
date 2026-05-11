"""Embedding and similarity utilities with graceful fallback.

Phase 35 requirement: if sentence-transformers is unavailable,
use a deterministic hash-based 384-dim float32 embedding.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np


class EmbeddingEngine:
    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self) -> None:
        self._model: Any | None = None
        self._use_fallback = False

    def load(self) -> None:
        if self._model is not None or self._use_fallback:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL_NAME)
        except Exception:
            self._use_fallback = True

    def _fallback_embed(self, text: str) -> np.ndarray:
        # Deterministic pseudo-embedding from input hash.
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "little")
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(384).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.astype(np.float32)

    def embed(self, text: str) -> np.ndarray:
        self.load()
        if self._model is None:
            return self._fallback_embed(text)

        vec = self._model.encode([text], normalize_embeddings=True)[0]
        arr = np.asarray(vec, dtype=np.float32)
        if arr.shape[0] != 384:
            # Keep API stable if backend model shape differs.
            resized = np.zeros(384, dtype=np.float32)
            n = min(384, arr.shape[0])
            resized[:n] = arr[:n]
            arr = resized
        return arr

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        a = np.asarray(a, dtype=np.float32)
        b = np.asarray(b, dtype=np.float32)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0.0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def serialize(self, embedding: np.ndarray) -> bytes:
        return np.asarray(embedding, dtype=np.float32).tobytes()

    def deserialize(self, data: bytes) -> np.ndarray:
        arr = np.frombuffer(data, dtype=np.float32)
        return arr.copy()
