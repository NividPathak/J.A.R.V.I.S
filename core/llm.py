"""Model backend abstraction.

Deliberately narrow: one text-in/text-out call. Both providers return plain text
and callers parse leniently, which keeps the LLM router and the Phase 4 fine-tuned
router on an identical contract — the tuned model emits bare labels, so anything
richer here would be a shape the swap-in couldn't honour.
"""
from typing import Protocol, runtime_checkable

from config.settings import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    LLM_PROVIDER,
    OLLAMA_HOST,
    OLLAMA_MODEL,
)


@runtime_checkable
class LLM(Protocol):
    model: str

    def complete(self, system: str, user: str, max_tokens: int = 512) -> str: ...


class OllamaLLM:
    """Local, free. The default."""

    def __init__(self, model: str = OLLAMA_MODEL, host: str = OLLAMA_HOST):
        import ollama

        self.model = model
        self._client = ollama.Client(host=host)

    def complete(self, system: str, user: str, max_tokens: int = 512) -> str:
        response = self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options={"num_predict": max_tokens, "temperature": 0},
        )
        return response["message"]["content"].strip()


class AnthropicLLM:
    """Cloud fallback for when local quality isn't enough."""

    def __init__(self, model: str = ANTHROPIC_MODEL, api_key: str = ANTHROPIC_API_KEY):
        import anthropic

        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, user: str, max_tokens: int = 512) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            # Routing is a fast classification, not a reasoning task.
            output_config={"effort": "low"},
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()


def get_llm(provider: str | None = None, model: str | None = None) -> LLM:
    provider = (provider or LLM_PROVIDER).lower()
    if provider == "ollama":
        return OllamaLLM(model=model or OLLAMA_MODEL)
    if provider == "anthropic":
        return AnthropicLLM(model=model or ANTHROPIC_MODEL)
    raise ValueError(f"Unknown provider: {provider!r} (expected 'ollama' or 'anthropic')")
