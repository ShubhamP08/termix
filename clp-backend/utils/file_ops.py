"""
Deterministic file-operations utilities.

Purpose:
- Avoid relying on LLM output for filename parsing or file command generation.
- Keep behavior simple, predictable, and cross-platform.
"""

from __future__ import annotations

import re
from typing import List, Optional

from utils.os_detector import detect_os


_QUOTED_NAME_RE = re.compile(r"""["']([^"']+)["']""")

# Matches simple filenames that may include an extension (and preserves dots).
# Examples: test.js, hello.py, archive.tar.gz
_FILENAME_WITH_DOTS_RE = re.compile(r"\b([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+)\b")

# Matches a bare name (no extension) after common cues like "named" / "called".
_NAMED_RE = re.compile(r"\b(?:named|called)\s+([A-Za-z0-9_.-]+)\b", re.IGNORECASE)

# Matches a bare name after phrases like:
# - "create file X"
# - "create python file X"
# - "make a javascript file named X"
# Keep it permissive but deterministic (non-greedy until the word 'file').
_AFTER_FILE_RE = re.compile(r"\b(?:create|make)\b.*?\bfile\b\s+([A-Za-z0-9_.-]+)\b", re.IGNORECASE)


def infer_extension(user_input: str) -> str:
    """
    Infer a file extension from the user's request.

    Mapping:
    - javascript -> .js
    - python -> .py
    - text -> .txt
    - default -> ""
    """
    text = (user_input or "").lower()
    if "javascript" in text or re.search(r"\bjs\b", text):
        return ".js"
    if "python" in text or re.search(r"\bpy\b", text):
        return ".py"
    if "text" in text or re.search(r"\btxt\b", text):
        return ".txt"
    return ""


def extract_filename(user_input: str) -> str:
    """
    Extract a filename from a natural-language instruction.

    Key properties:
    - Preserves dots (critical for extensions).
    - Handles quoted names: "test.js"
    - Handles: "named test", "called test.js", "create file hello"
    """
    text = (user_input or "").strip()
    if not text:
        return ""

    # 1) Prefer quoted filenames.
    quoted = _QUOTED_NAME_RE.findall(text)
    for q in quoted:
        q = q.strip()
        if q and not q.isspace():
            return q

    # 2) Prefer explicit filenames that already contain a dot (test.js).
    m = _FILENAME_WITH_DOTS_RE.search(text)
    if m:
        return m.group(1)

    # 3) "named X" / "called X"
    m = _NAMED_RE.search(text)
    if m:
        return m.group(1)

    # 4) "create file X"
    m = _AFTER_FILE_RE.search(text)
    if m:
        return m.group(1)

    return ""


def build_filename(user_input: str) -> str:
    """
    Build a deterministic filename from user input.

    Rules:
    - If filename already has an extension -> keep it
    - Else append inferred extension
    - Default filename -> "file"
    """
    raw = extract_filename(user_input).strip()
    if not raw:
        raw = "file"

    # If it already has a dot in the tail, assume it has an extension.
    if "." in raw.strip("."):
        return raw

    ext = infer_extension(user_input)
    return f"{raw}{ext}" if ext else raw


def _quote_for_shell(path: str) -> str:
    """
    Quote a filename for safe shell usage.

    We keep it simple: use double-quotes and escape embedded quotes.
    This works for cmd.exe and POSIX shells for typical filenames.
    """
    escaped = path.replace('"', '\\"')
    return f'"{escaped}"'


def generate_file_commands(filename: str) -> List[str]:
    """
    Generate deterministic file-creation commands (no LLM).

    Returns:
    - touch <filename>
    - echo "" > <filename>

    Cross-platform notes:
    - On Windows (cmd.exe), `touch` is typically unavailable, so we use `type nul > file`.
    - On POSIX (Linux/macOS), `touch` is standard.
    """
    name = (filename or "").strip()
    if not name:
        name = "file"

    q = _quote_for_shell(name)
    os_key = detect_os()

    if os_key == "windows":
        # Create/overwrite file with empty content.
        return [
            f"type nul > {q}",
            f"echo.> {q}",
        ]

    return [
        f"touch {q}",
        f'echo "" > {q}',
    ]


def is_create_file_intent(user_input: str) -> bool:
    """
    Deterministic intent detection for create-file requests.

    This avoids asking the LLM to parse filenames.
    """
    text = (user_input or "").lower()
    return bool(re.search(r"\b(create|make)\b", text) and re.search(r"\bfile\b", text))

