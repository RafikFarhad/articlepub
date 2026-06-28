from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser

from .models import Article
from .text import html_to_text, normalize_whitespace


BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre"}
NOISE_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form"}


@dataclass(slots=True)
class Block:
    tag: str
    text: str


@dataclass(slots=True)
class ParsedPage:
    title: str | None = None
    author: str | None = None
    meta_title: str | None = None
    blocks: list[Block] = field(default_factory=list)


class ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = ParsedPage()
        self._skip: list[str] = []
        self._title_parts: list[str] = []
        self._in_title = False
        self._current_tag: str | None = None
        self._current_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value for key, value in attrs if value is not None}
        if tag in NOISE_TAGS:
            self._skip.append(tag)
            return
        if self._skip:
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            self._handle_meta(attrs_dict)
            return
        if tag in BLOCK_TAGS:
            self._flush_current()
            self._current_tag = tag
            self._current_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._skip and tag == self._skip[-1]:
            self._skip.pop()
            return
        if self._skip:
            return
        if tag == "title":
            self._in_title = False
            self.page.title = normalize_whitespace(" ".join(self._title_parts)) or self.page.title
            return
        if self._current_tag == tag:
            self._flush_current()

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._current_tag:
            self._current_parts.append(data)

    def close(self) -> None:
        self._flush_current()
        super().close()

    def _flush_current(self) -> None:
        if not self._current_tag:
            return
        text = normalize_whitespace(" ".join(self._current_parts))
        if text and not _looks_like_noise(text):
            self.page.blocks.append(Block(self._current_tag, text))
        self._current_tag = None
        self._current_parts = []

    def _handle_meta(self, attrs: dict[str, str]) -> None:
        key = attrs.get("property") or attrs.get("name") or ""
        content = normalize_whitespace(attrs.get("content") or "")
        if not content:
            return
        key = key.casefold()
        if key in {"og:title", "twitter:title"}:
            self.page.meta_title = content
        elif key in {"author", "article:author", "twitter:creator"}:
            self.page.author = content.lstrip("@")


def extract_article(html: str, source_url: str) -> Article:
    parser = ArticleParser()
    parser.feed(html)
    parser.close()
    page = parser.page

    title = _choose_title(page)
    blocks = _trim_blocks(page.blocks, title)
    if not blocks:
        text = html_to_text(html)
        if not text:
            raise ValueError("Could not extract readable article content")
        blocks = [Block("p", text)]

    article_html = blocks_to_html(blocks, source_url)
    text = html_to_text(article_html)
    return Article(title=title, author=page.author, html=article_html, text=text, source_url=source_url)


def blocks_to_html(blocks: list[Block], source_url: str) -> str:
    out: list[str] = ["<article>"]
    in_list = False
    for block in blocks:
        tag = block.tag if block.tag in BLOCK_TAGS else "p"
        text = escape(block.text)
        if tag == "li":
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{text}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if tag == "pre":
            out.append(f"<pre>{text}</pre>")
        else:
            out.append(f"<{tag}>{text}</{tag}>")
    if in_list:
        out.append("</ul>")
    out.append("</article>")
    return "\n".join(out)


def _choose_title(page: ParsedPage) -> str:
    first_h1 = next((block.text for block in page.blocks if block.tag == "h1"), None)
    title = first_h1 or page.meta_title or page.title or "Untitled Article"
    title = title.split("|")[0].strip()
    return title or "Untitled Article"


def _trim_blocks(blocks: list[Block], title: str) -> list[Block]:
    usable = [block for block in blocks if len(block.text) >= 2]
    if not usable:
        return []
    while usable and _is_chrome_block(usable[0].text, title):
        usable.pop(0)
    while usable and _is_chrome_block(usable[-1].text, title):
        usable.pop()
    return usable


def _is_chrome_block(text: str, title: str) -> bool:
    lowered = text.casefold()
    if lowered == title.casefold():
        return False
    return lowered in {"home", "about", "archive", "archives", "subscribe", "privacy", "terms"} or len(text) <= 2


def _looks_like_noise(text: str) -> bool:
    lowered = text.casefold()
    if lowered in {"menu", "navigation", "skip to content"}:
        return True
    if len(text) < 20 and lowered in {"home", "about", "blog", "contact", "archive", "subscribe"}:
        return True
    return False
