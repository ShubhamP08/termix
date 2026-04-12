"""
LangGraph pipeline for CLP1.

Flow:
  normalize → planner → knowledge_lookup → [llm if needed] → validator → executor → learning → END

All logic lives in the graph. cli/main.py only handles UI (display + confirm).
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.state import AgentState
from agent.nodes import (
    normalize_node,
    planner_node,
    knowledge_lookup_node,
    llm_generation_node,
    validator_node,
    executor_node,
    learning_node,
)


def _route_after_knowledge(state: AgentState) -> str:
    """Go to LLM if KB found nothing, otherwise validate directly."""
    if state.get("commands"):
        return "validator"
    return "llm"


def _route_after_validator(state: AgentState) -> str:
    """Only execute if commands passed validation and user approved."""
    if state.get("validated") and not state.get("error") and state.get("approved"):
        return "executor"
    return END


def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("normalize", normalize_node)
    builder.add_node("planner", planner_node)
    builder.add_node("knowledge", knowledge_lookup_node)
    builder.add_node("llm", llm_generation_node)
    builder.add_node("validator", validator_node)
    builder.add_node("executor", executor_node)
    builder.add_node("learning", learning_node)

    builder.set_entry_point("normalize")
    builder.add_edge("normalize", "planner")
    builder.add_edge("planner", "knowledge")

    builder.add_conditional_edges(
        "knowledge",
        _route_after_knowledge,
        {"validator": "validator", "llm": "llm"},
    )

    builder.add_edge("llm", "validator")

    builder.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"executor": "executor", END: END},
    )

    builder.add_edge("executor", "learning")
    builder.add_edge("learning", END)

    return builder.compile()


graph = build_graph()
