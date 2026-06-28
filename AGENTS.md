@/Users/farhad/.codex/RTK.md

# Project Guide

This repo is a small Python 3.11 CLI/TUI app named `articlepub`. It converts article/blog URLs into Kindle-friendly EPUB files and can optionally upload them to Calibre-Web.

## How To Work Here

- Run shell commands through `rtk`.
- Use `PYTHONPATH=src` for local execution unless the package is installed.
- Keep the app dependency-free unless the user explicitly approves adding dependencies.
- Do not run live Anthropic or Calibre-Web calls unless the user asks or provides credentials for that purpose.
- Never print API keys, passwords, bearer tokens, or secret URL query values in logs, doctor output, or errors.
- Raw debug artifacts under `OUT/.raw` may intentionally contain fetched HTML, LLM requests, and LLM responses. Terminal output must still redact secrets.

## Useful Commands

```bash
PYTHONPATH=src python -m articlepub --help
PYTHONPATH=src python -m articlepub add "file://$PWD/tests/fixtures/blog.html" --provider none --fetch-mode local --out /private/tmp/articlepub-check --log-level debug
PYTHONPATH=src python -m articlepub doctor https://www.rafikfarhad.me/ --provider none
PYTHONPATH=src python -m unittest discover -s tests
```

For live Anthropic testing:

```bash
PYTHONPATH=src python -m articlepub add "https://www.rafikfarhad.me/" --provider anthropic --api-key "$ANTHROPIC_API_KEY" --log-level debug --store-metadata
```

## Current CLI Behavior

- Main command: `articlepub add URL`.
- Default output directory: `dist`.
- Default fetch mode: `auto`.
- Default provider: `anthropic`.
- API key source: `--api-key` or `ANTHROPIC_API_KEY`.
- `--fetch-mode local`: local fetch/extract, then provider refinement.
- `--fetch-mode llm`: skip local fetch and ask the LLM provider to fetch the URL.
- `--fetch-mode auto`: local fetch/extract first; fall back to LLM fetch only when local fetch/extract fails or extraction is too short. Do not fall back when LLM refinement fails.
- `--doctor` validates flags/config and performs a short live Anthropic check when provider/key are present.
- `--store-metadata` recreates `OUT/.raw` for the run. Without it, stale `OUT/.raw` data is deleted.
- `--log-level debug` should show each pipeline step and elapsed time. Long-running steps redraw one transient `running:` line in place, then print the final `ok:` or `failed:` line permanently.

## Important Files

- `src/articlepub/cli.py`: argparse commands and flags.
- `src/articlepub/cli_ui.py`: banner, colored output, spinner, report formatting, redacted writes.
- `src/articlepub/pipeline.py`: URL-to-EPUB orchestration and step timing boundaries.
- `src/articlepub/stats.py`: run timing, LLM usage, debug heartbeat for long steps.
- `src/articlepub/llm/anthropic.py`: Anthropic Messages API provider.
- `src/articlepub/prompts.py`: LLM prompts.
- `src/articlepub/raw_store.py`: `.raw` metadata storage and cleanup.
- `src/articlepub/redaction.py`: secret redaction for terminal output.
- `src/articlepub/diagnostics.py`: doctor checks.
- `tests/`: unittest suite; add focused tests for behavior changes.

## Anthropic Notes

- Local refinement uses the `article_result` tool with forced `tool_choice`; avoid returning to free-form JSON parsing for the normal path.
- Remote fetch uses Anthropic's `web_fetch` server tool plus the same `article_result` tool.
- Preserve article sentences. The LLM may clean structure and formatting, but should not rewrite content.
- Store LLM request/response artifacts only through `RawStore` when `--store-metadata` is enabled.

## Output Style Expectations

Keep live logs and final reports visually consistent:

```text
INFO  Fetch mode: auto
DEBUG     0ms start: llm refine article (AnthropicProvider)
DEBUG 130.23s ok: llm refine article

INFO  Run summary
INFO  Title: Example
INFO  Total: 130.47s

INFO  Step timing
OK    130.23s llm refine article (AnthropicProvider)
```

The spinner is intentionally disabled in debug mode so logs do not interleave. Long-running debug status should redraw in place on TTYs and stay quiet on non-TTY streams.

## Test Expectations

- Run the full suite before finishing code changes:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

- Prefer unit tests with mocked providers/fetchers over network tests.
- Add regression tests when changing logging, redaction, doctor checks, raw metadata, or Anthropic payload parsing.
