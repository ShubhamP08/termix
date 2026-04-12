"""
Semantic KB search (local cosine over stored embeddings) and embedding rebuild.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.embedding import get_embedding
from utils.similarity import cosine_similarity

logger = logging.getLogger(__name__)

_SEMANTIC_THRESHOLD = 0.75
_auto_rebuild_done = False


def _kb_path(path: Optional[str] = None) -> str:
    if path:
        return path
    from knowledge.retriever import _default_kb_path

    return _default_kb_path()


def build_rule_text(rule: Dict[str, Any]) -> str:
    """Natural-language text used for embedding and fuzzy/semantic routing."""
    intent = (rule.get("intent") or "").strip()
    desc = (rule.get("description") or "").strip()
    parts: List[str] = []
    if intent:
        parts.append(intent)
    if desc:
        parts.append(desc)
    examples = rule.get("examples")
    if isinstance(examples, list) and examples:
        ex_strs = [str(e).strip() for e in examples if isinstance(e, str) and str(e).strip()]
        if ex_strs:
            parts.append("Examples: " + "; ".join(ex_strs))
    text = rule.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return ". ".join(parts) if parts else intent or desc or ""


def rebuild_embeddings(path: Optional[str] = None) -> None:
    """
    For each KB rule: ensure ``id``, ``text``, ``command`` (linux template or legacy), and ``embedding``.
    Writes the updated KB to disk and clears the in-memory KB cache.
    """
    from knowledge.retriever import canonical_kb_command, clear_knowledge_cache

    kb_path = _kb_path(path)
    with open(kb_path, "r", encoding="utf-8") as f:
        kb = json.load(f)

    rules = kb.get("rules") or []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rid = rule.get("id")
        if not isinstance(rid, str) or not rid.strip():
            rule["id"] = str(uuid.uuid4())

        text = build_rule_text(rule)
        rule["text"] = text

        cmd = canonical_kb_command(rule)  # type: ignore[arg-type]
        if cmd:
            rule["command"] = cmd

        if not text:
            rule["embedding"] = []
            continue

        try:
            rule["embedding"] = get_embedding(text, task="document")
        except Exception:
            logger.exception("Embedding failed for rule id=%s", rule.get("id"))
            rule["embedding"] = []

    kb["rules"] = rules
    with open(kb_path, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=2, ensure_ascii=False)
        f.write("\n")

    clear_knowledge_cache()
    logger.info("rebuild_embeddings: wrote %d rules to %s", len(rules), kb_path)


@dataclass(frozen=True)
class SemanticHit:
    command: str
    similarity: float
    rule: Dict[str, Any]


def semantic_search(
    user_input: str,
    *,
    kb: Optional[Dict[str, Any]] = None,
    threshold: float = _SEMANTIC_THRESHOLD,
) -> Optional[SemanticHit]:
    """
    Embed ``user_input``, cosine-compare to each rule's ``embedding``, return best above threshold.
    """
    from knowledge.retriever import _pick_os_command, load_knowledge

    kb_obj = kb if kb is not None else load_knowledge()
    rules = kb_obj.get("rules") or []
    q = (user_input or "").strip()
    if not q:
        return None

    if not any(
        isinstance(r, dict) and isinstance(r.get("embedding"), list) and len(r["embedding"]) > 0
        for r in rules
    ):
        return None

    try:
        query_vec = get_embedding(q, task="query")
    except Exception:
        logger.exception("semantic_search: query embedding failed")
        return None

    if not query_vec:
        return None

    best_sim = -1.0
    best_rule: Optional[Dict[str, Any]] = None

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        emb = rule.get("embedding")
        if not isinstance(emb, list) or len(emb) == 0:
            continue
        sim = cosine_similarity(query_vec, emb)
        if sim > best_sim:
            best_sim = sim
            best_rule = rule

    if best_rule is None or best_sim <= threshold:
        return None

    cmd = _pick_os_command(best_rule)  # type: ignore[arg-type]
    if not cmd:
        return None

    return SemanticHit(command=cmd, similarity=best_sim, rule=best_rule)


def maybe_auto_rebuild_embeddings(path: Optional[str] = None) -> None:
    """
    Optionally rebuild embeddings once per process when ``CLP_AUTO_REBUILD_EMBEDDINGS=1``.
    """
    global _auto_rebuild_done
    if _auto_rebuild_done:
        return
    if os.getenv("CLP_AUTO_REBUILD_EMBEDDINGS", "").strip() != "1":
        return
    if not os.getenv("GEMINI_API_KEY", "").strip():
        logger.warning("CLP_AUTO_REBUILD_EMBEDDINGS set but GEMINI_API_KEY is missing; skip rebuild")
        _auto_rebuild_done = True
        return
    _auto_rebuild_done = True
    try:
        rebuild_embeddings(path=path)
    except Exception:
        logger.exception("auto rebuild_embeddings failed")
