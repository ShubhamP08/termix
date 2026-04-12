"""
Typed AgentState passed through the LangGraph StateGraph.

Placeholder only — field set may evolve as nodes are implemented.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict


IntentType = Literal[
    "file_op",
    "network",
    "process",
    "git",
    "unknown",
]


class RetrievalCandidate(TypedDict, total=False):
    source: Literal["json_kb", "vector", "llm"]
    intent: IntentType
    command: str
    explanation: str
    score: float
    metadata: Dict[str, Any]


class AgentState(TypedDict, total=False):
    # Core fields (requested)
    user_input: str
    normalized_input: str
    tasks: List[str]
    commands: List[str]
    source: str
    intent: IntentType
    validated: bool
    approved: bool
    execution_result: Dict[str, Any]
    error: str

    # Backward-compatible / extended fields (kept for future graph wiring)
    user_query: str
    normalized_query: str

    # Retrieval fan-out results
    kb_candidates: List[RetrievalCandidate]
    vector_candidates: List[RetrievalCandidate]
    llm_candidates: List[RetrievalCandidate]

    # Confidence routing
    best_candidate: RetrievalCandidate
    confidence: float
    needs_clarification: bool
    clarification_question: str

    # Safety + execution
    proposed_command: str
    dry_run_preview: str
    blocked_reason: str

    # History / trace for multi-turn context
    history: List[Dict[str, Any]]

