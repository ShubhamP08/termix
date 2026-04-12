"""
LLM engine abstraction.

Default implementation calls Gemini API service.
"""

from __future__ import annotations

from services.llm import call_llm


class LLMEngine:
    def __init__(self) -> None:
        # Placeholder for future configuration (model, base URL, timeouts, etc.)
        pass

    def complete(self, prompt: str) -> str:
        return call_llm(prompt)

