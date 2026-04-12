"""
Lightweight vector similarity helpers (no numpy/scipy).
"""

from __future__ import annotations

import math
from typing import Sequence


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """
    Cosine similarity in [-1, 1]. Returns 0.0 if either vector is empty or zero-norm.
    """
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y

    if na <= 0.0 or nb <= 0.0:
        return 0.0

    return dot / (math.sqrt(na) * math.sqrt(nb))
