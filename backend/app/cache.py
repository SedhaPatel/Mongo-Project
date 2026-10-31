"""Disk caching mechanism for Metrologic LLM and Embedding calls.

Implements Section 7.6 of docs/PLAN.md:
Disk cache keyed by sha256(model + canonical JSON input) in CACHE_DIR.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from backend.app.config import CACHE_DIR, OFFLINE


def _get_cache_path(key: str) -> Path:
    cache_path = Path(CACHE_DIR)
    cache_path.mkdir(parents=True, exist_ok=True)
    return cache_path / f"{key}.json"


def compute_cache_key(model: str, payload: Any) -> str:
    canonical = json.dumps({"model": model, "payload": payload}, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_cached_response(key: str) -> Optional[Any]:
    path = _get_cache_path(key)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    if OFFLINE:
        raise RuntimeError(f"OFFLINE=1 and cache miss for key {key}")
    return None


def set_cached_response(key: str, data: Any) -> None:
    path = _get_cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to write to cache {path}: {e}")
