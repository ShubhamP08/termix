"""
Semantic search using embeddings (cosine similarity).

Provides embedding similarity scoring for KB entries.
Loads precomputed embeddings from data/embeddings.json
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Module-level cache for embeddings
_embeddings_cache: Optional[Dict[str, List[float]]] = None


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        vec1: First vector
        vec2: Second vector
        
    Returns:
        float: Similarity score between -1 and 1 (typically 0 to 1 for embeddings)
    """
    if len(vec1) != len(vec2):
        return 0.0
    
    if len(vec1) == 0:
        return 0.0
    
    # Dot product
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    
    # Magnitudes
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    
    return dot_product / (mag1 * mag2)


def load_embeddings() -> Dict[str, List[float]]:
    """
    Load embeddings from data/embeddings.json.
    
    Cached in memory after first load.
    """
    global _embeddings_cache
    
    if _embeddings_cache is not None:
        return _embeddings_cache
    
    # Lazy import to avoid circular dependencies
    from utils.kb import load_embeddings as kb_load_embeddings
    
    _embeddings_cache = kb_load_embeddings()
    return _embeddings_cache


def clear_embeddings_cache() -> None:
    """Clear the in-memory embeddings cache."""
    global _embeddings_cache
    _embeddings_cache = None


def semantic_search(
    user_input: str,
    kb_rules: List[dict],
    embeddings: Optional[Dict[str, List[float]]] = None,
    threshold: float = 0.75
) -> Tuple[Optional[dict], float]:
    """
    Find the best matching KB rule using semantic similarity.
    
    Args:
        user_input: User's natural language query
        kb_rules: List of KB rules with ids
        embeddings: Precomputed embeddings dict (loaded if not provided)
        threshold: Minimum similarity score (0-1)
        
    Returns:
        Tuple[Optional[dict], float]: (best_matching_rule, similarity_score)
    """
    # Load embeddings if not provided
    if embeddings is None:
        embeddings = load_embeddings()
    
    if not embeddings:
        logger.warning("No embeddings available for semantic search")
        return None, -1.0
    
    # Generate embedding for user input using TF method
    from services.embedding_api import _get_tf_embedding
    user_embedding = _get_tf_embedding(user_input)
    
    best_rule = None
    best_score = -1.0
    
    for rule in kb_rules:
        rule_id = rule.get("id")
        if not rule_id or rule_id not in embeddings:
            continue
        
        rule_embedding = embeddings[rule_id]
        score = cosine_similarity(user_embedding, rule_embedding)
        
        if score > best_score:
            best_score = score
            best_rule = rule
    
    if best_score >= threshold and best_rule:
        return best_rule, best_score
    
    return None, best_score
