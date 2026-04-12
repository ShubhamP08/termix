"""
Knowledge retrieval orchestration stubs.

Intended to provide:
- JSON KB exact-match lookup
- Vector semantic search
- LLM fallback generation
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, TypedDict

from agent.state import AgentState
from utils.fuzzy_match import match_query
from utils.normalizer import normalize_text
from utils.os_detector import detect_os

logger = logging.getLogger(__name__)

FUZZY_SCORE_THRESHOLD = 85.0


class KnowledgeRule(TypedDict, total=False):
    id: str
    text: str
    embedding: List[float]
    intent: str
    description: str
    examples: List[str]
    commands: Dict[str, str]
    command: str  # backward compatibility with older KB entries


class KnowledgeBase(TypedDict, total=False):
    version: str
    description: str
    rules: List[KnowledgeRule]


@dataclass(frozen=True)
class KBResolution:
    """Result of local KB resolution (fuzzy or semantic)."""

    commands: List[str]
    layer: str  # fuzzy | semantic | ""
    score: float


def _default_kb_path() -> str:
    return os.path.join(os.path.dirname(__file__), "knowledge_base.json")


def clear_knowledge_cache() -> None:
    """Invalidate cached KB after on-disk updates (e.g. embedding rebuild)."""
    load_knowledge.cache_clear()


@lru_cache(maxsize=1)
def load_knowledge(path: Optional[str] = None) -> KnowledgeBase:
    """
    Load the JSON knowledge base from disk.

    Cached to avoid per-call I/O.
    """
    kb_path = path or _default_kb_path()
    with open(kb_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("knowledge_base.json must contain a JSON object at the root.")
    if "rules" not in data or not isinstance(data["rules"], list):
        raise ValueError('knowledge_base.json must contain a "rules": [] list.')
    return data  # type: ignore[return-value]


def _map_os_for_kb() -> str:
    """
    Map detect_os() output to KB command keys.
    - linux -> linux
    - mac -> macos
    - windows -> windows
    """
    current = detect_os()
    if current == "mac":
        return "macos"
    if current == "windows":
        return "windows"
    return "linux"


def canonical_kb_command(rule: KnowledgeRule) -> Optional[str]:
    """
    Stable command string for KB storage (prefer linux from ``commands``, else legacy ``command``).
    """
    commands_map = rule.get("commands")
    if isinstance(commands_map, dict):
        chosen = commands_map.get("linux")
        if isinstance(chosen, str) and chosen.strip():
            return chosen.strip()
        for _k, v in commands_map.items():
            if isinstance(v, str) and v.strip():
                return v.strip()

    legacy = rule.get("command")
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip()
    return None


def _pick_os_command(rule: KnowledgeRule) -> Optional[str]:
    """
    Resolve command from OS-specific map with fallback to linux.
    Also supports legacy single `command` field.
    """
    commands_map = rule.get("commands")
    if isinstance(commands_map, dict):
        os_key = _map_os_for_kb()
        chosen = commands_map.get(os_key) or commands_map.get("linux")
        if isinstance(chosen, str) and chosen.strip():
            return chosen.strip()

    # Backward compatibility with older KB schema entries.
    legacy = rule.get("command")
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip()
    return None


def _extract_filename_from_query(query: str) -> str | None:
    """Parse an explicit “create file” filename from user text."""
    if not query or not query.strip():
        return None

    # Preserve punctuation from query for extensions (e.g. .txt), but lowercase matching keywords.
    original = query.strip()
    lowered = original.lower()

    # Example: "create file name a with extension txt" -> "a.txt"
    m = re.search(
        r"(?:create|make)\s+file(?:\s+(?:name|named|called))?\s+(.+?)\s+with\s+extension\s+([a-z0-9_]+)\s*$",
        lowered,
    )
    if m:
        basename = m.group(1).strip().strip("\"' ")
        extension = m.group(2).strip().lstrip('.')
        if not basename:
            return None
        if '.' in basename:
            return basename
        return f"{basename}.{extension}"

    m2 = re.search(r"(?:create|make)\s+file(?:\s+(?:name|named|called))?\s+(.+)$", original, re.I)
    if m2:
        filename = m2.group(1).strip().strip("\"' ")
        if filename:
            return filename

    return None


def _fuzzy_resolve(query: str, kb_obj: KnowledgeBase) -> KBResolution:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return KBResolution([], "", 0.0)

    rules = kb_obj.get("rules") or []
    best_score = 0.0
    best_rule: Optional[Dict[str, Any]] = None

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        candidates: List[str] = []
        for ex in rule.get("examples") or []:
            if isinstance(ex, str) and ex.strip():
                candidates.append(normalize_text(ex))
        for field in (rule.get("intent"), rule.get("description")):
            if isinstance(field, str) and field.strip():
                candidates.append(normalize_text(field))
        text_field = rule.get("text")
        if isinstance(text_field, str) and text_field.strip():
            candidates.append(normalize_text(text_field))
        if not candidates:
            continue
        _match, score = match_query(normalized_query, candidates)
        if float(score) > best_score:
            best_score = float(score)
            best_rule = rule

    if best_rule is None or best_score <= FUZZY_SCORE_THRESHOLD:
        return KBResolution([], "", 0.0)

    cmd = _pick_os_command(best_rule)  # type: ignore[arg-type]
    if not cmd:
        return KBResolution([], "", 0.0)

    return KBResolution([cmd], "fuzzy", best_score)


def resolve_command(
    query: str,
    *,
    kb: Optional[KnowledgeBase] = None,
) -> KBResolution:
    """
    Resolve a command from the KB using RapidFuzz (``score > 85``), then semantic similarity (``> 0.75``).
    """
    kb_obj = kb or load_knowledge()

    filename = _extract_filename_from_query(query)
    if filename:
        os_key = _map_os_for_kb()
        if os_key == "windows":
            return KBResolution([f"type nul > {filename}"], "fuzzy", 100.0)
        return KBResolution([f"touch {filename}"], "fuzzy", 100.0)

    normalized_query = normalize_text(query)
    if not normalized_query or not (kb_obj.get("rules") or []):
        return KBResolution([], "", 0.0)

    fuzzy_res = _fuzzy_resolve(query, kb_obj)
    if fuzzy_res.commands:
        logger.info("kb_resolve layer=%s score=%.4f", fuzzy_res.layer, fuzzy_res.score)
        return fuzzy_res

    from knowledge.semantic import semantic_search

    hit = semantic_search(query, kb=kb_obj)
    if hit is not None:
        logger.info("kb_resolve layer=semantic score=%.4f", hit.similarity)
        return KBResolution([hit.command], "semantic", hit.similarity)

    logger.info("kb_resolve layer=none score=0.0000 (will use LLM if configured)")
    return KBResolution([], "", 0.0)


def retrieve_from_kb(state: AgentState, *, kb: Dict[str, Any]) -> AgentState:
    query = state.get("normalized_query") or state.get("user_query") or ""
    res = resolve_command(query, kb=kb)  # type: ignore[arg-type]
    state["kb_candidates"] = [
        {
            "source": "json_kb",
            "command": cmd,
            "score": float(res.score),
        }
        for cmd in res.commands
    ]
    return state


def retrieve_from_vector(state: AgentState, *, vector_store: Any) -> AgentState:
    # Placeholder integration point; can be replaced with real embeddings later.
    query = state.get("normalized_query") or state.get("user_query") or ""
    results = vector_store.search(query) if vector_store is not None else []
    state["vector_candidates"] = results
    return state


def retrieve_from_llm(state: AgentState, *, llm: Any) -> AgentState:
    # Placeholder; intentionally does not call any LLM yet.
    state["llm_candidates"] = []
    return state


def search_command(
    query: str,
    *,
    kb: Optional[KnowledgeBase] = None,
) -> List[str]:
    """
    Find commands for a user query using RapidFuzz (threshold 85), then semantic embeddings.

    Supports dynamic create-file names (e.g. "create file name a.txt").
    On match, returns OS-specific command from ``commands`` or legacy ``command``.
    """
    return list(resolve_command(query, kb=kb).commands)