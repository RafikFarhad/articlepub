from __future__ import annotations

import hashlib
import re
import zipfile
from datetime import timezone
from html import escape
from pathlib import Path

from .models import Article
from .sanitize import sanitize_article_html


def write_epub(article: Article, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{slugify(article.title)}.epub"
    path = output_dir / filename
    identifier = "urn:articlepub:" + hashlib.sha1(article.source_url.encode("utf-8")).hexdigest()
    chapter = _chapter_xhtml(article)
    nav = _nav_xhtml(article)
    opf = _opf(article, identifier)

    with zipfile.ZipFile(path, "w") as zf:
        mimetype = zipfile.ZipInfo("mimetype")
        mimetype.compress_type = zipfile.ZIP_STORED
        zf.writestr(mimetype, "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/nav.xhtml", nav)
        zf.writestr("OEBPS/chapter.xhtml", chapter)
        zf.writestr("OEBPS/style.css", STYLE_CSS)
    return path


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug[:80] or "article"


def _chapter_xhtml(article: Article) -> str:
    body = sanitize_article_html(article.html, article.source_url)
    author = f"<p class=\"byline\">{escape(article.author)}</p>" if article.author else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{escape(article.title)}</title>
  <link rel="stylesheet" type="text/css" href="style.css" />
</head>
<body>
  <header>
    <h1>{escape(article.title)}</h1>
    {author}
    <p class="source"><a href="{escape(article.source_url, quote=True)}">{escape(article.source_url)}</a></p>
  </header>
  {body}
</body>
</html>
"""


def _nav_xhtml(article: Article) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{escape(article.title)}</title>
</head>
<body>
  <nav epub:type="toc" id="toc" xmlns:epub="http://www.idpf.org/2007/ops">
    <h1>Contents</h1>
    <ol>
      <li><a href="chapter.xhtml">{escape(article.title)}</a></li>
    </ol>
  </nav>
</body>
</html>
"""


def _opf(article: Article, identifier: str) -> str:
    fetched = article.fetched_at.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    author = escape(article.author or "Unknown")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{escape(identifier)}</dc:identifier>
    <dc:title>{escape(article.title)}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>en</dc:language>
    <dc:source>{escape(article.source_url)}</dc:source>
    <meta property="dcterms:modified">{fetched}</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml" />
    <item id="style" href="style.css" media-type="text/css" />
  </manifest>
  <spine>
    <itemref idref="chapter" />
  </spine>
</package>
"""


CONTAINER_XML = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" />
  </rootfiles>
</container>
"""


STYLE_CSS = """
body {
  font-family: serif;
  line-height: 1.45;
  margin: 5%;
}
h1, h2, h3, h4, h5, h6 {
  line-height: 1.2;
  margin-top: 1.6em;
}
p, li {
  margin: 0.75em 0;
}
blockquote {
  border-left: 0.2em solid #999;
  margin-left: 0;
  padding-left: 1em;
}
pre {
  white-space: pre-wrap;
  font-family: monospace;
}
.byline, .source {
  color: #555;
  font-size: 0.9em;
}
"""
