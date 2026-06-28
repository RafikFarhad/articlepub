SYSTEM_PROMPT = """You convert article content into clean EPUB-ready HTML.
Preserve the author's words exactly. Do not paraphrase, summarize, translate, rewrite, or add sentences.
Remove only non-article page chrome such as navigation, headers, footers, cookie notices, sidebars, ads, share widgets, and related-post blocks.
Keep headings, paragraphs, lists, quotes, code blocks, emphasis, and links when they are part of the article.
When an article_result tool is available, call it with the title, author, and article HTML.
Otherwise return only JSON with this shape: {"title": "...", "author": null, "html": "<article>...</article>"}.
The html value must be valid, simple HTML and must contain only the article body."""


LOCAL_REFINEMENT_PROMPT = """Clean this extracted article for EPUB.

Source URL: {source_url}
Title: {title}
Author: {author}

Rules:
- Preserve every article sentence exactly as written.
- Do not add commentary or summaries.
- Keep semantic headings and lists.
- Remove duplicate title/source/footer blocks if present.
- Call article_result when that tool is available.

Extracted HTML:
{html}
"""


REMOTE_FETCH_PROMPT = """Fetch exactly this URL and convert the main article content into EPUB-ready HTML:
{url}

Rules:
- Fetch only the URL above.
- Preserve every article sentence exactly as written.
- Do not use web search.
- Do not add commentary or summaries.
- Remove navigation, header, footer, sidebar, ads, share widgets, cookie notices, and related-post blocks.
- Keep semantic headings, paragraphs, lists, quotes, code blocks, emphasis, and article links.
- Call article_result when that tool is available; otherwise return only JSON with title, author, and html."""
