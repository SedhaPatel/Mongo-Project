"""Voyage AI embedding wrapper with disk caching and retry logic.

Implements Voyage AI 1024-dimension embeddings (voyage-3-large)
per Section 2 and Section 7.6 of docs/PLAN.md.

VERIFY result (2026-10-31, https://docs.voyageai.com/docs/embeddings):
``voyage-3-large`` is a real model and its default output dimension is 1024
(2048/1024/512/256 selectable).  Only the documentation was checked here; no
live API call was possible without a key.

Resolution order for a text: disk cache -> committed offline fixture
(``seed/fixtures/text_embeddings.json``, synthetic demo data only) -> Voyage.
With ``OFFLINE=1`` a miss in both raises; it never silently fabricates a
vector for text that was not precomputed.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Union

import httpx

from backend.app.cache import compute_cache_key, get_cached_response, set_cached_response
from backend.app.config import EMBED_MODEL, OFFLINE, VOYAGE_API_KEY


VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
TEXT_EMBEDDINGS_FILE = (
    Path(__file__).resolve().parent.parent / "seed" / "fixtures" / "text_embeddings.json"
)


@lru_cache(maxsize=1)
def _fixture_table() -> Dict[str, Dict[str, List[float]]]:
    """Load the committed offline embeddings, if present."""
    try:
        with open(TEXT_EMBEDDINGS_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_fixture_embedding(text: str, input_type: str = "document") -> Optional[List[float]]:
    """Return a precomputed offline vector for this exact text, if any."""
    return _fixture_table().get(input_type, {}).get(text)


def get_embedding(
    text: str,
    input_type: str = "document",
    model: str = EMBED_MODEL,
    api_key: str = VOYAGE_API_KEY,
) -> List[float]:
    """Retrieves a 1024-dimensional embedding for a single string using Voyage AI.

    Caches results to CACHE_DIR to avoid redundant API hits and enable offline execution.
    """
    embeddings = get_embeddings([text], input_type=input_type, model=model, api_key=api_key)
    return embeddings[0]


def get_embeddings(
    texts: List[str],
    input_type: str = "document",
    model: str = EMBED_MODEL,
    api_key: str = VOYAGE_API_KEY,
) -> List[List[float]]:
    """Retrieves embeddings for multiple strings using Voyage AI."""
    cache_payload = {"texts": texts, "input_type": input_type}
    key = compute_cache_key(model, cache_payload)
    try:
        cached = get_cached_response(key)
    except RuntimeError:
        # OFFLINE=1 on a miss: the committed fixture below is the last resort.
        cached = None
    if cached is not None:
        return cached

    fixture = [get_fixture_embedding(text, input_type) for text in texts]
    if texts and all(vector is not None for vector in fixture):
        set_cached_response(key, fixture)
        return fixture  # type: ignore[return-value]

    if OFFLINE:
        raise RuntimeError(
            f"OFFLINE=1 and cache miss for key {key} "
            f"(no offline fixture for input_type='{input_type}')"
        )

    if not api_key:
        raise ValueError(
            "VOYAGE_API_KEY is not configured and embedding was not found in cache."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "input": texts,
        "model": model,
        "input_type": input_type,
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(VOYAGE_API_URL, headers=headers, json=payload)
        resp.raise_for_status()
        result = resp.json()

    embeddings = [item["embedding"] for item in result["data"]]
    set_cached_response(key, embeddings)
    return embeddings

