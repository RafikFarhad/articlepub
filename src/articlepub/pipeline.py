from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .epub import write_epub
from .extract import extract_article
from .fetch import LocalFetcher
from .llm.base import LLMProvider, NoopProvider
from .models import Article, BuildResult, CalibreConfig
from .raw_store import RawStore
from .sanitize import sanitize_article_html
from .stats import BuildStats, LogFn
from .text import assert_sentences_preserved, html_to_text
from .upload import CalibreWebUploader, ProgressLog


@dataclass(slots=True)
class BuildOptions:
    url: str
    output_dir: Path
    fetch_mode: str = "auto"
    strict: bool = False
    title: str | None = None
    provider: LLMProvider | None = None
    local_fetcher: LocalFetcher | None = None
    calibre: CalibreConfig | None = None
    stats: BuildStats | None = None
    log: LogFn | None = None
    upload_progress: ProgressLog | None = None
    store_metadata: bool = False


def build(options: BuildOptions) -> BuildResult:
    stats = options.stats or BuildStats()
    raw_store = RawStore(options.output_dir, options.store_metadata)
    try:
        provider = options.provider or NoopProvider()
        provider.set_raw_store(raw_store if options.store_metadata else None)
        fetcher = options.local_fetcher or LocalFetcher()
        article: Article
        source_for_validation: str | None = None

        if options.fetch_mode == "local":
            article, source_for_validation = _extract_local_article(options.url, fetcher, stats, options.log, raw_store)
            _refine_article(article, provider, stats, options.log)
        elif options.fetch_mode == "llm":
            article = _remote_article(options.url, provider, stats, options.log, raw_store)
        elif options.fetch_mode == "auto":
            try:
                article, source_for_validation = _extract_local_article(options.url, fetcher, stats, options.log, raw_store)
            except Exception:
                if not provider.supports_remote_fetch:
                    raise
                if options.log:
                    options.log("local path failed; falling back to LLM fetch")
                article = _remote_article(options.url, provider, stats, options.log, raw_store)
                source_for_validation = None
            else:
                if len(article.text) < 300 and provider.supports_remote_fetch:
                    if options.log:
                        options.log("local extraction was short; falling back to LLM fetch")
                    article = _remote_article(options.url, provider, stats, options.log, raw_store)
                    source_for_validation = None
                else:
                    _refine_article(article, provider, stats, options.log)
        else:
            raise ValueError(f"Unknown fetch mode: {options.fetch_mode}")

        with stats.step("sanitize article html", log=options.log):
            if options.title:
                article.title = options.title
            article.html = sanitize_article_html(article.html, article.source_url)
            article.text = html_to_text(article.html)
            raw_store.write_text(
                "sanitized-article",
                "html",
                article.html,
                metadata={"source_url": article.source_url, "title": article.title},
                content_type="text/html",
            )

        if options.strict and source_for_validation:
            with stats.step("strict sentence validation", log=options.log):
                assert_sentences_preserved(source_for_validation, article.text)

        with stats.step("write epub", str(options.output_dir), log=options.log):
            epub_path = write_epub(article, options.output_dir)
        result = BuildResult(article=article, epub_path=epub_path, stats=stats)
        if options.calibre:
            with stats.step("upload to calibre-web", options.calibre.base_url, log=options.log):
                upload_result = CalibreWebUploader(
                    options.calibre,
                    log=options.log,
                    progress=options.upload_progress,
                ).upload_result(epub_path)
            result.uploaded = True
            result.upload_response = upload_result.response_text
            result.upload_result = upload_result
        return result
    finally:
        stats.finish()


def _extract_local_article(
    url: str,
    fetcher: LocalFetcher,
    stats: BuildStats,
    log: LogFn | None,
    raw_store: RawStore,
) -> tuple[Article, str]:
    with stats.step("local fetch", url, log=log):
        fetched = fetcher.fetch(url)
        raw_store.write_text(
            "local-fetch",
            "html",
            fetched.body,
            metadata={"url": fetched.url, "final_url": fetched.final_url, "content_type": fetched.content_type},
            content_type=fetched.content_type or "text/html",
        )
    with stats.step("extract main content", fetched.final_url or fetched.url, log=log):
        article = extract_article(fetched.body, fetched.final_url or fetched.url)
        raw_store.write_text(
            "extracted-article",
            "html",
            article.html,
            metadata={"source_url": article.source_url, "title": article.title, "author": article.author},
            content_type="text/html",
        )
        raw_store.write_text(
            "extracted-text",
            "txt",
            article.text,
            metadata={"source_url": article.source_url, "title": article.title},
            content_type="text/plain",
        )
    source_text = article.text
    return article, source_text


def _refine_article(article: Article, provider: LLMProvider, stats: BuildStats, log: LogFn | None) -> None:
    with stats.step("llm refine article", provider.__class__.__name__, log=log):
        refined = provider.refine_article(article)
        stats.add_llm_usage(refined.usage)
        article.title = refined.title or article.title
        article.author = refined.author or article.author
        article.html = refined.html
        article.text = html_to_text(article.html)


def _remote_article(
    url: str,
    provider: LLMProvider,
    stats: BuildStats,
    log: LogFn | None,
    raw_store: RawStore,
) -> Article:
    if not provider.supports_remote_fetch:
        raise RuntimeError("The selected provider does not support LLM remote fetch mode")
    with stats.step("llm fetch article", provider.__class__.__name__, log=log):
        fetched = provider.fetch_article(url)
        stats.add_llm_usage(fetched.usage)
    with stats.step("sanitize remote article", url, log=log):
        html = sanitize_article_html(fetched.html, url)
        raw_store.write_text(
            "remote-article",
            "html",
            html,
            metadata={"source_url": url, "title": fetched.title, "author": fetched.author},
            content_type="text/html",
        )
    return Article(title=fetched.title, author=fetched.author, html=html, text=html_to_text(html), source_url=url)
