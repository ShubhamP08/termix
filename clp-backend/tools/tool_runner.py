"""
Tool runner — the single entry point for tool-driven execution.

Usage
-----
    from tools.tool_runner import run_tool
    result = run_tool(retrieval_result, user_input, kb_rule)

Flow
----
    1. Detect which placeholders the matched KB rule requires.
    2. Extract values from user_input via placeholder_extractor.
    3. If any required values are missing → return ToolResult with
       missing_placeholders (caller prompts user, no execution).
    4. Look up handler in TOOL_REGISTRY by rule_id.
       a. Python handler exists → call it, return ToolResult (may be
          already executed for safe ops, or pending confirmation for
          destructive ops).
       b. No handler (None in registry) or rule not in registry →
          use shell_renderer to fill the OS command template and return
          ToolResult with rendered_commands for the shell executor.
    5. Respect requires_confirmation: if True the caller (nodes.py /
       server.py) must gate execution behind a user confirmation step.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from tools.types import ToolResult
from tools.placeholder_extractor import detect_placeholders, extract_placeholders
from tools.tool_registry import TOOL_REGISTRY
from tools.shell_renderer import render_command

logger = logging.getLogger(__name__)


def run_tool(
    rule_id: Optional[str],
    command_template: str,
    user_input: str,
    kb_rule: Optional[Dict[str, Any]] = None,
    requires_confirmation: bool = False,
) -> ToolResult:
    """
    Resolve and (if safe) execute the tool for the matched KB rule.

    Parameters
    ----------
    rule_id : str or None
        KB rule ``id``, e.g. ``"fs_create_file"``.  None → shell fallback.
    command_template : str
        The OS-specific command string (may contain ``<placeholders>``).
    user_input : str
        Raw user query — used for placeholder extraction.
    kb_rule : dict or None
        Full KB rule dict (needed for shell renderer).
    requires_confirmation : bool
        Propagated from the KB rule's ``requires_confirmation`` field.

    Returns
    -------
    ToolResult
        See tools/types.py for the full contract.
    """
    # ── Step 1: detect required placeholders from the command template ────
    required = detect_placeholders(command_template)
    logger.debug("[tool_runner] rule=%s required_slots=%s", rule_id, required)

    # ── Step 2: extract values from user query ────────────────────────────
    if required:
        extracted = extract_placeholders(user_input, required)
        args = extracted.values
        missing = extracted.missing
    else:
        args = {}
        missing = []

    # ── Step 3: missing placeholders → ask user, do NOT execute ──────────
    if missing:
        logger.info("[tool_runner] missing slots %s for rule=%s", missing, rule_id)
        rendered = _render_template_partial(command_template, args, kb_rule)
        return ToolResult(
            tool_name=rule_id or "unknown",
            arguments=args,
            missing_placeholders=missing,
            requires_confirmation=requires_confirmation,
            safe_to_execute=False,
            rendered_commands=[rendered] if rendered else [],
        )

    # ── Step 4a: Python-native handler ────────────────────────────────────
    handler = TOOL_REGISTRY.get(rule_id) if rule_id else None
    if handler is not None:
        logger.info("[tool_runner] dispatching to Python handler for rule=%s", rule_id)
        result = handler(args)
        # Merge confirmation flag (KB may mark something requires_confirmation
        # even if the handler doesn't set it — take the more restrictive value)
        if requires_confirmation and not result.requires_confirmation:
            result.requires_confirmation = True
        return result

    # ── Step 4b: Shell renderer fallthrough ───────────────────────────────
    logger.info("[tool_runner] shell render fallthrough for rule=%s", rule_id)
    rendered = render_command(kb_rule, args) if kb_rule else None

    if rendered:
        return ToolResult(
            tool_name=rule_id or "shell",
            arguments=args,
            requires_confirmation=requires_confirmation,
            safe_to_execute=True,
            rendered_commands=[rendered],
        )

    # Render failed — unfilled placeholders somehow remain
    return ToolResult(
        tool_name=rule_id or "shell",
        arguments=args,
        requires_confirmation=requires_confirmation,
        safe_to_execute=False,
        rendered_commands=[command_template],
        error="Could not render command — placeholders may remain unfilled.",
    )


def _render_template_partial(
    template: str,
    args: Dict[str, str],
    kb_rule: Optional[Dict[str, Any]],
) -> str:
    """
    Partially fill the template for display purposes (missing slots shown as <name>).
    """
    result = template
    for name, value in args.items():
        result = result.replace(f"<{name}>", value)
    return result


# ── Confirmation execution helpers ────────────────────────────────────────────

def execute_confirmed_tool(rule_id: str, args: Dict[str, str]) -> ToolResult:
    """
    Execute a destructive op AFTER the user has confirmed.

    Called by nodes.py / server.py when requires_confirmation=True and
    approved=True.  Only the tools that defer execution (remove_file,
    remove_folder) need a separate execute step.  All other tools
    already ran inside run_tool().
    """
    from filesystem.file_agent import execute_remove_file, execute_remove_folder

    DEFERRED = {
        "fs_remove_file": lambda a: execute_remove_file(a.get("filename", "")),
        "fs_remove_folder": lambda a: execute_remove_folder(a.get("folder", "")),
    }

    executor = DEFERRED.get(rule_id)
    if executor:
        logger.info("[tool_runner] executing confirmed deferred op: %s", rule_id)
        return executor(args)

    # For non-deferred tools (app launchers, shell commands): return
    # empty result — the caller handles shell execution via execute_commands()
    return ToolResult(
        tool_name=rule_id,
        arguments=args,
        safe_to_execute=True,
        executed=False,
    )
