"""
LangGraph node functions for CLP1.

Each node receives AgentState, mutates it, and returns it.

The retrieval pipeline (fuzzy → semantic → LLM) is now consolidated
inside ``knowledge.retriever.retrieve()``.  These nodes just wire
the pipeline output into the AgentState for the graph to process.
"""

from __future__ import annotations

import logging

from agent.state import AgentState
from utils.normalizer import normalize_text
from knowledge.retriever import retrieve
from security.validator import validate_commands, contains_unresolved_placeholders
from execution.executor import execute_commands
from knowledge.learner import save_command
from utils.history_logger import log_history

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------

def normalize_node(state: AgentState) -> AgentState:
    """Lowercase, strip punctuation, collapse whitespace."""
    user_input = state.get("user_input") or ""
    state["normalized_input"] = normalize_text(user_input)
    return state


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

def planner_node(state: AgentState) -> AgentState:
    """
    Simple pass-through: set normalized_input as a single task.
    
    No LLM dependency. The retrieval pipeline (KB fuzzy→semantic) will
    determine whether to call Gemini if KB has no match.
    """
    query = state.get("normalized_input") or ""
    # Simple deterministic pass-through: always set task to the normalized query
    state["tasks"] = [query]
    logger.debug("[planner] task: %s", query)
    return state


# ---------------------------------------------------------------------------
# Knowledge lookup (unified retrieval pipeline)
# ---------------------------------------------------------------------------

def knowledge_lookup_node(state: AgentState) -> AgentState:
    """
    Run the unified retrieval pipeline then dispatch to the tool layer.

    Flow:
        1. retrieve(user_input) → RetrievalResult (fuzzy → semantic → LLM)
        2. run_tool(rule_id, command_template, user_input, kb_rule) → ToolResult
           a. Extracts placeholder values from the raw query
           b. If slots are missing → sets missing_placeholders (caller prompts user)
           c. If Python-native handler → executes immediately (create/read/find)
           d. If shell command → renders template → sets rendered_commands

    SKIP_KB=true bypasses KB lookup (forces LLM mode).
    """
    import os as _os
    if _os.getenv("SKIP_KB", "").lower() == "true":
        logger.info("[knowledge] skipping KB lookup (SKIP_KB=true)")
        return state

    tasks = state.get("tasks") or []
    query = state.get("user_input") or (tasks[0] if tasks else "")

    # ── Step 1: Retrieval ──────────────────────────────────────────────────
    result = retrieve(query)

    # ── Step 2: Load KB rule for the matched rule_id ───────────────────────
    kb_rule = None
    command_template = result.commands[0] if result.commands else ""
    if result.rule_id:
        try:
            from knowledge.retriever import load_knowledge as _lk
            kb_data = _lk()
            kb_rule = next(
                (r for r in (kb_data.get("rules") or []) if r.get("id") == result.rule_id),
                None,
            )
            # Use the OS-specific template as the command template
            if kb_rule:
                from knowledge.retriever import _pick_os_command
                cmd = _pick_os_command(kb_rule)
                if cmd:
                    command_template = cmd
        except Exception as exc:
            logger.warning("[knowledge] could not load KB rule for id=%s: %s", result.rule_id, exc)

    # ── Step 3: Tool runner ────────────────────────────────────────────────
    requires_conf = result.requires_confirmation
    if kb_rule:
        kb_confirms = kb_rule.get("requires_confirmation", False)
        requires_conf = requires_conf or kb_confirms

    if result.source in ("intent", "kb_intent", "kb_fuzzy", "kb_semantic") and result.rule_id:
        from tools.tool_runner import run_tool
        tool_result = run_tool(
            rule_id=result.rule_id,
            command_template=command_template,
            user_input=query,
            kb_rule=kb_rule,
            requires_confirmation=requires_conf,
        )

        # Missing slots — ask user, do not proceed to execution
        if tool_result.missing_placeholders:
            state["missing_placeholders"] = tool_result.missing_placeholders
            state["tool_name"] = tool_result.tool_name
            state["source"] = result.source
            state["score"] = result.score
            state["rule_id"] = result.rule_id
            state["requires_confirmation"] = requires_conf
            logger.info(
                "[knowledge] missing slots %s for rule=%s — awaiting user input",
                tool_result.missing_placeholders, result.rule_id,
            )
            return state

        if not tool_result.safe_to_execute:
            state["error"] = tool_result.error or "Tool execution blocked as unsafe"
            state["tool_name"] = tool_result.tool_name
            state["source"] = result.source
            state["score"] = result.score
            state["rule_id"] = result.rule_id
            state["requires_confirmation"] = tool_result.requires_confirmation
            logger.warning(
                "[knowledge] blocked tool=%s rule=%s reason=%s",
                tool_result.tool_name,
                result.rule_id,
                tool_result.error,
            )
            return state

        # Tool executed (Python-native) or rendered shell command
        cmds = tool_result.rendered_commands if not tool_result.executed else []
        if validate_commands(cmds) or tool_result.executed:
            state["commands"] = cmds
            state["source"] = result.source
            state["score"] = result.score
            state["intent"] = result.intent  # type: ignore[assignment]
            state["requires_confirmation"] = tool_result.requires_confirmation
            state["tool_name"] = tool_result.tool_name
            state["missing_placeholders"] = []
            state["pending_tool"] = {}
            if result.rule_id:
                state["rule_id"] = result.rule_id
            if (
                not tool_result.executed
                and tool_result.requires_confirmation
                and result.rule_id in {"fs_remove_file", "fs_remove_folder"}
            ):
                state["pending_tool"] = {
                    "rule_id": result.rule_id,
                    "arguments": tool_result.arguments,
                }
            if tool_result.executed:
                # Python-native op already ran — store output, skip shell executor
                state["tool_output"] = tool_result.output
                state["execution_result"] = [{
                    "command": command_template,
                    "success": not bool(tool_result.error),
                    "output": tool_result.output,
                    "error": tool_result.error,
                }]
                state["validated"] = True
            logger.info(
                "[knowledge] tool=%s executed=%s rendered=%s",
                tool_result.tool_name, tool_result.executed, cmds,
            )
        else:
            state["error"] = tool_result.error or "Unsafe command detected"
            logger.warning("[knowledge] tool blocked: %s", tool_result.error)
        return state

    # ── LLM result or no-match: fall through with raw commands ────────────
    if result.commands and validate_commands(result.commands):
        state["commands"] = result.commands
        state["source"] = result.source
        state["score"] = result.score
        state["intent"] = result.intent  # type: ignore[assignment]
        state["requires_confirmation"] = result.requires_confirmation
        state["missing_placeholders"] = []
        if result.rule_id:
            state["rule_id"] = result.rule_id
        logger.info("[knowledge] LLM/direct resolved via %s (score=%.2f)", result.source, result.score)
    elif result.commands:
        state["error"] = "Unsafe command detected"
        logger.warning("[knowledge] blocked: %s", result.commands)
    else:
        logger.info("[knowledge] no commands generated")

    return state


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validator_node(state: AgentState) -> AgentState:
    """Safety-check all commands before execution."""
    # Check if Python-native tool already executed successfully
    execution_result = state.get("execution_result") or {}
    tool_output = state.get("tool_output") or ""
    
    if execution_result or tool_output:
        # If execution_result exists, check for at least one success
        if isinstance(execution_result, list):
            has_success = any(r.get("success") for r in execution_result)
            if has_success:
                state["validated"] = True
                logger.debug("[validator] Python-native execution succeeded, marking validated")
                return state
        elif isinstance(execution_result, dict) and execution_result.get("success"):
            state["validated"] = True
            logger.debug("[validator] Python-native execution succeeded, marking validated")
            return state
        
        # If tool_output exists and no error, treat as valid
        if tool_output and not state.get("error"):
            state["validated"] = True
            logger.debug("[validator] tool output exists, marking validated")
            return state
    
    # Check if we're waiting for user to provide missing placeholders — not an error
    missing = state.get("missing_placeholders") or []
    if missing:
        # Missing placeholders is a valid prompt-for-input state, not an error
        state["validated"] = False
        state["error"] = ""  # Do not set error for missing placeholders
        logger.debug("[validator] awaiting missing placeholders, no error set")
        return state
    
    # Standard command validation
    commands = state.get("commands") or []
    if not commands:
        state["validated"] = False
        state["error"] = state.get("error") or "No commands generated"
        return state

    if any(contains_unresolved_placeholders(cmd) for cmd in commands):
        state["validated"] = False
        state["error"] = "Unresolved placeholders detected in command template."
        logger.warning("[validator] blocked unresolved placeholders: %s", commands)
        return state

    safe = validate_commands(commands)
    state["validated"] = safe

    if not safe:
        state["error"] = "Unsafe command detected"
        logger.warning("[validator] blocked commands: %s", commands)
    else:
        logger.debug("[validator] commands passed")

    return state


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

def executor_node(state: AgentState) -> AgentState:
    """
    Execute validated, approved commands.

    The graph only reaches this node when:
      - state["validated"] is True
      - state["approved"] is True  (set by cli/main.py before re-invoking or
        by passing approved=True into the initial state for non-interactive use)
    """
    pending_tool = state.get("pending_tool") or {}
    if pending_tool:
        from tools.tool_runner import execute_confirmed_tool

        rule_id = pending_tool.get("rule_id", "")
        arguments = pending_tool.get("arguments", {})
        tool_result = execute_confirmed_tool(rule_id, arguments)
        state["execution_result"] = [{
            "command": (tool_result.rendered_commands[0] if tool_result.rendered_commands else rule_id),
            "success": not bool(tool_result.error),
            "output": tool_result.output,
            "error": tool_result.error,
        }]
        log_history(
            state.get("user_input") or state.get("normalized_input"),
            tool_result.rendered_commands or [rule_id],
            state.get("source"),
        )
        logger.info("[executor] deferred tool executed: %s", rule_id)
        return state

    commands = state.get("commands") or []
    if not commands:
        state["execution_result"] = []
        return state

    results = execute_commands(commands)
    state["execution_result"] = results

    log_history(
        state.get("user_input") or state.get("normalized_input"),
        commands,
        state.get("source"),
    )

    success_count = sum(1 for r in results if r.get("success"))
    logger.info("[executor] %d/%d commands succeeded", success_count, len(results))
    return state


# ---------------------------------------------------------------------------
# Learning
# ---------------------------------------------------------------------------

def learning_node(state: AgentState) -> AgentState:
    """
    Persist LLM-generated commands back into the KB so future queries
    resolve via fuzzy/semantic instead of calling Gemini again.
    """
    if state.get("source") not in {"llm", "gemini"}:
        return state

    commands = state.get("commands") or []
    results = state.get("execution_result") or []

    # Only learn from commands that actually succeeded
    succeeded = [
        cmd for cmd, res in zip(commands, results) if res.get("success")
    ]
    if not succeeded:
        logger.debug("[learning] no successful LLM commands to persist")
        return state

    query = state.get("normalized_input") or state.get("user_input") or ""
    save_command(query, succeeded)
    logger.info("[learning] saved %d command(s) for query: %s", len(succeeded), query)
    return state
