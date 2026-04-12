"""
Planning layer stub.

Responsible for converting user intent + context into a structured plan before command generation.
"""

from __future__ import annotations

import os
from typing import List

from agent.state import AgentState

from ai.llm_engine import LLMEngine
from services.llm import safe_parse


def plan(state: AgentState) -> AgentState:
    user_request = state.get("user_query") or ""
    engine = LLMEngine()
    tasks = plan_tasks(user_request, engine=engine)
    state["plan"] = tasks
    return state


def _load_prompt_template() -> str:
    prompts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts"))
    path = os.path.join(prompts_dir, "planner_prompt.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_tasks_json(text: str) -> List[str]:
    obj = safe_parse(text, retries=2)
    if isinstance(obj, dict) and isinstance(obj.get("tasks"), list):
        tasks = [t for t in obj["tasks"] if isinstance(t, str) and t.strip()]
        return [t.strip() for t in tasks]
    raise ValueError('Expected JSON object with a "tasks" list.')


def plan_tasks(user_request: str, *, engine: LLMEngine) -> List[str]:
    """
    Convert a user request into smaller tasks.

    Falls back to returning the original request if planning fails.

    Example:
      "setup fastapi project"
    Output:
      ["create folder","create venv","install fastapi","create main.py"]
    """
    try:
        template = _load_prompt_template().rstrip()
        prompt = f"{template}\n\nUser request:\n{user_request}\n"
        raw = engine.complete(prompt)
        return _parse_tasks_json(raw)
    except Exception as e:
        # If planning fails, just return the original request as a single task
        print(f"Planning failed: {e}, using user request as single task")
        return [user_request]

