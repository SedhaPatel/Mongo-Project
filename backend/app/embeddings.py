"""Voyage AI embedding wrapper with disk caching and retry logic.

Implements Voyage AI 1024-dimension embeddings (voyage-3-large)
per Section 2 and Section 7.6 of docs/PLAN.md.
"""

from typing import List, Union
import httpx

from backend.app.cache import compute_cache_key, get_cached_response, set_cached_response
from backend.app.config import EMBED_MODEL, VOYAGE_API_KEY


VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"


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
    cached = get_cached_response(key)
    if cached is not None:
        return cached

    if not api_key:
        raise ValueError("VOYAGE_API_KEY is not configured and embedding was not found in cache.")

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
