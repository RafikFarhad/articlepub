from __future__ import annotations

import os
from typing import Any

from .llm.anthropic import AnthropicProvider
from .llm.base import LLMProvider, NoopProvider


def make_provider(
    provider_name: str,
    api_key: str | None = None,
    model: str | None = None,
    web_fetch_tool: str | None = None,
    timeout: int | None = None,
    retries: int | None = None,
    max_tokens: int | None = None,
) -> LLMProvider:
    if provider_name == "none":
        return NoopProvider()
    if provider_name != "anthropic":
        raise ValueError(f"Unknown provider: {provider_name}")
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("Anthropic provider requires --api-key or ANTHROPIC_API_KEY")
    kwargs: dict[str, Any] = {"api_key": key}
    if model:
        kwargs["model"] = model
    if web_fetch_tool:
        kwargs["web_fetch_tool"] = web_fetch_tool
    if timeout is not None:
        kwargs["timeout"] = timeout
    if retries is not None:
        kwargs["retries"] = retries
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return AnthropicProvider(**kwargs)
