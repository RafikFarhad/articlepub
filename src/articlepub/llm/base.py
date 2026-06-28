from __future__ import annotations

from .types import LLMArticle
from ..models import Article
from ..raw_store import RawStore


class LLMProvider:
    supports_remote_fetch = False
    raw_store: RawStore | None = None

    def set_raw_store(self, raw_store: RawStore | None) -> None:
        self.raw_store = raw_store

    def refine_article(self, article: Article) -> LLMArticle:
        raise NotImplementedError

    def fetch_article(self, url: str) -> LLMArticle:
        raise NotImplementedError


class NoopProvider(LLMProvider):
    def refine_article(self, article: Article) -> LLMArticle:
        return LLMArticle(title=article.title, author=article.author, html=article.html)

    def fetch_article(self, url: str) -> LLMArticle:
        raise RuntimeError("No LLM provider is configured for remote fetch mode")
