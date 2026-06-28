from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, TextIO

from .diagnostics import DoctorReport
from .models import BuildResult
from .redaction import redact_secrets
from .stats import BuildStats, LLMUsage


RESET = "\033[0m"
COLORS = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}
LEVELS = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
    "quiet": 50,
}


@dataclass(slots=True)
class TerminalUI:
    stream: TextIO
    enabled: bool
    log_level: str = "info"
    force_plain: bool = False
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _transient_active: bool = field(default=False, init=False, repr=False)

    @classmethod
    def auto(
        cls,
        stream: TextIO | None = None,
        log_level: str = "info",
        force_plain: bool = False,
    ) -> "TerminalUI":
        target = stream or sys.stderr
        term = os.environ.get("TERM", "")
        enabled = bool(getattr(target, "isatty", lambda: False)()) and "NO_COLOR" not in os.environ and term != "dumb"
        return cls(stream=target, enabled=enabled, log_level=log_level, force_plain=force_plain)

    def banner(self) -> None:
        if not self.enabled:
            return
        art = r"""
    _         _   _      _      ____        _
   / \   _ __| |_(_) ___| | ___|  _ \ _   _| |__
  / _ \ | '__| __| |/ __| |/ _ \ |_) | | | | '_ \
 / ___ \| |  | |_| | (__| |  __/  __/| |_| | |_) |
/_/   \_\_|   \__|_|\___|_|\___|_|    \__,_|_.__/
"""
        self.write(self.color(art.rstrip(), "cyan"))
        self.write(self.color("URL -> EPUB -> Kindle  :-)", "dim"))

    def info(self, message: str) -> None:
        if self._should_emit("info"):
            self._log_line("INFO", message, color="cyan")

    def debug(self, message: str, elapsed_s: float | None = None, transient: bool = False) -> None:
        if self._should_emit("debug"):
            self._log_line("DEBUG", message, elapsed_s=elapsed_s, color="dim", transient=transient)

    def success(self, message: str) -> None:
        if self._should_emit("info"):
            self._log_line("OK", f"{message}  :-)", color="green")

    def warning(self, message: str) -> None:
        if self._should_emit("warning"):
            self._log_line("WARN", f"{message}  :-/", color="yellow")

    def error(self, message: str) -> None:
        self._log_line("ERR", message, color="red")

    @contextmanager
    def spinner(self, message: str, done: str | None = None) -> Iterator[None]:
        if not self.enabled or not self._allows("info") or self._allows("debug"):
            yield
            return

        stop = threading.Event()
        failed = False
        started = time.perf_counter()

        def animate() -> None:
            frames = ["-", "\\", "|", "/"]
            index = 0
            while not stop.is_set():
                frame = frames[index % len(frames)]
                elapsed = _seconds(time.perf_counter() - started)
                self.stream.write(f"\r{self.color(frame, 'cyan')} {message} ({elapsed})")
                self.stream.flush()
                index += 1
                time.sleep(0.09)

        thread = threading.Thread(target=animate, daemon=True)
        thread.start()
        try:
            yield
        except Exception:
            failed = True
            raise
        finally:
            stop.set()
            thread.join(timeout=0.2)
            self.stream.write("\r\033[K")
            self.stream.flush()
            elapsed = _seconds(time.perf_counter() - started)
            if failed:
                self.error(f"{message} ({elapsed})")
            else:
                self.success(f"{done or message} ({elapsed})")

    def report(self, result: BuildResult) -> None:
        if not self._should_emit("info"):
            return
        stats = result.stats
        self.write("")
        self._log_line("INFO", "Run summary", color="cyan")
        self._log_line("INFO", f"Title: {result.article.title}", color="cyan")
        self._log_line("INFO", f"EPUB: {result.epub_path}", color="cyan")
        self._log_line("INFO", f"Total: {_seconds(stats.total_seconds)}", color="cyan")
        self._write_steps(stats)
        self._write_llm_usage(stats.llm_usage)

    def doctor_report(self, report: DoctorReport) -> None:
        if not self._should_emit("info"):
            return
        self._log_line("INFO", "Doctor report", color="cyan")
        for check in report.checks:
            if check.status == "ok":
                marker = "OK"
                color = "green"
            elif check.status == "warn":
                marker = "WARN"
                color = "yellow"
            else:
                marker = "ERR"
                color = "red"
            self._log_line(marker, f"{check.name}: {check.message}", color=color)
        if report.ok:
            self.success("Doctor checks passed")
        else:
            self.error("Doctor checks failed")

    def _write_steps(self, stats: BuildStats) -> None:
        if not stats.steps:
            return
        self.write("")
        self._log_line("INFO", "Step timing", color="cyan")
        for step in stats.steps:
            marker = "OK" if step.status == "ok" else "ERR"
            color = "green" if step.status == "ok" else "red"
            detail = f" ({step.detail})" if step.detail else ""
            self._log_line(marker, f"{step.name}{detail}", elapsed_s=step.duration_s, color=color)

    def _write_llm_usage(self, usages: list[LLMUsage]) -> None:
        self.write("")
        self._log_line("INFO", "LLM usage", color="cyan")
        if not usages:
            self._log_line("INFO", "none", color="cyan")
            return
        total = LLMUsage(provider="total")
        for usage in usages:
            total.input_tokens += usage.input_tokens
            total.output_tokens += usage.output_tokens
            total.cache_creation_input_tokens += usage.cache_creation_input_tokens
            total.cache_read_input_tokens += usage.cache_read_input_tokens
            for key, value in usage.extra.items():
                total.extra[key] = total.extra.get(key, 0) + value
            label = usage.provider
            if usage.model:
                label = f"{label}/{usage.model}"
            self._log_line(
                "INFO",
                f"{label} input={usage.input_tokens} output={usage.output_tokens} "
                + f"cache_write={usage.cache_creation_input_tokens} cache_read={usage.cache_read_input_tokens} "
                + f"total={usage.total_tokens}{_extra_usage_text(usage)}",
                color="cyan",
            )
        if len(usages) > 1:
            self._log_line(
                "INFO",
                f"total input={total.input_tokens} output={total.output_tokens} "
                + f"cache_write={total.cache_creation_input_tokens} cache_read={total.cache_read_input_tokens} "
                + f"total={total.total_tokens}{_extra_usage_text(total)}",
                color="cyan",
            )

    def color(self, message: str, color: str) -> str:
        if not self.enabled:
            return message
        return f"{COLORS[color]}{message}{RESET}"

    def write(self, message: str) -> None:
        with self._lock:
            self._clear_transient()
            self.stream.write(redact_secrets(message) + "\n")
            self.stream.flush()

    def _log_line(
        self,
        level: str,
        message: str,
        elapsed_s: float | None = None,
        color: str | None = None,
        transient: bool = False,
    ) -> None:
        if elapsed_s is None:
            prefix = f"{level:<5}"
        else:
            prefix = f"{level:<5} {_seconds(elapsed_s):>7}"
        if color:
            prefix = self.color(prefix, color)
        line = f"{prefix} {message}"
        if transient:
            self._write_transient(line)
        else:
            self.write(line)

    def _should_emit(self, level: str) -> bool:
        if not self._allows(level):
            return False
        if self.enabled or self.force_plain:
            return True
        return level in {"warning", "error"}

    def _allows(self, level: str) -> bool:
        configured = LEVELS.get(self.log_level, LEVELS["info"])
        requested = LEVELS[level]
        return requested >= configured

    def _write_transient(self, message: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            self.stream.write("\r\033[K" + redact_secrets(message))
            self.stream.flush()
            self._transient_active = True

    def _clear_transient(self) -> None:
        if self._transient_active:
            self.stream.write("\r\033[K")
            self._transient_active = False


def _seconds(value: float) -> str:
    if value < 1:
        return f"{value * 1000:.0f}ms"
    return f"{value:.2f}s"


def _extra_usage_text(usage: LLMUsage) -> str:
    if not usage.extra:
        return ""
    return " " + " ".join(f"{key}={value}" for key, value in sorted(usage.extra.items()))
