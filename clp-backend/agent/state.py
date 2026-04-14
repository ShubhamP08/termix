"""
Typed AgentState passed through the LangGraph StateGraph.

Kept minimal — only fields that nodes actually read or write.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict


IntentType = Literal[
    "file_op",
    "general",
    "unknown",
]


class AgentState(TypedDict, total=False):
    # ── Input ──────────────────────────────────────────────────────────
    user_input: str
    normalized_input: str
    tasks: List[str]

    # ── Retrieval output ───────────────────────────────────────────────
    commands: List[str]
    source: str                 # "kb_fuzzy" | "kb_semantic" | "llm" | "none"
    score: float                # 0.0–1.0 normalised confidence
    intent: IntentType
    requires_confirmation: bool
    rule_id: Optional[str]      # KB rule ID for traceability

    # ── Tool execution layer ───────────────────────────────────────────
    tool_name: str              # e.g. "create_file", "open_app"
    tool_output: str            # stdout from Python-native tool execution
    missing_placeholders: List[str]  # slot names the user must still provide
    pending_tool: Dict[str, Any]     # deferred Python tool execution payload

    # ── Validation / execution ─────────────────────────────────────────
    validated: bool
    approved: bool
    execution_result: Dict[str, Any]
    error: str

    # ── History / trace for multi-turn context ─────────────────────────
    history: List[Dict[str, Any]]
