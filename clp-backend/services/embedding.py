"""
Gemini embedding API wrapper.
"""

from __future__ import annotations

import os
from typing import List, Literal

import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

_EMBED_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/embedding-001")

TaskKind = Literal["document", "query"]


def get_embedding(text: str, *, task: TaskKind = "document") -> List[float]:
    """
    Return an embedding vector for ``text`` using the Gemini Embeddings API.

    ``task`` selects the API task type: ``document`` for KB entries, ``query`` for user input.
    """
    stripped = (text or "").strip()
    if not stripped:
        return []

    task_type = "retrieval_document" if task == "document" else "retrieval_query"

    result = genai.embed_content(
        model=_EMBED_MODEL,
        content=stripped,
        task_type=task_type,
    )
    emb = result.get("embedding")
    if isinstance(emb, list):
        return [float(x) for x in emb]
    return []
