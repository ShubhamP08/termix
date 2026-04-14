"""
Knowledge base utilities.

Thin helpers for loading the KB and checking embedding status.
Embeddings are now stored inline in ``knowledge_base.json`` — there is
no separate ``data/embeddings.json`` file.

For rebuilding embeddings, use ``knowledge.semantic.rebuild_embeddings()``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)


def get_kb_path() -> str:
    """Get the knowledge base file path."""
    return os.path.join(os.path.dirname(__file__), "..", "knowledge", "knowledge_base.json")


def load_kb() -> dict:
    """Load knowledge base from disk."""
    kb_path = get_kb_path()
    with open(kb_path, "r", encoding="utf-8") as f:
        return json.load(f)


def embeddings_status() -> dict:
    """
    Get status of inline embeddings in the KB.

    Returns:
        {
            "kb_count": number of KB rules,
            "embedding_count": rules that have a non-empty embedding,
            "missing_count": rules without embeddings,
            "is_valid": all rules have embeddings
        }
    """
    kb = load_kb()
    rules = kb.get("rules", [])
    kb_count = len(rules)

    has_embedding = 0
    missing_ids: list = []

    for rule in rules:
        emb = rule.get("embedding")
        if isinstance(emb, list) and len(emb) > 0:
            has_embedding += 1
        else:
            rule_id = rule.get("id", "unknown")
            if len(missing_ids) < 5:
                missing_ids.append(rule_id)

    return {
        "kb_count": kb_count,
        "embedding_count": has_embedding,
        "missing_count": kb_count - has_embedding,
        "missing_ids": missing_ids,
        "is_valid": has_embedding == kb_count,
    }


def validate_embeddings() -> bool:
    """
    Check if embeddings are valid and up-to-date.

    Returns True if all KB rules have inline embeddings.
    """
    status = embeddings_status()
    is_valid = status["is_valid"]

    if not is_valid:
        logger.warning(
            "Embeddings invalid: %d/%d (%d missing)",
            status["embedding_count"],
            status["kb_count"],
            status["missing_count"],
        )

    return is_valid


def ensure_embeddings_exist() -> bool:
    """
    Check if inline embeddings exist and rebuild if necessary.

    Returns True if embeddings are valid after this call.
    """
    if validate_embeddings():
        return True

    logger.info("Embeddings missing or outdated, rebuilding...")
    try:
        from knowledge.semantic import rebuild_embeddings
        rebuild_embeddings()
        return validate_embeddings()
    except Exception as e:
        logger.error("Failed to rebuild embeddings: %s", e)
        return False
