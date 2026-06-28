from __future__ import annotations

from dataclasses import dataclass

from ..stats import LLMUsage


@dataclass(slots=True)
class LLMArticle:
    title: str
    html: str
    author: str | None = None
    usage: LLMUsage | None = None
