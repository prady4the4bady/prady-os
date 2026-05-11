from __future__ import annotations

import numpy as np

from embedding_engine import EmbeddingEngine


def test_embed_shape_and_dtype():
    e = EmbeddingEngine()
    v = e.embed("hello world")
    assert v.shape == (384,)
    assert v.dtype == np.float32


def test_embed_is_deterministic_fallback():
    e = EmbeddingEngine()
    e._model = None
    e._use_fallback = True
    a = e.embed("same text")
    b = e.embed("same text")
    assert np.allclose(a, b)


def test_cosine_similarity_bounds():
    e = EmbeddingEngine()
    a = e.embed("alpha")
    b = e.embed("beta")
    sim = e.cosine_similarity(a, b)
    assert -1.0 <= sim <= 1.0


def test_serialize_deserialize_roundtrip():
    e = EmbeddingEngine()
    a = e.embed("round trip")
    raw = e.serialize(a)
    b = e.deserialize(raw)
    assert b.shape == (384,)
    assert np.allclose(a, b)
