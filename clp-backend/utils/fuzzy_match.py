"""
Fuzzy matching stub (e.g. for command aliases / intent labels).
"""

from __future__ import annotations

from typing import Iterable, Optional, Tuple

from rapidfuzz import fuzz, process

def match_query(query: str, choices: Iterable[str]) -> Tuple[Optional[str], float]:
    """
    Return the best match and its score (0-100) using RapidFuzz.
    """
    choices_list = list(choices)
    if not choices_list:
        return None, 0.0

    result = process.extractOne(query, choices_list, scorer=fuzz.WRatio)
    if result is None:
        return None, 0.0

    match, score, _idx = result
    return match, float(score)

