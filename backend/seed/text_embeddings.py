"""Deterministic offline fixture embeddings (PLAN Section 7.6).

This is **not** a replacement for Voyage.  It exists so the synthetic demo can
be replayed on a laptop with no ``VOYAGE_API_KEY`` and no network:

- only exact ``(input_type, text)`` pairs that were precomputed into
  ``seed/fixtures/text_embeddings.json`` resolve here;
- anything else still raises, so a real deployment cannot silently receive
  made-up vectors;
- with a key configured, ``embeddings.get_embeddings`` calls Voyage and never
  reaches this module.

Vectors are 1024-dimensional signed hashes of stemmed words, L2-normalised.
That keeps the synthetic corpus self-consistent (texts that share domain words
are close) while remaining reproducible byte for byte.
"""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List

DIM = 1024
FIXTURE_FILE = Path(__file__).resolve().parent / "fixtures" / "text_embeddings.json"

# The query the demo uses in Stage 2 and Stage 3 (PLAN Section 10).
STAGE2_QUERY = "Process plan for an Inconel 718 sleeve with a Ø28H7 bore"

# Text used by backend/tests/test_embeddings.py; precomputed so the suite is
# reproducible without a Voyage key.
EMBEDDING_TEST_TEXT = "Metrologic ISO/IEC 17025 test for Voyage embeddings"


def _stem(word: str) -> str:
    for suffix in ("ing", "ed"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            word = word[: -len(suffix)]
            break
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    if word.endswith("s") and len(word) > 3:
        word = word[:-1]
    return word


def _tokens(text: str) -> List[str]:
    normalised = text.lower().replace("Ø", " o").replace("µ", " u")
    return [
        "w:" + _stem(word)
        for word in re.findall(r"[a-z0-9]+", normalised)
        if len(word) >= 2
    ]


def embed_text(text: str) -> List[float]:
    """Return a deterministic 1024-dimensional unit vector for ``text``."""
    vector = [0.0] * DIM
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % DIM
        sign = 1.0 if (value >> 63) & 1 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [round(x / norm, 6) for x in vector]


def lesson_embed_text(lesson: Dict[str, Any]) -> str:
    """The exact document string ``write_lesson`` embeds (PLAN 7.2 step 3)."""
    return f"{lesson['title']}. {lesson['content']} Action: {lesson['action']}"


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def build_fixture() -> Dict[str, Dict[str, List[float]]]:
    """Build the ``{"document": {...}, "query": {...}}`` fixture table."""
    ncr = _load_json(FIXTURE_FILE.parent / "ncr_0412_lessons.json")
    table: Dict[str, Dict[str, List[float]]] = {"document": {}, "query": {}}

    for lesson in ncr["lessons"]:
        text = lesson_embed_text(lesson)
        table["document"][text] = embed_text(text)

    table["document"][EMBEDDING_TEST_TEXT] = embed_text(EMBEDDING_TEST_TEXT)
    table["query"][STAGE2_QUERY] = embed_text(STAGE2_QUERY)
    return table


def write_fixture(path: Path = FIXTURE_FILE) -> Path:
    table = build_fixture()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(table, handle, indent=1)
    return path


if __name__ == "__main__":
    written = write_fixture()
    table = build_fixture()
    print(f"Wrote {sum(len(v) for v in table.values())} fixture embeddings to {written}")
