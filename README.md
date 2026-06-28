# ArticlePub

`articlepub` turns a blog/article URL into a Kindle-friendly EPUB and can upload it to Calibre-Web.

## Examples

```bash
python -m articlepub add https://www.rafikfarhad.me/ --out dist
python -m articlepub add https://www.rafikfarhad.me/ --provider anthropic --api-key "$ANTHROPIC_API_KEY"
python -m articlepub add https://www.rafikfarhad.me/ --fetch-mode llm --provider anthropic --api-key "$ANTHROPIC_API_KEY"
python -m articlepub add https://www.rafikfarhad.me/ --calibre-url https://calibre.example.com --calibre-username user --calibre-password pass
python -m articlepub tui
```

In an interactive terminal, the CLI shows a colored banner, spinner animation, and ASCII status faces. When stdout/stderr are redirected, it keeps output plain for scripting.

Use `--log-level debug` to see each timed pipeline step as it runs. The final status report includes total runtime, per-step timing, and LLM token usage when the provider returns it.

```bash
python -m articlepub add https://www.rafikfarhad.me/ --log-level debug
```

For slower LLM web fetches, increase the Anthropic timeout or retries:

```bash
python -m articlepub add https://www.rafikfarhad.me/ --llm-timeout 600 --llm-retries 3
```

Store raw run artifacts for debugging:

```bash
python -m articlepub add https://www.rafikfarhad.me/ --store-metadata
```

This recreates `OUT/.raw` for each run. Without `--store-metadata`, stale `OUT/.raw` data is deleted.

Run doctor before a long job to validate the URL, output directory, flag combinations, Calibre config, and Anthropic key/model with a short API call:

```bash
python -m articlepub add https://www.rafikfarhad.me/ --doctor
python -m articlepub doctor https://www.rafikfarhad.me/ --doctor-timeout 10
```

## Fetch Modes

- `local`: fetches the URL locally, extracts the main article, then optionally asks the LLM to clean the article HTML.
- `llm`: does not fetch locally; asks the LLM provider to fetch the exact URL with its web-fetch tool.
- `auto`: tries local first and falls back to LLM fetch when local fetch/extraction fails.

## Anthropic

Anthropic support uses the Messages API directly. For `--fetch-mode llm`, it enables Claude's `web_fetch` server tool and restricts the request to the domain of the URL you passed.

The API key can be passed with `--api-key` or `ANTHROPIC_API_KEY`.

## Prompts

LLM prompts live in `src/articlepub/prompts.py`.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
