"""
Normalization utilities stub (e.g. whitespace, quoting normalization).
"""

from __future__ import annotations

import re
import string

_PUNCT_TRANSLATION_TABLE = str.maketrans("", "", string.punctuation)


def normalize_text(text: str) -> str:
    """
    Normalize free-form user text for downstream intent/routing.

    - Lowercases
    - Removes ASCII punctuation
    - Collapses extra whitespace
    """
    lowered = text.lower()
    no_punct = lowered.translate(_PUNCT_TRANSLATION_TABLE)
    collapsed_spaces = re.sub(r"\s+", " ", no_punct).strip()
    return collapsed_spaces

