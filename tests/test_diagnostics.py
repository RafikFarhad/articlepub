from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from articlepub.diagnostics import DoctorOptions, run_doctor


class DiagnosticsTest(TestCase):
    def test_fetch_mode_llm_requires_provider(self) -> None:
        with TemporaryDirectory() as tmp:
            report = run_doctor(
                DoctorOptions(
                    url="https://example.com/post",
                    output_dir=Path(tmp),
                    fetch_mode="llm",
                    provider_name="none",
                )
            )

        failures = [check for check in report.checks if check.status == "fail"]
        self.assertFalse(report.ok)
        self.assertIn("--fetch-mode llm requires an LLM provider", [check.message for check in failures])

    def test_live_anthropic_check_uses_doctor_timeout(self) -> None:
        seen = {}

        def fake_check(self):
            seen["timeout"] = self.timeout
            seen["retries"] = self.retries
            seen["max_tokens"] = self.max_tokens

        with TemporaryDirectory() as tmp, patch("articlepub.diagnostics.AnthropicProvider.check_connection", fake_check):
            report = run_doctor(
                DoctorOptions(
                    url="https://example.com/post",
                    output_dir=Path(tmp),
                    fetch_mode="auto",
                    provider_name="anthropic",
                    api_key="test-key",
                    doctor_timeout=6,
                    llm_timeout=600,
                    log_level="debug",
                    store_metadata=True,
                )
            )

        self.assertTrue(report.ok)
        self.assertEqual(seen, {"timeout": 6, "retries": 0, "max_tokens": 8})
        self.assertIn(("log level", "debug"), [(check.name, check.message) for check in report.checks])
        self.assertIn(("model", "claude-sonnet-4-6"), [(check.name, check.message) for check in report.checks])
        self.assertIn(("doctor timeout", "6s"), [(check.name, check.message) for check in report.checks])
        self.assertIn(("store metadata", "enabled"), [(check.name, check.message) for check in report.checks])

    def test_invalid_log_level_is_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            report = run_doctor(
                DoctorOptions(
                    url="https://example.com/post",
                    output_dir=Path(tmp),
                    fetch_mode="auto",
                    provider_name="none",
                    log_level="verbose",
                )
            )

        self.assertFalse(report.ok)
        self.assertIn("Unsupported log level: verbose", [check.message for check in report.checks])
