"""
Three-tier command resolver: fuzzy → semantic → LLM

Orchestrates the command resolution strategy with source tracking.
Central decision-making for command generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from knowledge.retriever import (
    KnowledgeBase,
    KBResolution,
    load_knowledge,
    canonical_kb_command,
    _map_os_for_kb,
)
from utils.fuzzy_match import match_query
from utils.normalizer import normalize_text
from services.semantic import semantic_search

logger = logging.getLogger(__name__)

# Thresholds
# Fuzzy: Strict threshold - requires >90% exact match
# Semantic: Very lenient for TF embeddings - catches anything with common words
FUZZY_THRESHOLD = 90.0  # Strict - only near-exact matches
SEMANTIC_THRESHOLD = 0.40  # Very lenient for TF - just needs common vocabulary


@dataclass
class ResolutionResult:
    """Result of command resolution with source tracking."""
    
    commands: List[str]
    source: str  # kb_fuzzy | kb_semantic | llm
    score: float  # confidence score
    rule_id: Optional[int] = None  # KB rule ID for traceability


def resolve_command(user_input: str) -> ResolutionResult:
    """
    Resolve a command through three-tier strategy:
    
    1. Fuzzy matching (RapidFuzz) on KB examples
       - Score > 85 → Return with source="kb_fuzzy"
    
    2. Semantic search (embeddings + cosine similarity)
       - Score > 0.75 → Return with source="kb_semantic"
    
    3. LLM fallback (Gemini)
       - Return with source="llm"
    
    Args:
        user_input: User's natural language query
        
    Returns:
        ResolutionResult: (commands, source, score, rule_id)
    """
    normalized_input = normalize_text(user_input)
    
    # Tier 1: Fuzzy matching
    logger.debug(f"[Resolver] Tier 1: Fuzzy matching for '{normalized_input}'")
    fuzzy_result = _tier_fuzzy(normalized_input)
    if fuzzy_result:
        logger.info(f"[Resolver] ✓ Tier 1 (fuzzy) matched with score {fuzzy_result.score:.2f}")
        return fuzzy_result
    
    # Tier 2: Semantic search
    logger.debug(f"[Resolver] Tier 2: Semantic search for '{normalized_input}'")
    semantic_result = _tier_semantic(normalized_input)
    if semantic_result:
        logger.info(f"[Resolver] ✓ Tier 2 (semantic) matched with score {semantic_result.score:.2f}")
        return semantic_result
    
    # Tier 3: LLM fallback
    logger.debug(f"[Resolver] Tier 3: LLM fallback for '{normalized_input}'")
    llm_result = _tier_llm(normalized_input)
    logger.info(f"[Resolver] ✓ Tier 3 (LLM) generated commands")
    return llm_result


def _tier_fuzzy(normalized_input: str) -> Optional[ResolutionResult]:
    """
    Tier 1: Fuzzy matching against KB examples.
    
    Returns fuzzy-matched rule if score > FUZZY_THRESHOLD.
    """
    try:
        kb = load_knowledge()
        rules = kb.get("rules", [])
        
        best_rule = None
        best_score = -1.0
        rule_idx = -1
        
        for idx, rule in enumerate(rules):
            # Build combined searchable text
            examples = rule.get("examples", [])
            intent = rule.get("intent", "")
            
            # Try matching against examples first, then intent
            for example in examples:
                # match_query returns (match_string, score) or (None, 0)
                _, score = match_query(normalized_input, [example])
                if score > best_score:
                    best_score = score
                    best_rule = rule
                    rule_idx = idx
            
            # Also try intent field
            if intent:
                _, score = match_query(normalized_input, [intent])
                if score > best_score:
                    best_score = score
                    best_rule = rule
                    rule_idx = idx
        
        if best_score >= FUZZY_THRESHOLD and best_rule:
            command = canonical_kb_command(best_rule)
            if command:
                return ResolutionResult(
                    commands=[command],
                    source="kb_fuzzy",
                    score=best_score / 100.0,  # Normalize to 0-1
                    rule_id=rule_idx
                )
    
    except Exception as e:
        logger.error(f"[Resolver] Fuzzy matching failed: {e}")
    
    return None


def _tier_semantic(normalized_input: str) -> Optional[ResolutionResult]:
    """
    Tier 2: Semantic search using embeddings.
    
    Returns semantically matching rule if score > SEMANTIC_THRESHOLD.
    """
    try:
        from services.semantic import semantic_search, load_embeddings
        
        kb = load_knowledge()
        rules = kb.get("rules", [])
        embeddings = load_embeddings()
        
        # Check if embeddings are available
        if not embeddings:
            logger.debug("[Resolver] No embeddings loaded, skipping semantic search")
            return None
        
        # Perform semantic search
        best_rule, best_score = semantic_search(
            normalized_input,
            rules,
            embeddings=embeddings,
            threshold=SEMANTIC_THRESHOLD
        )
        
        if best_rule and best_score >= SEMANTIC_THRESHOLD:
            command = canonical_kb_command(best_rule)
            if command:
                rule_id = rules.index(best_rule) if best_rule in rules else -1
                return ResolutionResult(
                    commands=[command],
                    source="kb_semantic",
                    score=best_score,
                    rule_id=rule_id
                )
    
    except Exception as e:
        logger.error(f"[Resolver] Semantic search failed: {e}")
    
    return None


def _tier_llm(user_input: str) -> ResolutionResult:
    """
    Tier 3: LLM fallback for novel/unknown requests.
    
    Delegates to Gemini for command generation.
    """
    from ai.command_generator import generate_commands
    from ai.llm_engine import LLMEngine
    
    try:
        engine = LLMEngine()
        commands = generate_commands(user_input, engine=engine)
        
        return ResolutionResult(
            commands=commands if commands else [],
            source="llm",
            score=1.0,  # LLM always returns score=1 (full confidence)
            rule_id=None
        )
    except Exception as e:
        logger.error(f"[Resolver] LLM generation failed: {e}")
        return ResolutionResult(commands=[], source="llm", score=0.0, rule_id=None)
