from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .base import LLMProvider
from .types import LLMArticle
from ..models import Article
from ..prompts import LOCAL_REFINEMENT_PROMPT, REMOTE_FETCH_PROMPT, SYSTEM_PROMPT
from ..raw_store import RawStore
from ..stats import LLMUsage


ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_WEB_FETCH_TOOL = "web_fetch_20260318"
ARTICLE_RESULT_TOOL = {
    "name": "article_result",
    "description": "Return the cleaned article as structured fields for EPUB generation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "author": {"type": ["string", "null"]},
            "html": {"type": "string"},
        },
        "required": ["title", "html"],
        "additionalProperties": False,
    },
}


class AnthropicError(RuntimeError):
    pass


@dataclass(slots=True)
class AnthropicProvider(LLMProvider):
    api_key: str
    model: str = DEFAULT_MODEL
    max_tokens: int = 8192
    timeout: int = 300
    retries: int = 2
    retry_delay_s: float = 1.0
    api_url: str = ANTHROPIC_MESSAGES_URL
    web_fetch_tool: str = DEFAULT_WEB_FETCH_TOOL
    anthropic_version: str = "2023-06-01"
    raw_store: RawStore | None = None

    supports_remote_fetch = True

    def refine_article(self, article: Article) -> LLMArticle:
        payload = self._base_payload(
            user_content=LOCAL_REFINEMENT_PROMPT.format(
                source_url=article.source_url,
                title=article.title,
                author=article.author or "",
                html=article.html,
            )
        )
        payload["tools"] = [ARTICLE_RESULT_TOOL]
        payload["tool_choice"] = {"type": "tool", "name": "article_result"}
        return self._request_article(payload, "llm-refine")

    def fetch_article(self, url: str) -> LLMArticle:
        domain = urlparse(url).hostname
        if not domain:
            raise AnthropicError("Remote fetch requires a URL with a hostname")
        payload = self._base_payload(user_content=REMOTE_FETCH_PROMPT.format(url=url))
        payload["tools"] = [
            {
                "type": self.web_fetch_tool,
                "name": "web_fetch",
                "max_uses": 1,
                "allowed_domains": [domain],
                "citations": {"enabled": False},
                "max_content_tokens": 100000,
            },
            ARTICLE_RESULT_TOOL,
        ]
        return self._request_article(payload, "llm-fetch")

    def check_connection(self) -> None:
        payload = {
            "model": self.model,
            "max_tokens": min(self.max_tokens, 8),
            "messages": [{"role": "user", "content": "Reply with OK."}],
        }
        response = self._post_json(payload, "doctor-check")
        _content_text(response)

    def _base_payload(self, user_content: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_content}],
        }

    def _request_article(self, payload: dict[str, Any], label: str) -> LLMArticle:
        response = self._post_json(payload, label)
        data = _article_result_tool_input(response)
        if data is not None:
            if self.raw_store:
                self.raw_store.write_json(
                    f"{label}-tool-input",
                    data,
                    metadata={"model": self.model},
                )
        else:
            text = _content_text(response)
            if self.raw_store:
                self.raw_store.write_text(
                    f"{label}-text",
                    "txt",
                    text,
                    metadata={"model": self.model},
                    content_type="text/plain",
                )
            data = _parse_json_object(text)
        title = str(data.get("title") or "Untitled Article").strip()
        author = data.get("author")
        html = str(data.get("html") or "").strip()
        if not html:
            raise AnthropicError("Anthropic response did not include article HTML")
        return LLMArticle(
            title=title,
            author=str(author).strip() if author else None,
            html=html,
            usage=_usage(response, provider="anthropic", model=self.model),
        )

    def _post_json(self, payload: dict[str, Any], label: str) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        attempts = max(0, self.retries) + 1
        last_error: Exception | None = None
        if self.raw_store:
            self.raw_store.write_json(
                f"{label}-request",
                {
                    "url": self.api_url,
                    "timeout": self.timeout,
                    "retries": self.retries,
                    "headers": {
                        "content-type": "application/json",
                        "anthropic-version": self.anthropic_version,
                    },
                    "payload": payload,
                },
                metadata={"model": self.model},
            )
        for attempt in range(1, attempts + 1):
            request = Request(
                self.api_url,
                data=body,
                headers={
                    "content-type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": self.anthropic_version,
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    if self.raw_store:
                        self.raw_store.write_json(
                            f"{label}-response",
                            data,
                            metadata={"model": self.model, "attempt": attempt},
                        )
                    return data
            except HTTPError as exc:
                if not _retryable_http(exc) or attempt == attempts:
                    detail = exc.read().decode("utf-8", errors="replace")
                    if self.raw_store:
                        self.raw_store.write_text(
                            f"{label}-error",
                            "txt",
                            detail,
                            metadata={"status": exc.code, "attempt": attempt},
                            content_type="text/plain",
                        )
                    raise AnthropicError(f"Anthropic API error {exc.code}: {detail}") from exc
                last_error = exc
            except (URLError, TimeoutError) as exc:
                if attempt == attempts:
                    if self.raw_store:
                        self.raw_store.write_json(
                            f"{label}-error",
                            {"error": str(exc), "attempt": attempt, "timeout": self.timeout},
                        )
                    raise AnthropicError(
                        f"Anthropic API request failed after {attempts} attempt(s), "
                        f"timeout={self.timeout}s: {exc}"
                    ) from exc
                last_error = exc
            if attempt < attempts:
                time.sleep(self.retry_delay_s * attempt)
        raise AnthropicError(f"Anthropic API request failed: {last_error}")


def _content_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in response.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    text = "\n".join(part for part in parts if part).strip()
    if not text:
        raise AnthropicError("Anthropic response did not include a text result")
    return text


def _article_result_tool_input(response: dict[str, Any]) -> dict[str, Any] | None:
    for block in response.get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use" or block.get("name") != "article_result":
            continue
        data = block.get("input")
        if not isinstance(data, dict):
            raise AnthropicError("Anthropic article_result tool input was not an object")
        return data
    return None


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AnthropicError("Anthropic response was not valid JSON")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AnthropicError(f"Anthropic response was not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AnthropicError("Anthropic response JSON was not an object")
    return data


def _usage(response: dict[str, Any], provider: str, model: str | None) -> LLMUsage | None:
    raw = response.get("usage")
    if not isinstance(raw, dict):
        return None
    known = {
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    }
    extra = _extra_usage(raw, known)
    return LLMUsage(
        provider=provider,
        model=model,
        input_tokens=_int(raw.get("input_tokens")),
        output_tokens=_int(raw.get("output_tokens")),
        cache_creation_input_tokens=_int(raw.get("cache_creation_input_tokens")),
        cache_read_input_tokens=_int(raw.get("cache_read_input_tokens")),
        extra=extra,
    )


def _int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _extra_usage(raw: dict[str, Any], known: set[str]) -> dict[str, int]:
    extra: dict[str, int] = {}
    for key, value in raw.items():
        if key in known:
            continue
        if isinstance(value, int):
            extra[key] = value
        elif isinstance(value, dict):
            for nested_key, nested_value in value.items():
                if isinstance(nested_value, int):
                    extra[f"{key}.{nested_key}"] = nested_value
    return extra


def _retryable_http(exc: HTTPError) -> bool:
    return exc.code == 429 or 500 <= exc.code < 600
