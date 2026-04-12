"""
Error recovery stub.

Intended to propose fixes when execution fails (e.g. command not found, permission denied).
"""

from __future__ import annotations

from agent.state import AgentState


def recover(state: AgentState) -> AgentState:
    raise NotImplementedError

