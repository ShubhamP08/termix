"""
Unified embedding module.

Provides a single ``get_embedding(text, task)`` entry point that:
  1. Tries the Gemini Embeddings API (if GEMINI_API_KEY is set).
  2. Falls back to a local TF (term-frequency) vector built from the KB vocabulary.

Embeddings are used for:
  - **document**: building stored KB embeddings (via ``rebuild_embeddings``).
  - **query**: embedding user input at search time.

Design notes:
  - One module, one function signature — no second ``embedding_api`` module.
  - TF fallback is deterministic and works offline (no API key needed).
  - The vocabulary for TF is lazily built from ``knowledge_base.json`` and cached.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import List, Literal

logger = logging.getLogger(__name__)

TaskKind = Literal["document", "query"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_embedding(text: str, *, task: TaskKind = "document") -> List[float]:
    """
    Return an embedding vector for *text*.

    Parameters
    ----------
    text : str
        The text to embed.
    task : "document" | "query"
        ``document`` for KB entries (stored at index time),
        ``query`` for user input (used at search time).

    Returns
    -------
    List[float]
        Embedding vector.  Empty list if *text* is blank.
    """
    stripped = (text or "").strip()
    if not stripped:
        return []

    # Try Gemini first (if API key is available)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            return _get_gemini_embedding(stripped, task=task, api_key=api_key)
        except Exception as exc:
            logger.warning("Gemini embedding failed, falling back to TF: %s", exc)

    # Fallback: local TF vector (always works, no network needed)
    return _get_tf_embedding(stripped)


# ---------------------------------------------------------------------------
# Gemini embeddings
# ---------------------------------------------------------------------------

_EMBED_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/embedding-001")


def _get_gemini_embedding(
    text: str,
    *,
    task: TaskKind,
    api_key: str,
) -> List[float]:
    """Call the Gemini Embeddings API."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)

    task_type = "retrieval_document" if task == "document" else "retrieval_query"

    result = genai.embed_content(
        model=_EMBED_MODEL,
        content=text,
        task_type=task_type,
    )
    emb = result.get("embedding")
    if isinstance(emb, list) and emb:
        logger.debug("Gemini embedding: %d dimensions", len(emb))
        return [float(x) for x in emb]

    raise ValueError("Gemini returned empty embedding")


# ---------------------------------------------------------------------------
# TF (term-frequency) fallback
# ---------------------------------------------------------------------------

def _get_tf_embedding(text: str) -> List[float]:
    """
    Build a simple term-frequency vector using the KB vocabulary.

    Each dimension corresponds to a word in the KB.  The value is
    ``count(word) / total_words`` in the input text.  This gives a
    sparse but deterministic embedding that works for cosine similarity
    without any external API.
    """
    words = text.lower().split()
    vocab = _get_vocab()
    embedding = [0.0] * len(vocab)

    word_count = len(words)
    if word_count == 0:
        return embedding

    for word in words:
        clean_word = "".join(c for c in word if c.isalnum() or c == "_")
        if clean_word in vocab:
            idx = vocab[clean_word]
            embedding[idx] += 1.0 / word_count

    logger.debug("TF embedding: %d dimensions", len(embedding))
    return embedding


@lru_cache(maxsize=1)
def _get_vocab() -> dict:
    """
    Build a sorted vocabulary from all text fields in the KB.

    Cached so we only read the file once per process.
    """
    vocab: dict = {}
    kb_path = os.path.join(
        os.path.dirname(__file__), "..", "knowledge", "knowledge_base.json"
    )

    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            kb = json.load(f)

        word_set: set = set()
        for rule in kb.get("rules", []):
            texts = [
                rule.get("intent", ""),
                rule.get("description", ""),
            ]
            texts.extend(rule.get("examples", []))
            text_field = rule.get("text", "")
            if text_field:
                texts.append(text_field)

            for t in texts:
                if t:
                    for w in str(t).lower().split():
                        clean = "".join(c for c in w if c.isalnum() or c == "_")
                        if clean:
                            word_set.add(clean)

        for idx, word in enumerate(sorted(word_set)):
            vocab[word] = idx

        logger.info("Built TF vocabulary: %d unique words", len(vocab))
    except Exception as exc:
        logger.error("Failed to build vocabulary: %s", exc)

    return vocab


def clear_embedding_cache() -> None:
    """Clear the cached TF vocabulary (e.g. after KB update)."""
    _get_vocab.cache_clear()
