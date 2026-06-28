from __future__ import annotations

import hashlib
import random
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
    cover_filename, cover_media_type, cover_data = _cover_image(article, identifier)
    cover = _cover_xhtml(article, cover_filename)
    opf = _opf(article, identifier, cover_filename, cover_media_type)

    with zipfile.ZipFile(path, "w") as zf:
        mimetype = zipfile.ZipInfo("mimetype")
        mimetype.compress_type = zipfile.ZIP_STORED
        zf.writestr(mimetype, "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/nav.xhtml", nav)
        zf.writestr("OEBPS/cover.xhtml", cover)
        zf.writestr(f"OEBPS/{cover_filename}", cover_data)
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


def _cover_xhtml(article: Article, cover_filename: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>Cover</title>
  <style type="text/css">
    body {{ margin: 0; }}
    img {{ display: block; height: 100vh; margin: 0 auto; max-width: 100%; }}
  </style>
</head>
<body>
  <img src="{escape(cover_filename, quote=True)}" alt="Cover for {escape(article.title, quote=True)}" />
</body>
</html>
"""


def _opf(article: Article, identifier: str, cover_filename: str, cover_media_type: str) -> str:
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
    <meta name="cover" content="cover-image" />
    <meta property="dcterms:modified">{fetched}</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml" />
    <item id="cover-image" href="{escape(cover_filename, quote=True)}" media-type="{cover_media_type}" properties="cover-image" />
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml" />
    <item id="style" href="style.css" media-type="text/css" />
  </manifest>
  <spine>
    <itemref idref="cover" linear="no" />
    <itemref idref="chapter" />
  </spine>
  <guide>
    <reference type="cover" title="Cover" href="cover.xhtml" />
  </guide>
</package>
"""


def _cover_image(article: Article, identifier: str) -> tuple[str, str, bytes]:
    try:
        return _cover_jpeg(article, identifier)
    except Exception:
        return "cover.svg", "image/svg+xml", _cover_svg(article, identifier).encode("utf-8")


def _cover_jpeg(article: Article, identifier: str) -> tuple[str, str, bytes]:
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    width, height = 1200, 1800
    rng = random.Random(identifier)
    background = _cover_palette(rng)
    image = Image.new("RGB", (width, height), background[0])
    pixels = image.load()
    for y in range(height):
        t = y / (height - 1)
        row = tuple(int(background[0][i] * (1 - t) + background[1][i] * t) for i in range(3))
        for x in range(width):
            pixels[x, y] = row

    draw = ImageDraw.Draw(image)
    for _ in range(10):
        color = tuple(min(255, c + rng.randint(6, 22)) for c in background[rng.randrange(2)])
        x0 = rng.randint(-width // 5, width)
        y0 = rng.randint(-height // 5, height)
        x1 = x0 + rng.randint(width // 4, width // 2)
        y1 = y0 + rng.randint(height // 8, height // 3)
        draw.rounded_rectangle((x0, y0, x1, y1), radius=42, fill=color)

    title_font = _cover_font(ImageFont, 82)
    meta_font = _cover_font(ImageFont, 38)
    title_lines = _wrap_cover_text(draw, article.title, title_font, width - 220, max_lines=7)
    line_heights = [_text_size(draw, line, title_font)[1] for line in title_lines]
    title_height = sum(line_heights) + 26 * max(0, len(title_lines) - 1)
    y = max(260, (height - title_height) // 2 - 90)
    text_color = (28, 34, 38)
    for index, line in enumerate(title_lines):
        line_width, line_height = _text_size(draw, line, title_font)
        draw.text(((width - line_width) / 2, y), line, fill=text_color, font=title_font)
        y += line_height + (26 if index < len(title_lines) - 1 else 0)

    meta = article.author or "ArticlePub"
    source = _host_label(article.source_url)
    for label, offset in [(meta, height - 250), (source, height - 185)]:
        label_width, _ = _text_size(draw, label, meta_font)
        draw.text(((width - label_width) / 2, offset), label, fill=(57, 66, 72), font=meta_font)

    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return "cover.jpg", "image/jpeg", output.getvalue()


def _cover_svg(article: Article, identifier: str) -> str:
    rng = random.Random(identifier)
    background = _cover_palette(rng)
    title_lines = _fallback_wrap(article.title, 24, 7)
    title = "".join(
        f'<text x="50%" y="{430 + index * 92}" text-anchor="middle">{escape(line)}</text>'
        for index, line in enumerate(title_lines)
    )
    author = article.author or "ArticlePub"
    source = _host_label(article.source_url)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1800" viewBox="0 0 1200 1800">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="{_rgb_hex(background[0])}" />
      <stop offset="100%" stop-color="{_rgb_hex(background[1])}" />
    </linearGradient>
  </defs>
  <rect width="1200" height="1800" fill="url(#bg)" />
  <g fill="#1c2226" font-family="serif" font-size="78" font-weight="700">{title}</g>
  <text x="50%" y="1560" text-anchor="middle" fill="#394248" font-family="serif" font-size="38">{escape(author)}</text>
  <text x="50%" y="1628" text-anchor="middle" fill="#394248" font-family="serif" font-size="34">{escape(source)}</text>
</svg>
"""


def _cover_palette(rng: random.Random) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    palettes = [
        ((232, 238, 233), (203, 224, 226)),
        ((239, 234, 222), (214, 227, 215)),
        ((231, 237, 244), (219, 226, 210)),
        ((238, 232, 236), (211, 226, 230)),
        ((235, 238, 225), (224, 219, 236)),
    ]
    return palettes[rng.randrange(len(palettes))]


def _cover_font(image_font, size: int):
    for name in ("DejaVuSerif.ttf", "Georgia.ttf", "Times New Roman.ttf"):
        try:
            return image_font.truetype(name, size=size)
        except OSError:
            continue
    try:
        return image_font.load_default(size=size)
    except TypeError:
        return image_font.load_default()


def _wrap_cover_text(draw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    words = text.split()
    if not words:
        return ["Untitled"]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_size(draw, candidate, font)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        while _text_size(draw, current, font)[0] > max_width and len(current) > 1:
            cut = max(1, len(current) - 1)
            while cut > 1 and _text_size(draw, current[:cut], font)[0] > max_width:
                cut -= 1
            lines.append(current[:cut])
            current = current[cut:]
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".") + "..."
    return lines


def _fallback_wrap(text: str, width: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return (lines or ["Untitled"])[:max_lines]


def _text_size(draw, text: str, font) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _host_label(url: str) -> str:
    match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)", url)
    return match.group(1) if match else "articlepub"


def _rgb_hex(value: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*value)


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
