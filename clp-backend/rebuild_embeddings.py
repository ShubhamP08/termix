#!/usr/bin/env python3
"""
Script to rebuild embeddings in the knowledge base.

Run this once to generate embeddings for all KB rules,
then the retriever can use semantic search.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from knowledge.semantic import rebuild_embeddings

if __name__ == "__main__":
    kb_path = os.path.join(os.path.dirname(__file__), "knowledge", "knowledge_base.json")
    print(f"Rebuilding embeddings in {kb_path}...")
    rebuild_embeddings(path=kb_path)
    print("✓ Embeddings rebuilt successfully!")
