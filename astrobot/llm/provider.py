"""LLM providers behind one interface, so OpenAI can be swapped for Claude by configuration."""
from __future__ import annotations

import os
from typing import Protocol


class LLMProvider(Protocol):
    def complete(self, system: str, messages: list[dict[str, str]], max_tokens: int = 600) -> str: ...


class OpenAIProvider:
    def __init__(self, model: str | None = None, client=None):
        from openai import OpenAI

        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = client or OpenAI()

    def complete(self, system: str, messages: list[dict[str, str]], max_tokens: int = 600) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=max_tokens,
            temperature=0.4,
        )
        return response.choices[0].message.content or ""


def get_provider(name: str | None = None) -> LLMProvider:
    name = (name or os.getenv("LLM_PROVIDER", "openai")).lower()
    if name == "openai":
        return OpenAIProvider()
    raise ValueError(f"Unknown LLM provider: {name}")
