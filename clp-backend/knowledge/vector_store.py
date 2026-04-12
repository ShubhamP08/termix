"""
Vector store abstraction stub.

Intended to manage embeddings + similarity search for command descriptions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from rapidfuzz import fuzz, process

from utils.normalizer import normalize_text


class VectorHit(TypedDict):
    text: str
    score: float
    metadata: Dict[str, Any]


class VectorStore:
    """
    Minimal local "vector" store placeholder.

    This does NOT embed text yet; it uses RapidFuzz scoring to provide a
    semantic-ish search until real embeddings are introduced.
    """

    def __init__(self, items: Optional[List[VectorHit]] = None) -> None:
        self._items: List[VectorHit] = items or []

    def add(self, text: str, *, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._items.append(
            {"text": text, "score": 0.0, "metadata": metadata or {}},
        )

    def search(self, query: str, *, k: int = 5):
        normalized_query = normalize_text(query)
        if not normalized_query or not self._items:
            return []

        choices = [normalize_text(it["text"]) for it in self._items]
        extracted = process.extract(
            normalized_query,
            choices,
            scorer=fuzz.WRatio,
            limit=k,
        )

        hits: List[VectorHit] = []
        for _choice, score, idx in extracted:
            item = self._items[int(idx)]
            hits.append(
                {
                    "text": item["text"],
                    "score": float(score),
                    "metadata": dict(item.get("metadata") or {}),
                }
            )
        return hits

