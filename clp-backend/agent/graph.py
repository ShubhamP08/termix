"""
LangGraph pipeline for CLP1.

Simplified flow (LLM fallback is now inside the retriever):

  normalize → planner → knowledge → validator → [executor] → [learning] → END

All retrieval logic (fuzzy → semantic → LLM) lives in the unified
``knowledge.retriever.retrieve()`` pipeline.  The graph only handles
flow control: normalise, plan, retrieve, validate, execute, learn.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.state import AgentState
from agent.nodes import (
    normalize_node,
    planner_node,
    knowledge_lookup_node,
    validator_node,
    executor_node,
    learning_node,
)


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
    builder.add_node("validator", validator_node)
    builder.add_node("executor", executor_node)
    builder.add_node("learning", learning_node)

    builder.set_entry_point("normalize")
    builder.add_edge("normalize", "planner")
    builder.add_edge("planner", "knowledge")

    # Retriever now handles LLM fallback internally, so knowledge
    # always produces commands (or empty).  Go straight to validator.
    builder.add_edge("knowledge", "validator")

    builder.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"executor": "executor", END: END},
    )

    builder.add_edge("executor", "learning")
    builder.add_edge("learning", END)

    return builder.compile()


graph = build_graph()
