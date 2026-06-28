from pathlib import Path
from unittest import TestCase

from articlepub.extract import extract_article


FIXTURE = Path(__file__).parent / "fixtures" / "blog.html"


class ExtractArticleTest(TestCase):
    def test_extracts_article_without_page_chrome(self) -> None:
        article = extract_article(FIXTURE.read_text(encoding="utf-8"), "https://www.rafikfarhad.me/")

        self.assertEqual(article.title, "Example Blog Post")
        self.assertEqual(article.author, "Rafik Farhad")
        self.assertIn("This is the first paragraph of the article.", article.text)
        self.assertIn("A Section", article.text)
        self.assertNotIn("Subscribe to my newsletter", article.text)
        self.assertNotIn("Privacy", article.text)
