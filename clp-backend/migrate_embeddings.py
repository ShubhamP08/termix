#!/usr/bin/env python3
"""
Migration script: Extract embeddings from KB and create separate embeddings.json

This script:
1. Reads knowledge_base.json
2. Extracts embeddings and creates id for each rule
3. Writes embeddings to data/embeddings.json
4. Removes embeddings from KB
5. Backs up original KB
"""

import json
import os
import sys
from datetime import datetime

def migrate_kb():
    """Migrate embeddings from KB to separate file."""
    
    kb_path = os.path.join(os.path.dirname(__file__), "knowledge", "knowledge_base.json")
    embeddings_path = os.path.join(os.path.dirname(__file__), "data", "embeddings.json")
    backup_path = os.path.join(os.path.dirname(__file__), "knowledge", f"knowledge_base.backup.{datetime.now().isoformat()}.json")
    
    print(f"Reading KB from {kb_path}...")
    with open(kb_path, "r", encoding="utf-8") as f:
        kb = json.load(f)
    
    # Backup original
    print(f"Creating backup at {backup_path}...")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=2)
    
    # Extract embeddings
    embeddings = {}
    rules = kb.get("rules", [])
    
    print(f"Processing {len(rules)} rules...")
    for idx, rule in enumerate(rules):
        # Create ID from index
        rule_id = f"rule_{idx:04d}"
        
        # Extract embedding if it exists
        if "embedding" in rule:
            embeddings[rule_id] = rule.pop("embedding")
        
        # Store ID in rule
        rule["id"] = rule_id
    
    # Save embeddings
    print(f"Saving embeddings to {embeddings_path}...")
    os.makedirs(os.path.dirname(embeddings_path), exist_ok=True)
    with open(embeddings_path, "w", encoding="utf-8") as f:
        json.dump(embeddings, f, indent=2)
    
    # Save cleaned KB
    print(f"Saving cleaned KB to {kb_path}...")
    with open(kb_path, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=2)
    
    print(f"\n✓ Migration complete!")
    print(f"  - Extracted {len(embeddings)} embeddings")
    print(f"  - Added IDs to {len(rules)} rules")
    print(f"  - KB file size reduction: embeddings removed")
    print(f"  - Backup saved: {backup_path}")

if __name__ == "__main__":
    try:
        migrate_kb()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
