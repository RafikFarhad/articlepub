from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urljoin

from .text import html_to_text


ALLOWED_TAGS = {
    "article",
    "section",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "blockquote",
    "pre",
    "code",
    "em",
    "strong",
    "b",
    "i",
    "ul",
    "ol",
    "li",
    "a",
    "br",
    "hr",
}
VOID_TAGS = {"br", "hr"}


class HTMLSanitizer(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.out: list[str] = []
        self.stack: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag not in ALLOWED_TAGS:
            return
        attrs_text = ""
        if tag == "a":
            href = next((value for key, value in attrs if key == "href" and value), None)
            if href:
                attrs_text = f' href="{escape(urljoin(self.base_url, href), quote=True)}"'
        if tag in VOID_TAGS:
            self.out.append(f"<{tag}{attrs_text} />")
            return
        self.out.append(f"<{tag}{attrs_text}>")
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        if tag in self.stack:
            while self.stack:
                open_tag = self.stack.pop()
                self.out.append(f"</{open_tag}>")
                if open_tag == tag:
                    break

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.out.append(escape(data))

    def close(self) -> None:
        super().close()
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")


def sanitize_article_html(html: str, base_url: str) -> str:
    parser = HTMLSanitizer(base_url)
    parser.feed(html)
    parser.close()
    cleaned = "".join(parser.out).strip()
    if "<article" not in cleaned:
        cleaned = f"<article>{cleaned}</article>"
    if not html_to_text(cleaned):
        return "<article><p>No readable content was extracted.</p></article>"
    return cleaned
