"""
Knowledge base utilities for managing embeddings.

Functions for rebuilding embeddings, loading/saving, and validation.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def get_kb_path() -> str:
    """Get the knowledge base file path."""
    return os.path.join(os.path.dirname(__file__), "..", "knowledge", "knowledge_base.json")


def get_embeddings_path() -> str:
    """Get the embeddings file path."""
    return os.path.join(os.path.dirname(__file__), "..", "data", "embeddings.json")


def load_kb() -> dict:
    """Load knowledge base from disk."""
    kb_path = get_kb_path()
    with open(kb_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_embeddings() -> Dict[str, List[float]]:
    """
    Load embeddings from disk.
    
    Returns empty dict if file doesn't exist.
    """
    embeddings_path = get_embeddings_path()
    
    if not os.path.exists(embeddings_path):
        logger.warning(f"Embeddings file not found: {embeddings_path}")
        return {}
    
    try:
        with open(embeddings_path, "r", encoding="utf-8") as f:
            embeddings = json.load(f)
        logger.info(f"Loaded {len(embeddings)} embeddings")
        return embeddings
    except Exception as e:
        logger.error(f"Failed to load embeddings: {e}")
        return {}


def save_embeddings(embeddings: Dict[str, List[float]]) -> None:
    """Save embeddings to disk."""
    embeddings_path = get_embeddings_path()
    os.makedirs(os.path.dirname(embeddings_path), exist_ok=True)
    
    with open(embeddings_path, "w", encoding="utf-8") as f:
        json.dump(embeddings, f, indent=2)
    
    logger.info(f"Saved {len(embeddings)} embeddings")


def rebuild_embeddings(use_gemini: bool = True) -> None:
    """
    Rebuild embeddings for all KB rules.
    
    Args:
        use_gemini: If True, use Gemini API; else use TF fallback
    """
    from services.embedding_api import get_embedding
    
    kb = load_kb()
    rules = kb.get("rules", [])
    
    embeddings = {}
    
    logger.info(f"Rebuilding {len(rules)} embeddings...")
    
    for rule in rules:
        rule_id = rule.get("id")
        if not rule_id:
            logger.warning(f"Rule missing ID: {rule}")
            continue
        
        # Combine texts for embedding
        texts = [
            rule.get("intent", ""),
            rule.get("description", ""),
        ]
        texts.extend(rule.get("examples", []))
        combined_text = " ".join(str(t) for t in texts if t)
        
        if not combined_text.strip():
            logger.warning(f"Rule {rule_id} has no text to embed")
            continue
        
        try:
            embedding = get_embedding(combined_text, use_gemini=use_gemini)
            embeddings[rule_id] = embedding
            logger.debug(f"Embedded {rule_id}: {len(embedding)} dimensions")
        except Exception as e:
            logger.error(f"Failed to embed {rule_id}: {e}")
    
    save_embeddings(embeddings)
    logger.info(f"✓ Rebuilt {len(embeddings)} embeddings")


def embeddings_status() -> dict:
    """
    Get status of embeddings.
    
    Returns:
        {
            "kb_count": number of KB rules,
            "embedding_count": number of embeddings,
            "missing_count": rules without embeddings,
            "last_rebuilt": timestamp or None,
            "is_valid": all rules have embeddings
        }
    """
    kb = load_kb()
    embeddings = load_embeddings()
    
    rules = kb.get("rules", [])
    kb_count = len(rules)
    embedding_count = len(embeddings)
    
    # Find missing
    missing_ids = set()
    for rule in rules:
        rule_id = rule.get("id")
        if rule_id and rule_id not in embeddings:
            missing_ids.add(rule_id)
    
    return {
        "kb_count": kb_count,
        "embedding_count": embedding_count,
        "missing_count": len(missing_ids),
        "missing_ids": list(missing_ids)[:5],  # First 5
        "is_valid": embedding_count == kb_count,
    }


def validate_embeddings() -> bool:
    """
    Check if embeddings are valid and up-to-date.
    
    Returns True if all KB rules have embeddings.
    """
    status = embeddings_status()
    is_valid = status["is_valid"]
    
    if not is_valid:
        logger.warning(
            f"Embeddings invalid: {status['embedding_count']}/{status['kb_count']} "
            f"({status['missing_count']} missing)"
        )
    
    return is_valid


def ensure_embeddings_exist() -> bool:
    """
    Check if embeddings exist and rebuild if necessary.
    
    Returns True if embeddings are valid after this call.
    """
    if validate_embeddings():
        return True
    
    logger.info("Embeddings missing or outdated, rebuilding...")
    try:
        rebuild_embeddings(use_gemini=False)  # Use TF to avoid API issues
        return validate_embeddings()
    except Exception as e:
        logger.error(f"Failed to rebuild embeddings: {e}")
        return False
