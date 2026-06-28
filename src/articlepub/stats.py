from __future__ import annotations

import inspect
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator


LogFn = Callable[..., None]


@dataclass(slots=True)
class StepTiming:
    name: str
    duration_s: float
    status: str = "ok"
    detail: str | None = None


@dataclass(slots=True)
class LLMUsage:
    provider: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    extra: dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


@dataclass(slots=True)
class BuildStats:
    started_at: float = field(default_factory=time.perf_counter)
    finished_at: float | None = None
    steps: list[StepTiming] = field(default_factory=list)
    llm_usage: list[LLMUsage] = field(default_factory=list)
    heartbeat_interval_s: float = 1.0

    @contextmanager
    def step(self, name: str, detail: str | None = None, log: LogFn | None = None) -> Iterator[None]:
        started = time.perf_counter()
        heartbeat_stop: threading.Event | None = None
        heartbeat_thread: threading.Thread | None = None
        if log:
            suffix = f" ({detail})" if detail else ""
            log(f"start: {name}{suffix}", elapsed_s=0.0)
            heartbeat_stop = threading.Event()
            heartbeat_thread = threading.Thread(
                target=_heartbeat,
                args=(name, started, self.heartbeat_interval_s, heartbeat_stop, log),
                daemon=True,
            )
            heartbeat_thread.start()
        status = "ok"
        final_detail = detail
        try:
            yield
        except Exception as exc:
            status = "failed"
            final_detail = str(exc)
            raise
        finally:
            if heartbeat_stop:
                heartbeat_stop.set()
            if heartbeat_thread:
                heartbeat_thread.join(timeout=0.2)
            duration = time.perf_counter() - started
            self.steps.append(StepTiming(name=name, duration_s=duration, status=status, detail=final_detail))
            if log:
                log(f"{status}: {name}", elapsed_s=duration)

    def add_llm_usage(self, usage: LLMUsage | None) -> None:
        if usage:
            self.llm_usage.append(usage)

    def finish(self) -> None:
        self.finished_at = time.perf_counter()

    @property
    def total_seconds(self) -> float:
        finished = self.finished_at or time.perf_counter()
        return finished - self.started_at

    @property
    def total_llm_usage(self) -> LLMUsage:
        total = LLMUsage(provider="total")
        for usage in self.llm_usage:
            total.input_tokens += usage.input_tokens
            total.output_tokens += usage.output_tokens
            total.cache_creation_input_tokens += usage.cache_creation_input_tokens
            total.cache_read_input_tokens += usage.cache_read_input_tokens
            for key, value in usage.extra.items():
                total.extra[key] = total.extra.get(key, 0) + value
        return total


def _heartbeat(
    name: str,
    started: float,
    interval_s: float,
    stop: threading.Event,
    log: LogFn,
) -> None:
    interval = max(interval_s, 0.1)
    while not stop.wait(interval):
        _log(log, f"running: {name}", elapsed_s=time.perf_counter() - started, transient=True)


def _log(log: LogFn, message: str, elapsed_s: float, transient: bool = False) -> None:
    if transient and _accepts_keyword(log, "transient"):
        log(message, elapsed_s=elapsed_s, transient=True)
        return
    log(message, elapsed_s=elapsed_s)


def _accepts_keyword(log: LogFn, keyword: str) -> bool:
    try:
        signature = inspect.signature(log)
    except (TypeError, ValueError):
        return True
    return keyword in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
    )
