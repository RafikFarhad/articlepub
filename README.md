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

## CLI Reference

`add` converts a URL to EPUB. `doctor` validates the same conversion flags without building an EPUB.

| Command | Argument or flag | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `add`, `doctor` | `url` | Yes | None | Article URL to convert or validate. |
| `add`, `doctor` | `--out` | No | `dist` | Output directory for EPUB and optional `.raw` metadata. |
| `add`, `doctor` | `--fetch-mode` | No | `auto` | Choices: `auto`, `local`, `llm`. |
| `add`, `doctor` | `--provider` | No | `anthropic` | Choices: `anthropic`, `none`. |
| `add`, `doctor` | `--api-key` | Conditional | `ANTHROPIC_API_KEY` env var, otherwise none | Required when `--provider anthropic` and `ANTHROPIC_API_KEY` is not set. |
| `add`, `doctor` | `--model` | No | `claude-sonnet-4-6` | Anthropic model name. |
| `add`, `doctor` | `--web-fetch-tool` | No | `web_fetch_20260318` | Anthropic server-tool version used by `--fetch-mode llm`. |
| `add`, `doctor` | `--llm-timeout` | No | `300` | Anthropic read timeout in seconds. |
| `add`, `doctor` | `--llm-retries` | No | `2` | Retry count for retryable Anthropic failures. |
| `add`, `doctor` | `--llm-max-tokens` | No | `8192` | Maximum Anthropic output tokens. |
| `add`, `doctor` | `--doctor-timeout` | No | `10` | Live doctor API check timeout in seconds. |
| `add`, `doctor` | `--strict` | No | `false` | Enables sentence-preservation validation when local source text is available. |
| `add`, `doctor` | `--title` | No | None | Overrides the EPUB title after extraction/refinement. |
| `add`, `doctor` | `--store-metadata` | No | `false` | Stores raw debug artifacts under `OUT/.raw`; without it, stale `.raw` data is removed. |
| `add`, `doctor` | `--log-level` | No | `info` | Choices: `quiet`, `error`, `warning`, `info`, `debug`. |
| `add`, `doctor` | `--calibre-url` | No | None | Calibre-Web base URL. Use `http://calibre.example.test/calibre-web/` for a path-mounted server. |
| `add`, `doctor` | `--calibre-username` | Conditional | None | Optional for anonymous upload; must be paired with `--calibre-password` when used. |
| `add`, `doctor` | `--calibre-password` | Conditional | None | Optional for anonymous upload; must be paired with `--calibre-username` when used. |
| `add`, `doctor` | `--calibre-api-key` | No | None | Optional Calibre-Web API token header. |
| `add` | `--doctor` | No | `false` | Validates flags/config and exits instead of building. |

`upload` sends an existing EPUB to Calibre-Web.

| Command | Argument or flag | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `upload` | `epub` | Yes | None | Path to an existing `.epub` file. |
| `upload` | `--calibre-url` | Yes | None | Calibre-Web base URL. |
| `upload` | `--calibre-username` | Conditional | None | Optional for anonymous upload; must be paired with `--calibre-password` when used. |
| `upload` | `--calibre-password` | Conditional | None | Optional for anonymous upload; must be paired with `--calibre-username` when used. |
| `upload` | `--calibre-api-key` | No | None | Optional Calibre-Web API token header. |
| `upload` | `--log-level` | No | `info` | Choices: `quiet`, `error`, `warning`, `info`, `debug`. |

`tui` has no flags.

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
