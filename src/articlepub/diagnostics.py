from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .llm.anthropic import DEFAULT_MODEL, DEFAULT_WEB_FETCH_TOOL, AnthropicError, AnthropicProvider
from .redaction import redact_secrets


@dataclass(slots=True)
class DoctorOptions:
    url: str | None
    output_dir: Path
    fetch_mode: str
    provider_name: str
    api_key: str | None = None
    model: str | None = None
    web_fetch_tool: str | None = None
    strict: bool = False
    title: str | None = None
    store_metadata: bool = False
    llm_timeout: int | None = None
    llm_retries: int | None = None
    llm_max_tokens: int | None = None
    calibre_url: str | None = None
    calibre_username: str | None = None
    calibre_password: str | None = None
    calibre_api_key: str | None = None
    doctor_timeout: int = 10
    doctor_enabled: bool = True
    log_level: str | None = None


@dataclass(slots=True)
class DoctorCheck:
    name: str
    status: str
    message: str


@dataclass(slots=True)
class DoctorReport:
    checks: list[DoctorCheck] = field(default_factory=list)

    def add(self, name: str, status: str, message: str) -> None:
        self.checks.append(DoctorCheck(name=name, status=status, message=message))

    @property
    def ok(self) -> bool:
        return all(check.status != "fail" for check in self.checks)


def run_doctor(options: DoctorOptions) -> DoctorReport:
    report = DoctorReport()
    _check_url(options, report)
    _check_output_dir(options, report)
    _check_article_flags(options, report)
    _check_llm_flags(options, report)
    _check_doctor_flags(options, report)
    _check_log_level(options, report)
    _check_provider(options, report)
    _check_calibre(options, report)
    return report


def _check_url(options: DoctorOptions, report: DoctorReport) -> None:
    if not options.url:
        report.add("url", "fail", "URL is required")
        return
    parsed = urlparse(options.url)
    if parsed.scheme not in {"http", "https", "file"}:
        report.add("url", "fail", f"Unsupported URL scheme: {parsed.scheme or '<missing>'}")
        return
    if parsed.scheme == "file" and not Path(parsed.path).exists():
        report.add("url", "fail", f"File URL does not exist: {parsed.path}")
        return
    if parsed.scheme in {"http", "https"} and not parsed.netloc:
        report.add("url", "fail", "HTTP URL is missing a host")
        return
    report.add("url", "ok", redact_secrets(options.url))


def _check_output_dir(options: DoctorOptions, report: DoctorReport) -> None:
    path = options.output_dir
    if path.exists() and not path.is_dir():
        report.add("output", "fail", f"Output path exists but is not a directory: {path}")
        return
    target = path if path.exists() else path.parent
    if not target.exists():
        report.add("output", "fail", f"Output parent directory does not exist: {target}")
        return
    if not os.access(target, os.W_OK):
        report.add("output", "fail", f"Output directory is not writable: {target}")
        return
    report.add("output", "ok", redact_secrets(path))


def _check_llm_flags(options: DoctorOptions, report: DoctorReport) -> None:
    if options.provider_name == "none":
        report.add("model", "ok", "not used")
    else:
        report.add("model", "ok", options.model or DEFAULT_MODEL)

    if options.provider_name == "anthropic":
        report.add("web fetch tool", "ok", options.web_fetch_tool or DEFAULT_WEB_FETCH_TOOL)
    elif options.web_fetch_tool:
        report.add("web fetch tool", "warn", "provided but not used without Anthropic provider")
    else:
        report.add("web fetch tool", "ok", "not used")

    if options.llm_timeout is not None and options.llm_timeout <= 0:
        report.add("llm timeout", "fail", "--llm-timeout must be greater than 0")
    else:
        report.add("llm timeout", "ok", str(options.llm_timeout or "provider default"))

    if options.llm_retries is not None and options.llm_retries < 0:
        report.add("llm retries", "fail", "--llm-retries must be 0 or greater")
    else:
        report.add("llm retries", "ok", str(options.llm_retries if options.llm_retries is not None else "provider default"))

    if options.llm_max_tokens is not None and options.llm_max_tokens <= 0:
        report.add("llm max tokens", "fail", "--llm-max-tokens must be greater than 0")
    else:
        report.add("llm max tokens", "ok", str(options.llm_max_tokens or "provider default"))

    if options.fetch_mode == "llm" and options.provider_name == "none":
        report.add("fetch mode", "fail", "--fetch-mode llm requires an LLM provider")
    else:
        report.add("fetch mode", "ok", options.fetch_mode)


def _check_article_flags(options: DoctorOptions, report: DoctorReport) -> None:
    report.add("title", "ok", redact_secrets(options.title) if options.title else "not overridden")
    if options.strict and options.fetch_mode == "llm":
        report.add("strict", "warn", "enabled, but sentence validation is strongest with local fetch")
    else:
        report.add("strict", "ok", "enabled" if options.strict else "disabled")
    report.add("store metadata", "ok", "enabled" if options.store_metadata else "disabled")


def _check_doctor_flags(options: DoctorOptions, report: DoctorReport) -> None:
    report.add("doctor", "ok", "enabled" if options.doctor_enabled else "standalone command")
    if options.doctor_timeout <= 0:
        report.add("doctor timeout", "fail", "--doctor-timeout must be greater than 0")
    else:
        report.add("doctor timeout", "ok", f"{options.doctor_timeout}s")


def _check_provider(options: DoctorOptions, report: DoctorReport) -> None:
    if options.provider_name == "none":
        report.add("provider", "ok", "none")
        report.add("api key", "ok", "not required")
        return
    if options.provider_name != "anthropic":
        report.add("provider", "fail", f"Unsupported provider: {options.provider_name}")
        return

    report.add("provider", "ok", "anthropic")
    key = options.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        report.add("api key", "fail", "Anthropic provider requires --api-key or ANTHROPIC_API_KEY")
        return

    provider = AnthropicProvider(
        api_key=key,
        model=options.model or DEFAULT_MODEL,
        max_tokens=8,
        timeout=options.doctor_timeout,
        retries=0,
        web_fetch_tool=options.web_fetch_tool or DEFAULT_WEB_FETCH_TOOL,
    )
    try:
        provider.check_connection()
    except AnthropicError as exc:
        report.add("api key", "fail", f"Anthropic API check failed: {exc}")
        return
    report.add("api key", "ok", f"Anthropic API accepted key/model within {options.doctor_timeout}s")


def _check_log_level(options: DoctorOptions, report: DoctorReport) -> None:
    allowed = {"quiet", "error", "warning", "info", "debug"}
    effective = options.log_level or "info"
    if effective not in allowed:
        report.add("log level", "fail", f"Unsupported log level: {effective}")
        return
    report.add("log level", "ok", effective)


def _check_calibre(options: DoctorOptions, report: DoctorReport) -> None:
    report.add("calibre url", "ok", redact_secrets(options.calibre_url) if options.calibre_url else "not set")
    report.add("calibre username", "ok", "provided" if options.calibre_username else "not set")
    report.add("calibre password", "ok", "provided" if options.calibre_password else "not set")
    report.add("calibre api key", "ok", "provided" if options.calibre_api_key else "not set")

    provided = [
        options.calibre_url,
        options.calibre_username,
        options.calibre_password,
        options.calibre_api_key,
    ]
    if not any(provided):
        report.add("calibre", "ok", "not configured")
        return
    if not options.calibre_url:
        report.add("calibre", "fail", "Calibre credentials were provided without --calibre-url")
        return
    parsed = urlparse(options.calibre_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        report.add("calibre", "fail", "--calibre-url must be an http(s) URL with a host")
        return
    if bool(options.calibre_username) != bool(options.calibre_password):
        report.add("calibre", "fail", "--calibre-username and --calibre-password must be provided together")
        return
    report.add("calibre", "ok", redact_secrets(options.calibre_url))
