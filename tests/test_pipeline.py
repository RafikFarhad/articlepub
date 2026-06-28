from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from articlepub.llm.base import LLMProvider
from articlepub.llm.base import NoopProvider
from articlepub.llm.types import LLMArticle
from articlepub.models import Article, FetchResult
from articlepub.pipeline import BuildOptions, build
from articlepub.stats import LLMUsage
from articlepub.text import assert_sentences_preserved


FIXTURE = Path(__file__).parent / "fixtures" / "blog.html"


class RecordingProvider(LLMProvider):
    supports_remote_fetch = True

    def __init__(self) -> None:
        self.refined = False
        self.remote = False

    def refine_article(self, article: Article) -> LLMArticle:
        self.refined = True
        return LLMArticle(title=article.title, author=article.author, html=article.html)

    def fetch_article(self, url: str) -> LLMArticle:
        self.remote = True
        return LLMArticle(
            title="Remote",
            author=None,
            html="<article><p>Remote article sentence.</p></article>",
            usage=LLMUsage(provider="test", model="fake", input_tokens=12, output_tokens=34),
        )


class FailingFetcher:
    def fetch(self, url: str):
        raise RuntimeError("blocked")


class HTMLFetcher:
    def fetch(self, url: str) -> FetchResult:
        paragraph = "This article sentence is long enough to avoid short-content fallback. " * 10
        return FetchResult(
            url=url,
            final_url=url,
            content_type="text/html",
            body=f"<html><body><article><h1>Local Article</h1><p>{paragraph}</p></article></body></html>",
        )


class FailingRefineProvider(LLMProvider):
    supports_remote_fetch = True

    def __init__(self) -> None:
        self.remote = False

    def refine_article(self, article: Article) -> LLMArticle:
        raise RuntimeError("refine timed out")

    def fetch_article(self, url: str) -> LLMArticle:
        self.remote = True
        return LLMArticle(title="Remote", author=None, html="<article><p>Remote.</p></article>")


class PipelineTest(TestCase):
    def test_auto_falls_back_to_remote_fetch(self) -> None:
        provider = RecordingProvider()
        with TemporaryDirectory() as tmp:
            result = build(
                BuildOptions(
                    url="https://example.com/post",
                    output_dir=Path(tmp),
                    fetch_mode="auto",
                    provider=provider,
                    local_fetcher=FailingFetcher(),
                )
            )
            self.assertTrue(result.epub_path.exists())

        self.assertTrue(provider.remote)
        self.assertEqual(result.article.title, "Remote")
        self.assertIn("local fetch", [step.name for step in result.stats.steps])
        self.assertIn("llm fetch article", [step.name for step in result.stats.steps])
        self.assertEqual(result.stats.total_llm_usage.input_tokens, 12)
        self.assertEqual(result.stats.total_llm_usage.output_tokens, 34)

    def test_auto_does_not_fall_back_to_remote_when_refine_fails(self) -> None:
        provider = FailingRefineProvider()

        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "refine timed out"):
                build(
                    BuildOptions(
                        url="https://example.com/post",
                        output_dir=Path(tmp),
                        fetch_mode="auto",
                        provider=provider,
                        local_fetcher=HTMLFetcher(),
                    )
                )

        self.assertFalse(provider.remote)

    def test_store_metadata_writes_raw_files_and_next_run_cleans_them(self) -> None:
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = build(
                BuildOptions(
                    url=FIXTURE.as_uri(),
                    output_dir=output_dir,
                    fetch_mode="local",
                    provider=NoopProvider(),
                    store_metadata=True,
                )
            )

            raw_dir = output_dir / ".raw"
            self.assertTrue(result.epub_path.exists())
            self.assertTrue(raw_dir.exists())
            names = sorted(path.name for path in raw_dir.iterdir())
            self.assertIn("manifest.json", names)
            self.assertTrue(any(name.endswith("-local-fetch.html") for name in names))
            self.assertTrue(any(name.endswith("-extracted-article.html") for name in names))
            self.assertTrue(any(name.endswith("-sanitized-article.html") for name in names))

            (raw_dir / "stale.txt").write_text("stale", encoding="utf-8")
            build(
                BuildOptions(
                    url=FIXTURE.as_uri(),
                    output_dir=output_dir,
                    fetch_mode="local",
                    provider=NoopProvider(),
                    store_metadata=False,
                )
            )

            self.assertFalse(raw_dir.exists())

    def test_strict_preservation_detects_rewritten_sentence(self) -> None:
        source = "This exact sentence belongs to the article and should not change."
        output = "This altered sentence belongs to the article and should not change."

        with self.assertRaises(ValueError):
            assert_sentences_preserved(source, output)
