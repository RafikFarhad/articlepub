from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import FetchResult


class LocalFetchError(RuntimeError):
    pass


class LocalFetcher:
    def __init__(self, timeout: int = 30, user_agent: str | None = None) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or "articlepub/0.1 (+https://github.com/local/articlepub)"

    def fetch(self, url: str) -> FetchResult:
        parsed = urlparse(url)
        if parsed.scheme == "file":
            path = Path(parsed.path)
            return FetchResult(url=url, body=path.read_text(encoding="utf-8"), content_type="text/html", final_url=url)
        if parsed.scheme not in {"http", "https"}:
            raise LocalFetchError(f"Unsupported URL scheme: {parsed.scheme or '<missing>'}")

        request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                content_type = response.headers.get("content-type")
                charset = response.headers.get_content_charset() or "utf-8"
                return FetchResult(
                    url=url,
                    body=raw.decode(charset, errors="replace"),
                    content_type=content_type,
                    final_url=response.geturl(),
                )
        except (HTTPError, URLError, TimeoutError) as exc:
            raise LocalFetchError(str(exc)) from exc
