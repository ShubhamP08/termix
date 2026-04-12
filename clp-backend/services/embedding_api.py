"""
Embedding API integration - Gemini with TF fallback.

Provides embeddings using Gemini API with graceful fallback to TF.
Manages embedding lifecycle and caching.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import List

logger = logging.getLogger(__name__)


def get_embedding(text: str, use_gemini: bool = True) -> List[float]:
    """
    Generate embedding for text using Gemini API (with TF fallback).
    
    Args:
        text: Text to embed
        use_gemini: If True, try Gemini API first; then fall back to TF
        
    Returns:
        List[float]: Embedding vector
    """
    if use_gemini:
        try:
            return _get_gemini_embedding(text)
        except Exception as e:
            logger.warning(f"Gemini embedding failed, falling back to TF: {e}")
            return _get_tf_embedding(text)
    else:
        return _get_tf_embedding(text)


def _get_gemini_embedding(text: str) -> List[float]:
    """
    Generate embedding using Gemini embeddings API.
    
    Uses text-embedding-004 model for semantic understanding.
    """
    try:
        import google.generativeai as genai
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        
        genai.configure(api_key=api_key)
        
        # Use embeddings API
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="semantic_similarity"
        )
        
        embedding = result.get("embedding", [])
        if not embedding:
            raise ValueError("Empty embedding returned")
        
        logger.debug(f"Generated Gemini embedding: {len(embedding)} dimensions")
        return embedding
    
    except ImportError:
        raise RuntimeError("google.generativeai not installed")
    except Exception as e:
        raise RuntimeError(f"Gemini embedding failed: {e}")


def _get_tf_embedding(text: str) -> List[float]:
    """
    Fallback: TF-based embedding for when Gemini is unavailable.
    
    Simple term-frequency vector for semantic search.
    """
    text = text.lower().strip()
    words = text.split()
    
    vocab = _get_vocab()
    embedding = [0.0] * len(vocab)
    
    word_count = len(words)
    if word_count == 0:
        return embedding
    
    for word in words:
        clean_word = ''.join(c for c in word if c.isalnum() or c == '_')
        if clean_word in vocab:
            idx = vocab[clean_word]
            embedding[idx] += 1.0 / word_count
    
    logger.debug(f"Generated TF embedding: {len(embedding)} dimensions")
    return embedding


@lru_cache(maxsize=1)
def _get_vocab() -> dict:
    """
    Build vocabulary from KB for TF embeddings.
    Cached to avoid rebuilding.
    """
    vocab = {}
    kb_path = os.path.join(os.path.dirname(__file__), "..", "knowledge", "knowledge_base.json")
    
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            kb = json.load(f)
        
        rules = kb.get("rules", [])
        word_set = set()
        
        for rule in rules:
            texts = [
                rule.get("intent", ""),
                rule.get("description", ""),
            ]
            texts.extend(rule.get("examples", []))
            
            for text in texts:
                if text:
                    words = text.lower().split()
                    for word in words:
                        clean = ''.join(c for c in word if c.isalnum() or c == '_')
                        if clean:
                            word_set.add(clean)
        
        for idx, word in enumerate(sorted(word_set)):
            vocab[word] = idx
        
        logger.info(f"Built vocabulary with {len(vocab)} unique words")
    except Exception as e:
        logger.error(f"Failed to build vocabulary: {e}")
    
    return vocab


def clear_embedding_cache() -> None:
    """Clear cached vocabulary."""
    _get_vocab.cache_clear()
