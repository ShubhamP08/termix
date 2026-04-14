"""
File-operations parsing helpers.

This module contains ONLY deterministic parsing utilities used by the
tool layer (tools/tool_runner.py, filesystem/file_agent.py).
Generation and intent-detection logic has moved to the tool layer.

Kept here:
    extract_filename    - parse a filename from NL text
    build_filename      - build a clean filename with inferred extension
    infer_extension     - guess file extension from language cues
    _quote_for_shell    - safely quote a path for shell use

Removed (now in filesystem/file_agent.py or tools/):
    generate_file_commands   - deprecated; file_agent.tool_create_file() used instead
    is_create_file_intent    - deprecated; fs_create_file KB rule handles this
"""

from __future__ import annotations

import re
from typing import Optional


_QUOTED_NAME_RE = re.compile(r"""["']([^"']+)["']""")
_FILENAME_WITH_DOTS_RE = re.compile(r"""\b([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+)\b""")
_NAMED_RE = re.compile(r"""\b(?:named|called)\s+([A-Za-z0-9_.-]+)\b""", re.IGNORECASE)
_AFTER_FILE_RE = re.compile(
    r"""\b(?:create|make)\b.*?\bfile\b\s+([A-Za-z0-9_.-]+)\b""", re.IGNORECASE
)


def infer_extension(user_input: str) -> str:
    """
    Infer a file extension from the user's request.

    Mapping:
    - javascript → .js
    - python     → .py
    - text       → .txt
    - default    → ""
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

    Priority:
    1. Quoted strings: "test.js"
    2. Filename with extension: test.js
    3. "named X" / "called X"
    4. "create file X"
    """
    text = (user_input or "").strip()
    if not text:
        return ""

    quoted = _QUOTED_NAME_RE.findall(text)
    for q in quoted:
        q = q.strip()
        if q and not q.isspace():
            return q

    m = _FILENAME_WITH_DOTS_RE.search(text)
    if m:
        return m.group(1)

    m = _NAMED_RE.search(text)
    if m:
        return m.group(1)

    m = _AFTER_FILE_RE.search(text)
    if m:
        return m.group(1)

    return ""


def build_filename(user_input: str) -> str:
    """
    Build a deterministic filename from user input.

    Rules:
    - If filename already has an extension → keep it
    - Else append inferred extension
    - Default filename → "file"
    """
    raw = extract_filename(user_input).strip()
    if not raw:
        raw = "file"
    if "." in raw.strip("."):
        return raw
    ext = infer_extension(user_input)
    return f"{raw}{ext}" if ext else raw


def _quote_for_shell(path: str) -> str:
    """Quote a path for safe shell usage (double-quotes, escaped internals)."""
    escaped = path.replace('"', '\\"')
    return f'"{escaped}"'
