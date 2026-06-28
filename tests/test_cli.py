import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from articlepub.cli import main


FIXTURE = Path(__file__).parent / "fixtures" / "blog.html"


class CliTest(TestCase):
    def test_add_local_file_without_provider(self) -> None:
        with TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["add", FIXTURE.as_uri(), "--provider", "none", "--fetch-mode", "local", "--out", tmp])

            self.assertEqual(code, 0)
            epub_path = Path(stdout.getvalue().strip())
            self.assertTrue(epub_path.exists())
            self.assertEqual(epub_path.parent, Path(tmp))

    def test_debug_log_level_reports_steps_to_stderr(self) -> None:
        with TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(
                    [
                        "add",
                        FIXTURE.as_uri(),
                        "--provider",
                        "none",
                        "--fetch-mode",
                        "local",
                        "--out",
                        tmp,
                        "--log-level",
                        "debug",
                    ]
                )

            self.assertEqual(code, 0)
            self.assertTrue(Path(stdout.getvalue().strip()).exists())
            status = stderr.getvalue()
            self.assertIn("DEBUG     0ms start: local fetch", status)
            self.assertIn("Run summary", status)
            self.assertIn("Step timing", status)
            self.assertIn("LLM usage", status)

    def test_add_doctor_with_provider_none_checks_flags_without_building(self) -> None:
        with TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(
                    [
                        "add",
                        FIXTURE.as_uri(),
                        "--provider",
                        "none",
                        "--fetch-mode",
                        "local",
                        "--out",
                        tmp,
                        "--doctor",
                        "--log-level",
                        "debug",
                    ]
                )

            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "")
            status = stderr.getvalue()
            self.assertIn("Doctor report", status)
            self.assertIn("OK    log level: debug", status)
            self.assertIn("OK    api key: not required", status)
            self.assertFalse(list(Path(tmp).glob("*.epub")))

    def test_doctor_fails_fast_when_anthropic_key_missing(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["doctor", FIXTURE.as_uri(), "--provider", "anthropic"])

        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Anthropic provider requires --api-key or ANTHROPIC_API_KEY", stderr.getvalue())

    def test_doctor_runs_live_api_check_when_key_is_present(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("articlepub.diagnostics.AnthropicProvider.check_connection"), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                [
                    "doctor",
                    FIXTURE.as_uri(),
                    "--provider",
                    "anthropic",
                    "--api-key",
                    "test-key",
                ]
            )

        self.assertEqual(code, 0)
        self.assertIn("OK    api key: Anthropic API accepted key/model within 10s", stderr.getvalue())

    def test_add_doctor_reports_every_add_flag(self) -> None:
        with TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                with patch("articlepub.diagnostics.AnthropicProvider.check_connection"):
                    code = main(
                        [
                            "add",
                            FIXTURE.as_uri(),
                            "--out",
                            tmp,
                            "--fetch-mode",
                            "auto",
                            "--provider",
                            "anthropic",
                            "--api-key",
                            "test-key",
                            "--model",
                            "custom-model",
                            "--web-fetch-tool",
                            "custom-web-fetch",
                            "--llm-timeout",
                            "11",
                            "--llm-retries",
                            "2",
                            "--llm-max-tokens",
                            "123",
                            "--doctor-timeout",
                            "4",
                        "--strict",
                        "--title",
                        "Custom Title",
                        "--store-metadata",
                        "--log-level",
                        "debug",
                            "--calibre-url",
                            "https://calibre.example.com",
                            "--calibre-username",
                            "user",
                            "--calibre-password",
                            "pass",
                            "--calibre-api-key",
                            "calibre-key",
                            "--doctor",
                        ]
                    )

            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "")
            status = stderr.getvalue()
            expected = [
                "OK    url:",
                f"OK    output: {tmp}",
                "OK    title: Custom Title",
                "OK    strict: enabled",
                "OK    store metadata: enabled",
                "OK    model: custom-model",
                "OK    web fetch tool: custom-web-fetch",
                "OK    llm timeout: 11",
                "OK    llm retries: 2",
                "OK    llm max tokens: 123",
                "OK    fetch mode: auto",
                "OK    doctor: enabled",
                "OK    doctor timeout: 4s",
                "OK    log level: debug",
                "OK    provider: anthropic",
                "OK    api key: Anthropic API accepted key/model within 4s",
                "OK    calibre url: https://calibre.example.com",
                "OK    calibre username: provided",
                "OK    calibre password: provided",
                "OK    calibre api key: provided",
                "OK    calibre: https://calibre.example.com",
            ]
            for line in expected:
                self.assertIn(line, status)

    def test_doctor_redacts_passwords_tokens_and_secret_url_parts(self) -> None:
        secret_url = "https://user:url-pass@example.com/post?access_token=url-token&ok=1"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("articlepub.diagnostics.AnthropicProvider.check_connection"), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                [
                    "doctor",
                    secret_url,
                    "--provider",
                    "anthropic",
                    "--api-key",
                    "anthropic-secret",
                    "--calibre-url",
                    "https://admin:calibre-url-pass@calibre.example.com?api_key=calibre-url-token",
                    "--calibre-username",
                    "calibre-user",
                    "--calibre-password",
                    "calibre-password-secret",
                    "--calibre-api-key",
                    "calibre-api-secret",
                ]
            )

        self.assertEqual(code, 0)
        output = stderr.getvalue()
        leaked = [
            "url-pass",
            "url-token",
            "anthropic-secret",
            "calibre-url-pass",
            "calibre-url-token",
            "calibre-password-secret",
            "calibre-api-secret",
        ]
        for secret in leaked:
            self.assertNotIn(secret, output)
        self.assertIn("[REDACTED]", output)
        self.assertIn("OK    calibre password: provided", output)
        self.assertIn("OK    calibre api key: provided", output)

    def test_debug_log_redacts_secret_url_query(self) -> None:
        secret_url = FIXTURE.as_uri() + "?token=file-token-secret&ok=1"
        with TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(
                    [
                        "add",
                        secret_url,
                        "--provider",
                        "none",
                        "--fetch-mode",
                        "local",
                        "--out",
                        tmp,
                        "--log-level",
                        "debug",
                    ]
                )

            self.assertEqual(code, 0)
            output = stderr.getvalue()
            self.assertNotIn("file-token-secret", output)
            self.assertIn("token=[REDACTED]", output)
