"""
Unified hybrid retrieval pipeline for NL-to-command resolution.

This is the **single canonical retrieval module**.  Every query flows through
the same 4-tier pipeline in strict order:

    1. Deterministic intent handlers  (file-create, etc.)   → source="intent"
    2. Fuzzy KB match                 (RapidFuzz ≥ 0.85)    → source="kb_fuzzy"
    3. Semantic similarity match      (cosine sim ≥ 0.60)   → source="kb_semantic"
    4. LLM fallback                   (Gemini generation)   → source="llm"

Each tier short-circuits: the first tier to produce a result wins.

Public API:
    retrieve(user_input)          → RetrievalResult
    load_knowledge(path)          → KnowledgeBase (cached)
    clear_knowledge_cache()       → None
    canonical_kb_command(rule)    → Optional[str]
    search_command(query)         → List[str]    (backward-compat convenience)

No vector database is used.  Embeddings are stored inline in the KB JSON.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, TypedDict

from utils.fuzzy_match import match_query
from utils.normalizer import normalize_text
from utils.os_detector import detect_os

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Thresholds — edit these to tune routing behaviour
# ═══════════════════════════════════════════════════════════════════════════

# Fuzzy: RapidFuzz score in 0-100 range.  85 means near-exact match
# on example strings.  Lower → more false positives.
FUZZY_THRESHOLD = 85.0

# Semantic: cosine similarity in 0-1 range.  0.60 is a good middle ground
# for TF vectors (sparse) and Gemini vectors (dense).  Tuned from review
# of actual KB content.  Lower → more semantic matches, higher → more LLM.
SEMANTIC_THRESHOLD = 0.60

# Commands matching these patterns require user confirmation before execution.
_DANGEROUS_PATTERNS = re.compile(
    r"\b(rm\s+-rf|rmdir|del\s|format|mkfs|dd\s|shutdown|reboot)\b",
    re.IGNORECASE,
)

_FILENAME_LIKE_RE = re.compile(r"\b[\w.-]+\.[A-Za-z0-9]{1,8}\b")
_QUOTED_TEXT_RE = re.compile(r"""["']([^"']+)["']""")
_INSTALL_TARGET_RE = re.compile(r"\b(?:pip|npm)\s+install\s+([a-z0-9_.@/-]+)\b", re.IGNORECASE)
_SIMPLE_INSTALL_RE = re.compile(r"\binstall\s+([a-z0-9_.@/-]+)\b", re.IGNORECASE)

_PYTHON_PACKAGES = {"pandas", "numpy", "fastapi", "requests", "flask", "django"}
_NODE_PACKAGES = {"react", "express", "axios", "vite", "next", "typescript"}


# ═══════════════════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════════════════

class KnowledgeRule(TypedDict, total=False):
    id: str
    text: str
    embedding: List[float]
    intent: str
    description: str
    examples: List[str]
    commands: Dict[str, str]
    command: str  # backward compat with older KB entries


class KnowledgeBase(TypedDict, total=False):
    version: str
    description: str
    rules: List[KnowledgeRule]


@dataclass
class RetrievalResult:
    """Structured output from the retrieval pipeline."""

    commands: List[str]                 # Shell commands to execute
    source: str                          # "intent" | "kb_fuzzy" | "kb_semantic" | "llm" | "none"
    score: float                         # 0.0–1.0 normalised confidence
    intent: str = "general"              # "file_op" | "general" | "unknown"
    requires_confirmation: bool = False  # True for destructive / LLM-sourced commands
    rule_id: Optional[str] = None        # KB rule ID for traceability


# ═══════════════════════════════════════════════════════════════════════════
# KB loading
# ═══════════════════════════════════════════════════════════════════════════

def _default_kb_path() -> str:
    return os.path.join(os.path.dirname(__file__), "knowledge_base.json")


def clear_knowledge_cache() -> None:
    """Invalidate cached KB after on-disk updates (e.g. embedding rebuild)."""
    load_knowledge.cache_clear()


@lru_cache(maxsize=1)
def load_knowledge(path: Optional[str] = None) -> KnowledgeBase:
    """
    Load the JSON knowledge base from disk.

    Cached in-memory to avoid per-call I/O.
    """
    kb_path = path or _default_kb_path()
    with open(kb_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("knowledge_base.json must contain a JSON object at the root.")
    if "rules" not in data or not isinstance(data["rules"], list):
        raise ValueError('knowledge_base.json must contain a "rules": [] list.')
    return data  # type: ignore[return-value]


# ═══════════════════════════════════════════════════════════════════════════
# OS-aware command helpers
# ═══════════════════════════════════════════════════════════════════════════

def _map_os_for_kb() -> str:
    """Map ``detect_os()`` output to KB command keys (linux / macos / windows)."""
    current = detect_os()
    if current == "mac":
        return "macos"
    if current == "windows":
        return "windows"
    return "linux"


def canonical_kb_command(rule: KnowledgeRule) -> Optional[str]:
    """
    Stable command string for KB storage.

    Prefers ``linux`` from the ``commands`` map, then any available key,
    then the legacy ``command`` field.
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

    Also supports legacy single ``command`` field.
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


# ═══════════════════════════════════════════════════════════════════════════
# Confirmation logic
# ═══════════════════════════════════════════════════════════════════════════

def _needs_confirmation(commands: List[str], source: str) -> bool:
    """
    Decide whether the user should confirm before execution.

    Rules:
    - LLM-sourced commands always require confirmation (not from KB).
    - Any command matching a destructive pattern requires confirmation.
    """
    if source == "llm":
        return True
    return any(_DANGEROUS_PATTERNS.search(cmd) for cmd in commands)


def _rule_by_id(kb: KnowledgeBase, rule_id: str) -> Optional[KnowledgeRule]:
    rules = kb.get("rules") or []
    for rule in rules:
        if isinstance(rule, dict) and rule.get("id") == rule_id:
            return rule  # type: ignore[return-value]
    return None


def _result_from_rule(rule: KnowledgeRule, *, source: str, score: float) -> Optional[RetrievalResult]:
    cmd = _pick_os_command(rule)
    if not cmd:
        return None
    commands = [cmd]
    return RetrievalResult(
        commands=commands,
        source=source,
        score=score,
        intent="file_op" if str(rule.get("id", "")).startswith("fs_") else "general",
        requires_confirmation=_needs_confirmation(commands, source),
        rule_id=rule.get("id"),
    )


def _tier_deterministic_intent(normalized_input: str) -> Optional[RetrievalResult]:
    """
    Route obvious structured filesystem intents directly to KB rule IDs.
    This prevents fuzzy false positives like mapping "create folder" to "pwd".
    """
    text = normalized_input.strip().lower()
    if not text:
        return None

    has_filename_like = bool(_FILENAME_LIKE_RE.search(text))

    create_words = {"create", "make", "new", "touch"}
    folder_create_words = {"create", "make", "new", "mkdir"}
    remove_words = {"delete", "remove", "rm"}
    remove_folder_words = {"delete", "remove", "rmdir"}
    copy_words = {"copy", "cp"}
    move_words = {"move", "mv", "rename"}
    read_words = {"read", "show", "cat", "view"}
    find_words = {"find", "locate"}
    search_words = {"grep", "search"}

    tokens = set(text.split())
    has_file_word = "file" in tokens
    has_folder_word = any(w in tokens for w in {"folder", "directory", "dir"})

    target_rule_id: Optional[str] = None

    # Order matters: folder/file remove/create are close semantically.
    if (tokens & folder_create_words) and has_folder_word:
        target_rule_id = "fs_create_folder"
    elif (tokens & create_words) and has_file_word:
        target_rule_id = "fs_create_file"
    elif (tokens & remove_folder_words) and has_folder_word:
        target_rule_id = "fs_remove_folder"
    elif (tokens & remove_words) and has_file_word:
        target_rule_id = "fs_remove_file"
    elif tokens & copy_words:
        target_rule_id = "fs_copy_file"
    elif tokens & move_words:
        target_rule_id = "fs_move_file"
    elif (
        (tokens & search_words)
        or ("find text" in text)
        or ("look for text" in text)
        or ("pattern" in tokens)
    ):
        target_rule_id = "fs_search_text_in_files"
    elif (
        (tokens & find_words and has_filename_like)
        or ("where is" in text and has_filename_like)
    ):
        target_rule_id = "fs_find_file_by_name"
    elif (tokens & read_words) and (has_file_word or has_filename_like):
        target_rule_id = "fs_show_file_contents"

    if not target_rule_id:
        return None

    kb = load_knowledge()
    rule = _rule_by_id(kb, target_rule_id)
    if not rule:
        return None
    return _result_from_rule(rule, source="intent", score=1.0)


def _extract_install_target(normalized_input: str) -> str:
    m = _INSTALL_TARGET_RE.search(normalized_input)
    if m:
        return m.group(1).strip()
    m = _SIMPLE_INSTALL_RE.search(normalized_input)
    if m:
        return m.group(1).strip()
    return ""


def _tier_deterministic_install_intent(normalized_input: str) -> Optional[RetrievalResult]:
    """
    Route developer package-install queries before fuzzy matching.
    If KB install rules are missing, synthesize a deterministic command.
    """
    text = normalized_input.strip().lower()
    if "install" not in text:
        return None

    target = _extract_install_target(text)
    if not target:
        return None

    tokens = set(text.split())
    ecosystem: Optional[str] = None
    if "pip" in tokens or "python" in tokens:
        ecosystem = "python"
    elif "npm" in tokens or "node" in tokens:
        ecosystem = "node"
    elif target in _PYTHON_PACKAGES:
        ecosystem = "python"
    elif target in _NODE_PACKAGES:
        ecosystem = "node"

    if ecosystem is None:
        return None

    kb = load_knowledge()
    if ecosystem == "python":
        rule = _rule_by_id(kb, "python_pip_install")
        if rule:
            result = _result_from_rule(rule, source="intent", score=1.0)
            if result:
                return result
        return RetrievalResult(
            commands=[f"pip install {target}"],
            source="intent",
            score=1.0,
            intent="general",
            requires_confirmation=False,
            rule_id=None,
        )

    rule = _rule_by_id(kb, "npm_install")
    if rule:
        # Keep a concrete command to avoid losing the package name when
        # the KB npm_install template is project-wide "npm install".
        cmd = (_pick_os_command(rule) or "npm install").strip()
        if re.fullmatch(r"npm\s+install", cmd, re.IGNORECASE):
            cmd = f"{cmd} {target}"
        return RetrievalResult(
            commands=[cmd],
            source="intent",
            score=1.0,
            intent="general",
            requires_confirmation=False,
            rule_id=None,
        )
    return RetrievalResult(
        commands=[f"npm install {target}"],
        source="intent",
        score=1.0,
        intent="general",
        requires_confirmation=False,
        rule_id=None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════════════

def retrieve(user_input: str) -> RetrievalResult:
    """
    Resolve a natural-language query into shell commands.

    Pipeline (short-circuits on first match):
        1. Fuzzy KB match       → source="kb_fuzzy"
        2. Semantic similarity  → source="kb_semantic"
        3. LLM fallback         → source="llm"

    File-create and other fs ops now go through the KB rule +
    tool runner placeholder extraction (fs_create_file, etc.).

    Returns a :class:`RetrievalResult` with commands, source, score,
    intent label, confirmation flag, and traceability rule ID.
    """
    raw = (user_input or "").strip()
    if not raw:
        return RetrievalResult(commands=[], source="none", score=0.0, intent="unknown")

    normalized = normalize_text(raw)

    # ── Tier 0: Deterministic routing for obvious filesystem intents ──────
    logger.debug("[retrieve] Tier 0 (deterministic intent) for '%s'", normalized)
    install_result = _tier_deterministic_install_intent(normalized)
    if install_result:
        logger.info("[retrieve] ✓ Tier 0 (deterministic install) command=%s", install_result.commands)
        return install_result

    intent_result = _tier_deterministic_intent(normalized)
    if intent_result:
        logger.info("[retrieve] ✓ Tier 0 (deterministic intent) rule=%s", intent_result.rule_id)
        return intent_result

    # Install queries without ecosystem hints should avoid fuzzy misrouting.
    # Return a structured "needs clarification" result instead of guessing.
    if "install" in normalized:
        target = _extract_install_target(normalized)
        if target:
            logger.info("[retrieve] install intent ambiguous for '%s' → needs ecosystem", raw)
            return RetrievalResult(
                commands=[],
                source="intent",
                score=1.0,
                intent="unknown",
                requires_confirmation=False,
                rule_id=None,
            )

    # Vague git commit requests are workflow-like and fuzzy matching tends to
    # misroute them to unrelated filesystem rules. Let the LLM handle them.
    if _should_force_llm(normalized, raw):
        logger.info("[retrieve] forcing LLM fallback for workflow-like query: %s", raw)
        return _tier_llm(raw)

    # ── Tier 1: Fuzzy KB match ───────────────────────────────────────
    logger.debug("[retrieve] Tier 1 (fuzzy) for '%s'", normalized)
    fuzzy_result = _tier_fuzzy(normalized)
    if fuzzy_result:
        logger.info("[retrieve] ✓ Tier 1 (fuzzy) score=%.2f", fuzzy_result.score)
        return fuzzy_result

    # ── Tier 2: Semantic similarity ────────────────────────────────────
    logger.debug("[retrieve] Tier 2 (semantic) for '%s'", normalized)
    semantic_result = _tier_semantic(raw)
    if semantic_result:
        logger.info("[retrieve] ✓ Tier 2 (semantic) score=%.2f", semantic_result.score)
        return semantic_result

    # ── Tier 3: LLM fallback ──────────────────────────────────────────
    logger.debug("[retrieve] Tier 3 (LLM) for '%s'", normalized)
    llm_result = _tier_llm(raw)
    logger.info("[retrieve] ✓ Tier 3 (LLM) generated %d command(s)", len(llm_result.commands))
    return llm_result


def _should_force_llm(normalized_input: str, raw_input: str) -> bool:
    """
    Detect high-level workflow queries that should skip KB fuzzy matching.

    Minimal targeted guard:
    - "commit the changes" and similar queries lack the commit message needed
      by the KB rule, and fuzzy matching often misroutes them to fs_* rules.
    """
    tokens = set(normalized_input.split())
    if "commit" not in tokens:
        return False

    has_commit_message = bool(_QUOTED_TEXT_RE.search(raw_input)) or "message" in tokens
    if has_commit_message:
        return False

    return "change" in tokens or "changes" in tokens



# ═══════════════════════════════════════════════════════════════════════════
# Tier implementations
# ═══════════════════════════════════════════════════════════════════════════


def _tier_fuzzy(normalized_input: str) -> Optional[RetrievalResult]:
    """
    Tier 2: Fuzzy matching against KB examples and intent strings.

    Uses RapidFuzz (WRatio scorer).  Threshold: FUZZY_THRESHOLD (85).
    Score is normalised to 0–1 for the output.
    """
    try:
        kb = load_knowledge()
        rules = kb.get("rules") or []

        best_rule: Optional[Dict[str, Any]] = None
        best_score = 0.0

        for rule in rules:
            if not isinstance(rule, dict):
                continue

            # Prefer high-signal fields (examples + intent). Description/text
            # are intentionally excluded to reduce broad fuzzy false positives.
            candidates: List[str] = []
            for ex in rule.get("examples") or []:
                if isinstance(ex, str) and ex.strip():
                    candidates.append(normalize_text(ex))
            for field_val in (rule.get("intent"),):
                if isinstance(field_val, str) and field_val.strip():
                    candidates.append(normalize_text(field_val))

            if not candidates:
                continue

            _match, score = match_query(normalized_input, candidates)
            if float(score) > best_score:
                best_score = float(score)
                best_rule = rule

        if best_rule is None or best_score < FUZZY_THRESHOLD:
            return None

        cmd = _pick_os_command(best_rule)  # type: ignore[arg-type]
        if not cmd:
            return None

        commands = [cmd]
        return RetrievalResult(
            commands=commands,
            source="kb_fuzzy",
            score=best_score / 100.0,  # Normalise RapidFuzz 0-100 → 0-1
            intent="general",
            requires_confirmation=_needs_confirmation(commands, "kb_fuzzy"),
            rule_id=best_rule.get("id"),
        )

    except Exception as exc:
        logger.error("[retrieve] Fuzzy matching failed: %s", exc)
        return None


def _tier_semantic(raw_input: str) -> Optional[RetrievalResult]:
    """
    Tier 3: Semantic search using embeddings + cosine similarity.

    Uses embeddings stored inline in KB rules.  Query is embedded
    at search time using the same model (Gemini or TF fallback).
    Threshold: SEMANTIC_THRESHOLD (0.60).
    """
    try:
        from knowledge.semantic import semantic_search

        kb = load_knowledge()
        hit = semantic_search(raw_input, kb=kb, threshold=SEMANTIC_THRESHOLD)

        if hit is None:
            return None

        commands = [hit.command]
        return RetrievalResult(
            commands=commands,
            source="kb_semantic",
            score=hit.similarity,
            intent="general",
            requires_confirmation=_needs_confirmation(commands, "kb_semantic"),
            rule_id=hit.rule.get("id"),
        )

    except Exception as exc:
        logger.error("[retrieve] Semantic search failed: %s", exc)
        return None


def _tier_llm(raw_input: str) -> RetrievalResult:
    """
    Tier 4: LLM fallback for novel / unknown requests.

    Delegates to Gemini for command generation.
    Always requires confirmation since the output is not from the curated KB.
    """
    from ai.command_generator import generate_commands
    from ai.llm_engine import LLMEngine

    try:
        engine = LLMEngine()
        commands = generate_commands(raw_input, engine=engine)
        commands = commands if commands else []

        return RetrievalResult(
            commands=commands,
            source="llm",
            score=0.5,  # LLM confidence is unknown — use neutral score
            intent="general",
            requires_confirmation=True,  # Always confirm LLM output
        )
    except Exception as exc:
        logger.error("[retrieve] LLM generation failed: %s", exc)
        return RetrievalResult(
            commands=[],
            source="llm",
            score=0.0,
            intent="unknown",
            requires_confirmation=False,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Backward-compatible convenience wrappers
# ═══════════════════════════════════════════════════════════════════════════

def search_command(
    query: str,
    *,
    kb: Optional[KnowledgeBase] = None,
) -> List[str]:
    """
    Find commands for a user query.

    Convenience wrapper that returns just the command list.
    """
    return list(retrieve(query).commands)
