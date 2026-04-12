"""
LangGraph node functions for CLP1.

Each node receives AgentState, mutates it, and returns it.
Execution and learning are now wired into the graph — cli/main.py
only handles display and user confirmation.
"""

from __future__ import annotations

import logging

from agent.state import AgentState
from utils.normalizer import normalize_text
from agent.resolver import resolve_command
from security.validator import validate_commands
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
    Break the request into tasks — but skip LLM for short, simple queries.

    Single-word or very short queries (≤ 4 words) go straight through as one
    task so we don't burn a Gemini call on "list files" or "show processes".
    """
    query = state.get("normalized_input") or ""
    words = query.split()

    if len(words) <= 4:
        # Fast path: no LLM needed for simple queries
        state["tasks"] = [query]
        logger.debug("[planner] fast-path: %s", query)
        return state

    from ai.llm_engine import LLMEngine
    from ai.planner import plan_tasks

    engine = LLMEngine()
    tasks = plan_tasks(query, engine=engine)
    state["tasks"] = tasks if tasks else [query]
    logger.debug("[planner] tasks: %s", state["tasks"])
    return state


# ---------------------------------------------------------------------------
# Knowledge lookup
# ---------------------------------------------------------------------------

def knowledge_lookup_node(state: AgentState) -> AgentState:
    """
    3-tier resolver: fuzzy → semantic → (falls through to LLM node).

    Now uses the first task from planner output rather than ignoring it.
    
    NOTE: Set SKIP_KB=true environment variable to force LLM usage.
    """
    import os
    
    # Allow skipping KB for testing/LLM-only mode
    if os.getenv("SKIP_KB", "").lower() == "true":
        logger.info("[knowledge] skipping KB lookup (SKIP_KB=true)")
        return state
    
    tasks = state.get("tasks") or []
    query = tasks[0] if tasks else (state.get("normalized_input") or "")

    result = resolve_command(query)

    if result.commands and validate_commands(result.commands):
        state["commands"] = result.commands
        state["source"] = result.source
        logger.info(
            "[knowledge] resolved via %s (score=%.2f)", result.source, result.score
        )
    elif result.commands:
        logger.warning(
            "[knowledge] blocked by validator: source=%s score=%.2f",
            result.source,
            result.score,
        )

    return state


# ---------------------------------------------------------------------------
# LLM generation (Tier 3 fallback)
# ---------------------------------------------------------------------------

def llm_generation_node(state: AgentState) -> AgentState:
    """Generate commands with Gemini when KB lookup found nothing."""
    if state.get("commands"):
        return state

    from ai.command_generator import generate_commands
    from ai.llm_engine import LLMEngine

    query = state.get("normalized_input") or ""
    engine = LLMEngine()
    commands = generate_commands(query, engine=engine)

    state["commands"] = commands or []
    state["source"] = "llm"
    logger.info("[llm] generated %d command(s)", len(state["commands"]))
    return state


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validator_node(state: AgentState) -> AgentState:
    """Safety-check all commands before execution."""
    commands = state.get("commands") or []
    safe = validate_commands(commands)
    state["validated"] = safe

    if not safe:
        state["error"] = "Unsafe command detected"
        logger.warning("[validator] blocked commands: %s", commands)
    else:
        logger.debug("[validator] commands passed")

    return state


# ---------------------------------------------------------------------------
# Executor  (previously missing from the graph)
# ---------------------------------------------------------------------------

def executor_node(state: AgentState) -> AgentState:
    """
    Execute validated, approved commands.

    The graph only reaches this node when:
      - state["validated"] is True
      - state["approved"] is True  (set by cli/main.py before re-invoking or
        by passing approved=True into the initial state for non-interactive use)
    """
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
# Learning  (previously missing from the graph)
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
