import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from articlepub.epub import write_epub
from articlepub.models import Article


class EpubTest(TestCase):
    def test_writes_epub_container_files(self) -> None:
        article = Article(
            title="A Test Article",
            author="Writer",
            source_url="https://example.com/post",
            html="<article><h1>A Test Article</h1><p>Body text stays here.</p></article>",
            text="Body text stays here.",
        )
        with TemporaryDirectory() as tmp:
            path = write_epub(article, Path(tmp))

            self.assertTrue(path.exists())
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                self.assertEqual(names[0], "mimetype")
                self.assertEqual(zf.read("mimetype"), b"application/epub+zip")
                self.assertIn("META-INF/container.xml", names)
                self.assertIn("OEBPS/content.opf", names)
                self.assertIn("OEBPS/nav.xhtml", names)
                chapter = zf.read("OEBPS/chapter.xhtml").decode("utf-8")
                self.assertIn("A Test Article", chapter)
                self.assertIn("Body text stays here.", chapter)
