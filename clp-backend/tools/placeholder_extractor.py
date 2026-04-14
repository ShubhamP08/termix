"""
Deterministic placeholder extractor.

Extracts <slot> values from natural-language user queries using
ordered regex strategies — no LLM involved.

Supported placeholders (matching the KB schema):
    <filename>      - a file name (with or without extension)
    <folder>        - a directory name
    <source>        - source path for copy/move operations
    <destination>   - destination path for copy/move operations
    <app_name>      - application name (validated downstream by allowlist)
    <pattern>       - text pattern for grep/search operations
    <branch>        - git branch name
    <message>       - git commit message
    <pid>           - process ID (integer)
    <host>          - hostname or IP address
    <package>       - pip/npm package name
    <script>        - Python script filename

Resolution contract:
    - If a value is confidently extracted  → it appears in ExtractedArgs.values
    - If a value cannot be confidently extracted → it appears in ExtractedArgs.missing
    - Callers must check `missing` before rendering commands;
      do NOT substitute empty strings or invented values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set


# ── Compiled regex helpers ──────────────────────────────────────────────────

# Quoted string: "value" or 'value'
_QUOTED_RE = re.compile(r"""["']([^"']+)["']""")

# A path-like token: alphanumeric + dots, slashes, underscores, hyphens
_PATH_TOKEN_RE = re.compile(r"""[\w./\\-]+\.\w+|[\w./\\-]{2,}""")

# Filename: has an extension  (e.g. notes.txt, archive.tar.gz)
_FILENAME_EXT_RE = re.compile(r"""\b([\w.-]+\.[\w]+)\b""")

# Bare name after cue words
_NAMED_RE = re.compile(r"""\b(?:named?|called)\s+([\w.-]+)""", re.I)
_AFTER_FILE_RE = re.compile(r"""\b(?:create|make|touch|new)\b.*?\bfile\b\s+([\w.-]+)""", re.I)
_AFTER_FOLDER_RE = re.compile(
    r"""\b(?:create|make|mkdir|new|remove|delete|rmdir)\b.*?\b(?:folder|directory|dir)\b\s+([\w./\\-]+)""",
    re.I,
)

# Source / destination: "X to Y"
_SRC_DEST_RE = re.compile(r"""([\w./\\-]+)\s+to\s+([\w./\\-]+)""", re.I)

# App name: after open/launch/start
_APP_NAME_RE = re.compile(
    r"""\b(?:open|launch|start)\s+(?:the\s+app\s+)?([\w\s]+?)
    (?:\s+(?:here|in\s+this(?:\s+\w+)?|in\s+the\s+current\s+(?:directory|dir|folder)|in\s+the))?$""",
    re.I | re.X,
)

# Pattern after "for" / "text" / "string" (for grep)
_PATTERN_AFTER_FOR_RE = re.compile(r"""\bfor\s+["']?(\S+)["']?""", re.I)
_PATTERN_AFTER_TEXT_RE = re.compile(r"""\b(?:text|string|pattern|grep)\s+["']?(\S+)["']?""", re.I)

# Branch name: after "branch" / "checkout"
_BRANCH_RE = re.compile(r"""\b(?:branch|checkout)\s+([\w./-]+)""", re.I)

# Commit message: quoted or after "saying"/"message"
_MSG_SAYING_RE = re.compile(r"""\b(?:saying|with\s+message?)\s+["']?(.+?)["']?$""", re.I)

# PID: plain integer, possibly after "pid" / "process"
_PID_RE = re.compile(r"""\b(?:pid\s+|process\s+)?(\d+)\b""")

# Host: domain or IP-like token
_HOST_RE = re.compile(r"""\b((?:[\w-]+\.)+[\w-]{2,}|(?:\d{1,3}\.){3}\d{1,3})\b""")

# Package: after "install" / "add"
_PACKAGE_RE = re.compile(r"""\b(?:install|add)\s+(?:python\s+package\s+|package\s+)?["']?([\w.-]+)["']?""", re.I)

# Script: *.py file
_SCRIPT_RE = re.compile(r"""\b([\w.-]+\.py)\b""")


# ── Result dataclass ────────────────────────────────────────────────────────

@dataclass
class ExtractedArgs:
    """Result of placeholder extraction."""
    values: Dict[str, str] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)


# ── Individual extractors ───────────────────────────────────────────────────

def _extract_quoted(text: str) -> List[str]:
    return _QUOTED_RE.findall(text)


def _extract_filename(text: str) -> str:
    """Extract a filename from user text. Returns '' if not found."""
    # 1. Quoted string
    for q in _extract_quoted(text):
        q = q.strip()
        if q and not q.isspace():
            return q

    # 2. Filename with extension
    m = _FILENAME_EXT_RE.search(text)
    if m:
        return m.group(1)

    # 3. "named X" / "called X"
    m = _NAMED_RE.search(text)
    if m:
        return m.group(1)

    # 4. "create file X", "touch X"
    m = _AFTER_FILE_RE.search(text)
    if m:
        return m.group(1)

    return ""


def _extract_folder(text: str) -> str:
    """Extract a folder/directory name from user text."""
    # Quoted first
    for q in _extract_quoted(text):
        q = q.strip()
        if q:
            return q

    # "named X" / "called X"
    m = _NAMED_RE.search(text)
    if m:
        return m.group(1)

    # "create folder X" / "mkdir X"
    m = _AFTER_FOLDER_RE.search(text)
    if m:
        return m.group(1)

    return ""


def _extract_source_destination(text: str) -> tuple[str, str]:
    """
    Extract source and destination from phrases like:
      "copy report.pdf to backups/"
      "move old.py to archive/new.py"
    Returns (source, destination), either may be empty.
    """
    m = _SRC_DEST_RE.search(text)
    if m:
        return m.group(1), m.group(2)

    # Fallback: two quoted strings
    quoted = _extract_quoted(text)
    if len(quoted) >= 2:
        return quoted[0].strip(), quoted[1].strip()

    return "", ""


def _extract_app_name(text: str) -> str:
    """Extract app name after open/launch/start."""
    # Quoted
    for q in _extract_quoted(text):
        return q.strip()

    m = _APP_NAME_RE.search(text)
    if m:
        return m.group(1).strip().lower()

    return ""


def _extract_pattern(text: str) -> str:
    """Extract search pattern for grep-style queries."""
    # Quoted string preferred
    for q in _extract_quoted(text):
        return q.strip()

    m = _PATTERN_AFTER_FOR_RE.search(text)
    if m:
        return m.group(1)

    m = _PATTERN_AFTER_TEXT_RE.search(text)
    if m:
        return m.group(1)

    return ""


def _extract_branch(text: str) -> str:
    m = _BRANCH_RE.search(text)
    return m.group(1) if m else ""


def _extract_message(text: str) -> str:
    # Quoted string is the clearest signal
    for q in _extract_quoted(text):
        return q.strip()

    m = _MSG_SAYING_RE.search(text)
    return m.group(1).strip() if m else ""


def _extract_pid(text: str) -> str:
    m = _PID_RE.search(text)
    return m.group(1) if m else ""


def _extract_host(text: str) -> str:
    m = _HOST_RE.search(text)
    return m.group(1) if m else ""


def _extract_package(text: str) -> str:
    m = _PACKAGE_RE.search(text)
    return m.group(1) if m else ""


def _extract_script(text: str) -> str:
    m = _SCRIPT_RE.search(text)
    if m:
        return m.group(1)
    # Also try generic filename extractor
    return _extract_filename(text)


# ── Dispatch table ──────────────────────────────────────────────────────────

_EXTRACTORS = {
    "filename":    _extract_filename,
    "folder":      _extract_folder,
    "app_name":    _extract_app_name,
    "pattern":     _extract_pattern,
    "branch":      _extract_branch,
    "message":     _extract_message,
    "pid":         _extract_pid,
    "host":        _extract_host,
    "package":     _extract_package,
    "script":      _extract_script,
}


# ── Public API ──────────────────────────────────────────────────────────────

def detect_placeholders(command_template: str) -> List[str]:
    """
    Return a list of placeholder names found in a command template string.
    E.g. "touch <filename>" → ["filename"]
    """
    return re.findall(r"<(\w+)>", command_template)


def extract_placeholders(user_input: str, required: List[str]) -> ExtractedArgs:
    """
    Extract values for the given placeholder names from *user_input*.

    Parameters
    ----------
    user_input : str
        The raw user query.
    required : List[str]
        List of placeholder names to extract (e.g. ["filename"], ["source", "destination"]).

    Returns
    -------
    ExtractedArgs
        .values  — successfully extracted {name: value} pairs
        .missing — names for which no value could be confidently extracted
    """
    text = (user_input or "").strip()
    values: Dict[str, str] = {}
    missing: List[str] = []

    # Special case: source + destination need joint extraction
    if "source" in required or "destination" in required:
        src, dst = _extract_source_destination(text)
        if "source" in required:
            if src:
                values["source"] = src
            else:
                missing.append("source")
        if "destination" in required:
            if dst:
                values["destination"] = dst
            else:
                missing.append("destination")

    for name in required:
        if name in ("source", "destination"):
            continue  # already handled above
        extractor = _EXTRACTORS.get(name)
        if extractor is None:
            # Unknown placeholder — can't extract, mark missing
            missing.append(name)
            continue
        value = extractor(text)
        if value:
            values[name] = value
        else:
            missing.append(name)

    return ExtractedArgs(values=values, missing=missing)
