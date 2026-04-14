"""
Tool registry: maps KB rule IDs to deterministic tool handlers.

Structure
---------
TOOL_REGISTRY : dict[rule_id, callable]
    Key   → KB rule ``id`` string (e.g. "fs_create_file")
    Value → callable(args: dict) → ToolResult

Fallthrough
-----------
Rules NOT in the registry (git_*, npm_*, python_*, sys_*) fall through
to the shell renderer in tool_runner.py — their OS-specific command
template is filled with extracted placeholder values and passed to the
shell executor.

Extending
---------
To add a new tool:
  1. Write the handler in the appropriate module.
  2. Add one line here:  TOOL_REGISTRY["rule_id"] = lambda args: my_handler(...)
"""

from __future__ import annotations

from typing import Callable, Dict

from tools.types import ToolResult
from filesystem.file_agent import (
    tool_create_file,
    tool_create_folder,
    tool_remove_file,
    tool_remove_folder,
    tool_copy_file,
    tool_move_file,
    tool_show_file_contents,
    tool_find_files_by_name,
    tool_search_text_in_files,
)
from tools.app_launcher import tool_open_app


# Handler callable type: receives extracted args dict, returns ToolResult
HandlerFn = Callable[[Dict[str, str]], ToolResult]


TOOL_REGISTRY: Dict[str, HandlerFn] = {
    # ── Filesystem ─────────────────────────────────────────────────────────
    "fs_create_file": lambda args: tool_create_file(args.get("filename", "")),
    "fs_create_folder": lambda args: tool_create_folder(args.get("folder", "")),
    "fs_remove_file": lambda args: tool_remove_file(args.get("filename", "")),
    "fs_remove_folder": lambda args: tool_remove_folder(args.get("folder", "")),
    "fs_copy_file": lambda args: tool_copy_file(args.get("source", ""), args.get("destination", "")),
    "fs_move_file": lambda args: tool_move_file(args.get("source", ""), args.get("destination", "")),
    "fs_show_file_contents": lambda args: tool_show_file_contents(args.get("filename", "")),
    "fs_find_file_by_name": lambda args: tool_find_files_by_name(args.get("filename", "")),
    "fs_search_text_in_files": lambda args: tool_search_text_in_files(args.get("pattern", "")),

    # ── App launching ───────────────────────────────────────────────────────
    "open_app": lambda args: tool_open_app(args.get("app_name", "")),
    "open_app_in_current_dir": lambda args: tool_open_app(args.get("app_name", ""), in_current_dir=True),

    # ── Native OS app shortcuts (no placeholder) ───────────────────────────
    # These use the shell renderer (no handler needed) — they have no
    # placeholders in their command templates.  Listed here as None to make
    # the registry explicit about what is handled vs. what falls through.
    "app_open_terminal": None,        # type: ignore[assignment]
    "app_open_file_manager": None,    # type: ignore[assignment]
    "app_open_calculator": None,      # type: ignore[assignment]
    "fs_list_files": None,            # type: ignore[assignment]
    "fs_current_directory": None,     # type: ignore[assignment]
}
