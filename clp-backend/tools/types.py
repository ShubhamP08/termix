"""
Canonical ToolResult dataclass — shared across all tool modules.

Import from here in file_agent, app_launcher, tool_registry, and tool_runner
to avoid duplicating the contract definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ToolResult:
    """
    Execution contract returned by every tool handler.

    Fields
    ------
    tool_name : str
        Canonical name of the tool that was invoked (e.g. "create_file").
    arguments : dict
        Placeholder values that were successfully extracted and used.
    missing_placeholders : list[str]
        Placeholder names the tool still needs.  If non-empty the caller
        MUST prompt the user for these values — do NOT execute.
    requires_confirmation : bool
        True when a human confirmation step is required before execution
        (e.g. destructive ops, app launches).
    safe_to_execute : bool
        False if the tool determined the operation is not safe or not
        permitted (e.g. app not in allowlist, file not found for delete).
    rendered_commands : list[str]
        Shell equivalent command(s) for display / fallback execution.
    output : str
        Stdout-style result from a Python-native execution (e.g. file
        contents, search hits). Empty for shell-delegated tools.
    error : str
        Error message if the tool failed or was blocked.
    executed : bool
        True if a Python-native op was already completed inside the tool.
        False for shell-rendered commands that still need subprocess.
    """

    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    missing_placeholders: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    safe_to_execute: bool = True
    rendered_commands: List[str] = field(default_factory=list)
    output: str = ""
    error: str = ""
    executed: bool = False
