"""
History logger for AI Terminal Agent.

Stores executed commands in data/history.json
"""

import json
import os
from datetime import datetime


HISTORY_PATH = os.path.join("data", "history.json")


def log_history(query: str, commands: list[str], source: str):
    """
    Save command execution history.
    """

    # Ensure data folder exists
    os.makedirs("data", exist_ok=True)

    # Create file if it doesn't exist
    if not os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "w") as f:
            json.dump([], f)

    # Load existing history
    with open(HISTORY_PATH, "r") as f:
        history = json.load(f)

    entry = {
        "query": query,
        "commands": commands,
        "source": source,
        "timestamp": datetime.now().isoformat(),
    }

    history.append(entry)

    # Save updated history
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)