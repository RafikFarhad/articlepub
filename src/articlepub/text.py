from __future__ import annotations

import re
from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip.append(tag)
            return
        if self._skip:
            return
        if tag in {"p", "div", "section", "article", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip and tag == self._skip[-1]:
            self._skip.pop()
            return
        if self._skip:
            return
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return normalize_whitespace(" ".join(part.strip() for part in self._parts if part.strip()))


def html_to_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def comparable_text(value: str) -> str:
    return normalize_whitespace(value).casefold()


def split_sentences(value: str) -> list[str]:
    text = normalize_whitespace(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def assert_sentences_preserved(source_text: str, output_text: str) -> None:
    source = comparable_text(source_text)
    missing: list[str] = []
    for sentence in split_sentences(output_text):
        comparable = comparable_text(sentence)
        if len(comparable) < 40:
            continue
        if comparable not in source:
            missing.append(sentence)
    if missing:
        preview = "; ".join(missing[:3])
        raise ValueError(f"LLM output appears to rewrite or add sentence content: {preview}")
