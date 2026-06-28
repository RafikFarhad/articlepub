from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .stats import BuildStats


@dataclass(slots=True)
class Article:
    title: str
    html: str
    text: str
    source_url: str
    author: str | None = None
    published: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FetchResult:
    url: str
    body: str
    content_type: str | None = None
    final_url: str | None = None


@dataclass(slots=True)
class BuildResult:
    article: Article
    epub_path: Path
    stats: BuildStats = field(default_factory=BuildStats)
    uploaded: bool = False
    upload_response: str | None = None


@dataclass(slots=True)
class CalibreConfig:
    base_url: str
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
