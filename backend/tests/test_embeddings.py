"""Tests for Voyage AI embedding client and caching."""

import os
from backend.app.cache import compute_cache_key, get_cached_response
from backend.app.config import EMBED_MODEL
from backend.app.embeddings import get_embedding, get_embeddings


def test_embedding_dimension_and_caching():
    test_text = "Metrologic ISO/IEC 17025 test for Voyage embeddings"
    # First call will use cached or live API
    emb = get_embedding(test_text, input_type="document")
    assert isinstance(emb, list)
    assert len(emb) == 1024

    # Second call should read from disk cache
    key = compute_cache_key(EMBED_MODEL, {"texts": [test_text], "input_type": "document"})
    cached = get_cached_response(key)
    assert cached is not None
    assert len(cached[0]) == 1024
    assert cached[0] == emb
