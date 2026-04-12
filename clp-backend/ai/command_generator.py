"""
Command generation layer stub.

Produces a proposed terminal command from the selected retrieval candidate / plan.
"""

from __future__ import annotations

import os
from typing import List

from agent.state import AgentState

from ai.llm_engine import LLMEngine
from services.llm import safe_parse


def generate_command(state: AgentState) -> AgentState:
    instruction = state.get("user_query") or ""
    engine = LLMEngine()
    commands = generate_commands(instruction, engine=engine)
    # For now, keep the first command as the proposed command to match existing AgentState usage.
    state["proposed_command"] = commands[0] if commands else ""
    return state


def _load_prompt_template() -> str:
    prompts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts"))
    path = os.path.join(prompts_dir, "command_prompt.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_commands_json(text: str) -> List[str]:
    """
    Parse a JSON response of the form: {"commands": ["..."]}.
    Uses safe_parse() with retry repair.
    """
    obj = safe_parse(text, retries=2)
    if isinstance(obj, dict) and isinstance(obj.get("commands"), list):
        commands = [c for c in obj["commands"] if isinstance(c, str) and c.strip()]
        return [c.strip() for c in commands]
    raise ValueError('Expected JSON object with a "commands" list.')


def generate_commands(user_instruction: str, *, engine: LLMEngine) -> List[str]:
    """
    Steps:
    1) load prompt template
    2) insert user instruction
    3) call llm_engine
    4) parse JSON response
    5) return list of commands

    Falls back to returning empty list if generation fails.
    """
    try:
        template = _load_prompt_template().rstrip()
        prompt = f"{template}\n\nUser instruction:\n{user_instruction}\n"
        raw = engine.complete(prompt)
        return _parse_commands_json(raw)
    except Exception as e:
        print(f"Command generation failed: {e}")
        return []

