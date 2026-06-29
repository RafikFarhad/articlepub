from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .cli_support import make_provider
from .cli_ui import TerminalUI
from .constants import DEFAULT_OUTPUT_DIR
from .diagnostics import DoctorOptions, run_doctor
from .models import CalibreConfig
from .pipeline import BuildOptions, build
from .tui import run_tui
from .upload import CalibreWebUploader, UploadResult


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    log_level = getattr(args, "log_level", None)
    is_doctor = getattr(args, "doctor", False) or args.command == "doctor"
    ui = TerminalUI.auto(log_level=log_level or "info", force_plain=log_level is not None or is_doctor)
    try:
        if args.command == "add":
            if args.doctor:
                return _doctor(args, ui)
            return _add(args, ui)
        if args.command == "doctor":
            return _doctor(args, ui)
        if args.command == "upload":
            return _upload(args, ui)
        if args.command == "tui":
            return run_tui(ui)
        if args.command == "version":
            print(__version__)
            return 0
        parser.print_help()
        return 2
    except Exception as exc:
        ui.error(str(exc))
        return 1


def _add(args: argparse.Namespace, ui: TerminalUI) -> int:
    ui.banner()
    provider = make_provider(
        args.provider,
        api_key=args.api_key,
        model=args.model,
        web_fetch_tool=args.web_fetch_tool,
        timeout=args.llm_timeout,
        retries=args.llm_retries,
        max_tokens=args.llm_max_tokens,
    )
    calibre = _calibre_config(args) if args.calibre_url else None
    upload_reporter = _UploadReporter(ui, buffered=True)
    ui.info(f"Fetch mode: {args.fetch_mode}")
    ui.info(f"Provider: {args.provider}")
    with ui.spinner("Building EPUB", "EPUB ready"):
        result = build(
            BuildOptions(
                url=args.url,
                output_dir=Path(args.out),
                fetch_mode=args.fetch_mode,
                strict=args.strict,
                title=args.title,
                provider=provider,
                calibre=calibre,
                log=ui.debug,
                upload_progress=upload_reporter.progress,
                store_metadata=args.store_metadata,
            )
        )
    ui.success(f"Saved {result.epub_path}")
    ui.report(result)
    if calibre and result.upload_result:
        if not upload_reporter.emitted:
            upload_reporter.report_result(calibre, result.upload_result)
        upload_reporter.report_final(result.upload_result)
        upload_reporter.flush()
    print(result.epub_path)
    if result.upload_result:
        print(result.upload_result.book_url or result.upload_result.location or "uploaded")
        return 1 if result.upload_result.shelf_errors else 0
    return 0


def _upload(args: argparse.Namespace, ui: TerminalUI) -> int:
    ui.banner()
    config = _calibre_config(args)
    upload_reporter = _UploadReporter(ui)

    try:
        result = CalibreWebUploader(config, log=ui.debug, progress=upload_reporter.progress).upload_result(Path(args.epub))
    except Exception as exc:
        ui.error(f"Book upload failed: {exc}")
        return 1

    if not upload_reporter.emitted:
        upload_reporter.report_result(config, result)
    upload_reporter.report_final(result)
    print(result.book_url or result.location or "uploaded")
    return 1 if result.shelf_errors else 0


class _UploadReporter:
    def __init__(self, ui: TerminalUI, buffered: bool = False) -> None:
        self.ui = ui
        self.buffered = buffered
        self.emitted = False
        self.events: list[tuple[str, str]] = []

    def progress(self, level: str, message: str) -> None:
        self.emitted = True
        self._record_or_emit(level, message)

    def flush(self) -> None:
        for level, message in self.events:
            self._emit(level, message)
        self.events.clear()

    def report_result(self, config: CalibreConfig, result: UploadResult) -> None:
        if config.username and config.password:
            self._record_or_emit("success", "Login succeeded")
        else:
            self._record_or_emit("info", "Login skipped (anonymous mode)")
        self._record_or_emit("success", "Book uploaded")
        if result.book_url:
            self._record_or_emit("info", f"Book: {result.book_url}")
        if config.shelf_names:
            self._record_or_emit("info", "Fetching shelves")
        for shelf_name in result.shelves_added:
            self._record_or_emit("success", f"Added to shelf: {shelf_name}")
        for shelf_name in result.shelves_present:
            self._record_or_emit("info", f"Already on shelf: {shelf_name}")
        for error in result.shelf_errors:
            self._record_or_emit("warning", f"Shelf update failed: {error}")

    def report_final(self, result: UploadResult) -> None:
        if result.shelf_errors:
            self._record_or_emit("warning", "Book uploaded, but shelf update failed")
        else:
            self._record_or_emit("success", "Book uploaded successfully")

    def _record_or_emit(self, level: str, message: str) -> None:
        if self.buffered:
            self.events.append((level, message))
            return
        self._emit(level, message)

    def _emit(self, level: str, message: str) -> None:
        if level == "success":
            self.ui.success(message)
        elif level == "warning":
            self.ui.warning(message)
        else:
            self.ui.info(message)


def _doctor(args: argparse.Namespace, ui: TerminalUI) -> int:
    report = run_doctor(
        DoctorOptions(
            url=args.url,
            output_dir=Path(args.out),
            fetch_mode=args.fetch_mode,
            provider_name=args.provider,
            api_key=args.api_key,
            model=args.model,
            web_fetch_tool=args.web_fetch_tool,
            strict=args.strict,
            title=args.title,
            store_metadata=args.store_metadata,
            llm_timeout=args.llm_timeout,
            llm_retries=args.llm_retries,
            llm_max_tokens=args.llm_max_tokens,
            calibre_url=args.calibre_url,
            calibre_username=args.calibre_username,
            calibre_password=args.calibre_password,
            calibre_api_key=args.calibre_api_key,
            doctor_timeout=args.doctor_timeout,
            doctor_enabled=getattr(args, "doctor", False),
            log_level=args.log_level,
        )
    )
    ui.doctor_report(report)
    return 0 if report.ok else 1


def _calibre_config(args: argparse.Namespace) -> CalibreConfig:
    return CalibreConfig(
        base_url=args.calibre_url,
        username=args.calibre_username,
        password=args.calibre_password,
        api_key=args.calibre_api_key,
        shelf_names=args.calibre_shelf or [],
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="articlepub")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    add = sub.add_parser("add", help="Convert a URL to EPUB")
    _add_conversion_args(add)
    add.add_argument("--doctor", action="store_true", help="Validate flags, credentials, and config, then exit.")

    doctor = sub.add_parser("doctor", help="Validate URL, flags, provider credentials, and config")
    _add_conversion_args(doctor)

    upload = sub.add_parser("upload", help="Upload an existing EPUB to Calibre-Web")
    upload.add_argument("epub")
    _add_log_level(upload)
    _add_calibre_args(upload, require_url=True)

    sub.add_parser("tui", help="Run the interactive terminal UI")
    sub.add_parser("version", help="Print the ArticlePub version")
    return parser


def _add_conversion_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("url")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--fetch-mode", choices=["auto", "local", "llm"], default="auto")
    parser.add_argument("--provider", choices=["none", "anthropic"], default="anthropic")
    parser.add_argument("--api-key")
    parser.add_argument("--model")
    parser.add_argument("--web-fetch-tool")
    parser.add_argument("--llm-timeout", type=_positive_int, help="LLM API read timeout in seconds. Anthropic default is 300.")
    parser.add_argument("--llm-retries", type=_non_negative_int, help="Retry count for retryable LLM API failures. Anthropic default is 2.")
    parser.add_argument("--llm-max-tokens", type=_positive_int, help="Maximum output tokens for the LLM response. Anthropic default is 8192.")
    parser.add_argument("--doctor-timeout", type=_positive_int, default=10, help="Live doctor API check timeout in seconds.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--title")
    parser.add_argument("--store-metadata", action="store_true", help="Write raw debug artifacts to OUT/.raw for this run.")
    _add_log_level(parser)
    _add_calibre_args(parser, require_url=False)


def _add_calibre_args(parser: argparse.ArgumentParser, require_url: bool) -> None:
    parser.add_argument("--calibre-url", required=require_url)
    parser.add_argument("--calibre-username")
    parser.add_argument("--calibre-password")
    parser.add_argument("--calibre-api-key")
    parser.add_argument("--calibre-shelf", action="append", help="Add uploaded book to a Calibre-Web shelf by name. Repeat for multiple shelves.")


def _add_log_level(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--log-level",
        choices=["quiet", "error", "warning", "info", "debug"],
        help="Control stderr status output. Use debug to see each timed pipeline step.",
    )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return parsed
