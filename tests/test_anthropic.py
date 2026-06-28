import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from articlepub.llm.anthropic import AnthropicProvider
from articlepub.models import Article
from articlepub.raw_store import RawStore


class FakeResponse:
    status = 200

    def __init__(self, data: dict) -> None:
        self.data = data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.data).encode("utf-8")


class AnthropicProviderTest(TestCase):
    def test_remote_fetch_uses_web_fetch_tool_for_exact_domain(self) -> None:
        response = {
            "usage": {
                "input_tokens": 101,
                "output_tokens": 202,
                "cache_creation_input_tokens": 3,
                "cache_read_input_tokens": 4,
                "server_tool_use": {"web_fetch_requests": 1},
            },
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "title": "Fetched Post",
                            "author": "Rafik",
                            "html": "<article><p>Fetched content.</p></article>",
                        }
                    ),
                }
            ]
        }

        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(response)

        provider = AnthropicProvider(api_key="test-key", model="test-model")
        with patch("articlepub.llm.anthropic.urlopen", fake_urlopen):
            article = provider.fetch_article("https://www.rafikfarhad.me/some-post")

        self.assertEqual(article.title, "Fetched Post")
        self.assertEqual(article.author, "Rafik")
        self.assertIn("Fetched content.", article.html)
        self.assertEqual(captured["request"].headers["X-api-key"], "test-key")
        self.assertEqual(captured["payload"]["model"], "test-model")
        self.assertEqual(captured["payload"]["tools"][0]["name"], "web_fetch")
        self.assertEqual(captured["payload"]["tools"][1]["name"], "article_result")
        self.assertEqual(captured["payload"]["tools"][0]["allowed_domains"], ["www.rafikfarhad.me"])
        self.assertIn("Fetch exactly this URL", captured["payload"]["messages"][0]["content"])
        self.assertIsNotNone(article.usage)
        self.assertEqual(article.usage.input_tokens, 101)
        self.assertEqual(article.usage.output_tokens, 202)
        self.assertEqual(article.usage.extra["server_tool_use.web_fetch_requests"], 1)
        self.assertEqual(article.usage.total_tokens, 310)

    def test_refine_article_returns_json_article(self) -> None:
        response = {
            "content": [
                {
                    "type": "text",
                    "text": '{"title":"Clean","author":null,"html":"<article><p>Same sentence.</p></article>"}',
                }
            ]
        }

        with patch("articlepub.llm.anthropic.urlopen", return_value=FakeResponse(response)):
            provider = AnthropicProvider(api_key="test-key")
            refined = provider.refine_article(
                Article(
                    title="Raw",
                    author=None,
                    source_url="https://example.com",
                    html="<article><p>Same sentence.</p></article>",
                    text="Same sentence.",
                )
            )

        self.assertEqual(refined.title, "Clean")
        self.assertEqual(refined.html, "<article><p>Same sentence.</p></article>")

    def test_refine_article_prefers_structured_tool_result(self) -> None:
        response = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "article_result",
                    "input": {
                        "title": "Tool Clean",
                        "author": "Writer",
                        "html": '<article><p>A quoted "sentence" stays valid.</p></article>',
                    },
                }
            ]
        }
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(response)

        with patch("articlepub.llm.anthropic.urlopen", fake_urlopen):
            provider = AnthropicProvider(api_key="test-key")
            refined = provider.refine_article(
                Article(
                    title="Raw",
                    author=None,
                    source_url="https://example.com",
                    html="<article><p>Same sentence.</p></article>",
                    text="Same sentence.",
                )
            )

        self.assertEqual(refined.title, "Tool Clean")
        self.assertEqual(refined.author, "Writer")
        self.assertIn('quoted "sentence"', refined.html)
        self.assertEqual(captured["payload"]["tool_choice"], {"type": "tool", "name": "article_result"})
        self.assertEqual(captured["payload"]["tools"][0]["name"], "article_result")

    def test_retries_timeout_before_succeeding(self) -> None:
        response = {
            "content": [
                {
                    "type": "text",
                    "text": '{"title":"Retry Success","author":null,"html":"<article><p>Finished.</p></article>"}',
                }
            ]
        }
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise TimeoutError("read operation timed out")
            return FakeResponse(response)

        provider = AnthropicProvider(api_key="test-key", timeout=7, retries=1, retry_delay_s=0)
        with patch("articlepub.llm.anthropic.urlopen", fake_urlopen):
            refined = provider.refine_article(
                Article(
                    title="Raw",
                    author=None,
                    source_url="https://example.com",
                    html="<article><p>Finished.</p></article>",
                    text="Finished.",
                )
            )

        self.assertEqual(refined.title, "Retry Success")
        self.assertEqual(calls, [7, 7])

    def test_check_connection_uses_small_payload(self) -> None:
        response = {"content": [{"type": "text", "text": "OK"}]}
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(response)

        provider = AnthropicProvider(api_key="test-key", timeout=9, max_tokens=8192)
        with patch("articlepub.llm.anthropic.urlopen", fake_urlopen):
            provider.check_connection()

        self.assertEqual(captured["payload"]["max_tokens"], 8)
        self.assertEqual(captured["payload"]["messages"][0]["content"], "Reply with OK.")
        self.assertEqual(captured["timeout"], 9)

    def test_stores_request_response_and_text_when_raw_store_is_enabled(self) -> None:
        response = {
            "content": [
                {
                    "type": "text",
                    "text": '{"title":"Clean","author":null,"html":"<article><p>Same sentence.</p></article>"}',
                }
            ]
        }

        with TemporaryDirectory() as tmp:
            raw_store = RawStore(Path(tmp), enabled=True)
            provider = AnthropicProvider(api_key="test-key", raw_store=raw_store)
            with patch("articlepub.llm.anthropic.urlopen", return_value=FakeResponse(response)):
                provider.refine_article(
                    Article(
                        title="Raw",
                        author=None,
                        source_url="https://example.com",
                        html="<article><p>Same sentence.</p></article>",
                        text="Same sentence.",
                    )
                )

            names = sorted(path.name for path in raw_store.raw_dir.iterdir())
            self.assertTrue(any(name.endswith("-llm-refine-request.json") for name in names))
            self.assertTrue(any(name.endswith("-llm-refine-response.json") for name in names))
            self.assertTrue(any(name.endswith("-llm-refine-text.txt") for name in names))
            request_file = next(raw_store.raw_dir.glob("*-llm-refine-request.json"))
            request_text = request_file.read_text(encoding="utf-8")
            self.assertIn("Clean this extracted article", request_text)
            self.assertNotIn("test-key", request_text)
