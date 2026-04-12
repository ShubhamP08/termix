"""
Filesystem helper agent stub.

Intended to assist with safe file operations (list/read/write/move) via validated commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Tuple

from agent.state import AgentState


def handle_file_op(state: AgentState) -> AgentState:
    # Placeholder integration point for LangGraph.
    # The graph can route file_op intents here once an operation schema is defined.
    raise NotImplementedError


def create_folders(paths: Iterable[str | Path]) -> None:
    """
    Create one or more folders (parents included). No-op if they already exist.
    """
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)

def create_file(path: str | Path, *, exist_ok: bool = False) -> Path:
    """
    Create an empty file.

    - Creates parent directories if needed
    - If exist_ok is False and file exists, raises FileExistsError
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and not exist_ok:
        raise FileExistsError(str(p))
    p.touch(exist_ok=True)
    return p

def write_file(
    path: str | Path,
    content: str,
    *,
    overwrite: bool = True,
    encoding: str = "utf-8",
) -> Path:
    """
    Write full file contents.

    - Creates parent directories if needed
    - If overwrite is False and file exists, raises FileExistsError
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and not overwrite:
        raise FileExistsError(str(p))
    p.write_text(content, encoding=encoding)
    return p

def edit_file(
    path: str | Path,
    *,
    find: str,
    replace: str,
    count: int = 1,
    encoding: str = "utf-8",
) -> Tuple[Path, int]:
    """
    Edit a file by replacing occurrences of `find` with `replace`.

    Returns (path, replacements_made).
    """
    p = Path(path)
    text = p.read_text(encoding=encoding)
    if not find:
        raise ValueError("`find` must be non-empty.")

    new_text = text.replace(find, replace, count)
    replacements_made = 0 if new_text == text else text.count(find) if count < 0 else min(text.count(find), count)
    p.write_text(new_text, encoding=encoding)
    return p, replacements_made

# def remove_file(path: str | Path) -> None:
#     """
#     Remove a file if it exists. No-op if it doesn't exist.
#     """
#     p = Path(path)

