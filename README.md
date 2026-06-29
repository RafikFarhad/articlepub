# ArticlePub

Turn a long article or blog post into a clean, Kindle-friendly EPUB.

ArticlePub is for the moment when you find something worth reading, but you want it in your reading queue instead of another browser tab. Give it a URL, get an EPUB, and optionally send that EPUB straight to Calibre-Web.

## Quick Start

If you have `uv`, you can run ArticlePub without installing it permanently:

```bash
uvx articlepub add "https://example.com/article" --provider none
```

That creates an EPUB in `dist/`.

Want AI cleanup and better article structure? Set your Anthropic key and leave the provider at its default:

```bash
export ANTHROPIC_API_KEY="..."
uvx articlepub add "https://example.com/article"
```

Trying ArticlePub before it is available from your Python package index? Run it directly from GitHub:

```bash
uvx --from git+https://github.com/RafikFarhad/articlepub.git articlepub add "https://example.com/article" --provider none
```

## Send To Calibre-Web

If your Calibre-Web server allows anonymous uploads:

```bash
uvx articlepub add "https://example.com/article" \
  --provider none \
  --calibre-url "https://calibre.example.com/"
```

If login is required:

```bash
uvx articlepub add "https://example.com/article" \
  --calibre-url "https://calibre.example.com/" \
  --calibre-username "articlepub" \
  --calibre-password "your-password"
```

Add the uploaded book to a shelf:

```bash
uvx articlepub add "https://example.com/article" \
  --calibre-url "https://calibre.example.com/" \
  --calibre-shelf "Quick Read"
```

Shelf names can contain spaces. Repeat `--calibre-shelf` to add the book to more than one shelf.

Already have an EPUB? Upload it directly:

```bash
uvx articlepub upload \
  --calibre-url "https://calibre.example.com/" \
  --calibre-shelf "Quick Read" \
  dist/article.epub
```

## What You Get

ArticlePub prints the EPUB path to stdout, so it is easy to script:

```text
dist/example-article.epub
```

When Calibre-Web upload is enabled, it also prints the Calibre-Web book URL when available:

```text
dist/example-article.epub
https://calibre.example.com/book/35
```

Status messages go to stderr and tell the story of the run:

```text
OK    Saved dist/example-article.epub  :-)
OK    Book uploaded  :-)
INFO  Book: https://calibre.example.com/book/35
OK    Added to shelf: Quick Read  :-)
OK    Book uploaded successfully  :-)
```

## Common Recipes

Save to a different folder:

```bash
uvx articlepub add "https://example.com/article" --provider none --out ~/Documents/epubs
```

Override the EPUB title:

```bash
uvx articlepub add "https://example.com/article" --provider none --title "Weekend Reading"
```

Use Claude to fetch the page directly when local extraction fails. This requires `ANTHROPIC_API_KEY` or `--api-key`:

```bash
uvx articlepub add "https://example.com/article" --fetch-mode llm
```

Check your setup before a long run:

```bash
uvx articlepub doctor "https://example.com/article" --provider none
```

See detailed timing and upload diagnostics:

```bash
uvx articlepub add "https://example.com/article" --provider none --log-level debug
```

Keep raw debug artifacts for one run:

```bash
uvx articlepub add "https://example.com/article" --provider none --store-metadata
```

Raw artifacts are written under `OUT/.raw`. Without `--store-metadata`, stale `.raw` data is removed.

## Fetch Modes

ArticlePub starts with `--fetch-mode auto`.

- `auto`: try local extraction first, then fall back to LLM fetch when needed.
- `local`: fetch and extract locally, then optionally ask the provider to clean the HTML.
- `llm`: ask the LLM provider to fetch the URL directly.

If you do not want to use an LLM, add `--provider none`.

## Useful Options

| Option | What it does |
| --- | --- |
| `--out dist` | Choose where EPUB files are written. |
| `--provider none` | Build without an LLM or API key. |
| `--api-key ...` | Pass an Anthropic key directly instead of using `ANTHROPIC_API_KEY`. |
| `--title "..."` | Override the EPUB title. |
| `--log-level debug` | Show detailed timing and Calibre-Web steps. |
| `--doctor` | Validate an `add` command without building the EPUB. |
| `--calibre-url ...` | Upload the result to Calibre-Web. |
| `--calibre-username ...` and `--calibre-password ...` | Log in before uploading. |
| `--calibre-shelf "Quick Read"` | Add the uploaded book to a shelf. |

Run `uvx articlepub --help` or `uvx articlepub add --help` for the full CLI reference.

## Local Development

From a checkout of this repository:

```bash
PYTHONPATH=src python -m articlepub add "file://$PWD/tests/fixtures/blog.html" \
  --provider none \
  --fetch-mode local \
  --out /private/tmp/articlepub-check \
  --log-level debug
```

Run the test suite:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
