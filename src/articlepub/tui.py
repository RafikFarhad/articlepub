from __future__ import annotations

from pathlib import Path

from .cli_support import make_provider
from .cli_ui import TerminalUI
from .models import CalibreConfig
from .pipeline import BuildOptions, build


def run_tui(ui: TerminalUI | None = None) -> int:
    ui = ui or TerminalUI.auto()
    ui.banner()
    if not ui.enabled:
        print("ArticlePub")
        print("---------")
    url = input("URL: ").strip()
    if not url:
        ui.error("URL is required")
        return 2
    fetch_mode = _choice("Fetch mode", ["auto", "local", "llm"], "auto")
    provider_name = _choice("Provider", ["none", "anthropic"], "anthropic")
    api_key = input("API key (blank uses env/provider default): ").strip() or None
    output_dir = Path(input("Output directory [dist]: ").strip() or "dist")
    calibre_url = input("Calibre-Web URL (blank to skip upload): ").strip() or None
    calibre = None
    if calibre_url:
        username = input("Calibre-Web username (blank if not needed): ").strip() or None
        password = input("Calibre-Web password (blank if not needed): ").strip() or None
        calibre = CalibreConfig(base_url=calibre_url, username=username, password=password)

    provider = make_provider(provider_name, api_key=api_key)
    with ui.spinner("Building EPUB", "EPUB ready"):
        result = build(
            BuildOptions(
                url=url,
                output_dir=output_dir,
                fetch_mode=fetch_mode,
                provider=provider,
                calibre=calibre,
                log=ui.debug,
            )
        )
    ui.report(result)
    print(f"EPUB: {result.epub_path}")
    if result.uploaded:
        ui.success("Uploaded to Calibre-Web")
    return 0


def _choice(label: str, choices: list[str], default: str) -> str:
    values = "/".join(choice.upper() if choice == default else choice for choice in choices)
    while True:
        answer = input(f"{label} [{values}]: ").strip().lower() or default
        if answer in choices:
            return answer
        print(f"Choose one of: {', '.join(choices)}")
