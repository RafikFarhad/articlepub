import io
import time
from pathlib import Path
from unittest import TestCase

from articlepub.cli_ui import TerminalUI
from articlepub.models import Article, BuildResult
from articlepub.stats import BuildStats, LLMUsage, StepTiming


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class CliUiTest(TestCase):
    def test_success_uses_color_and_ascii_face_when_enabled(self) -> None:
        stream = TtyBuffer()
        ui = TerminalUI(stream=stream, enabled=True)

        ui.success("Done")

        output = stream.getvalue()
        self.assertIn("\033[32m", output)
        self.assertIn("OK", output)
        self.assertIn(":-)", output)

    def test_debug_uses_explicit_label_and_front_loaded_time(self) -> None:
        stream = io.StringIO()
        ui = TerminalUI(stream=stream, enabled=False, log_level="debug", force_plain=True)

        ui.debug("start: fetch", elapsed_s=1.25)

        self.assertEqual(stream.getvalue(), "DEBUG   1.25s start: fetch\n")

    def test_debug_transient_status_redraws_until_final_line(self) -> None:
        stream = TtyBuffer()
        ui = TerminalUI(stream=stream, enabled=True, log_level="debug")

        ui.debug("running: llm refine article", elapsed_s=75.06, transient=True)
        transient_output = stream.getvalue()
        ui.debug("ok: llm refine article", elapsed_s=80.12)

        self.assertIn("\r\033[K", transient_output)
        self.assertNotIn("\n", transient_output)
        output = stream.getvalue()
        self.assertIn("running: llm refine article", output)
        self.assertIn("\r\033[K", output)
        self.assertTrue(output.endswith("ok: llm refine article\n"))

    def test_debug_transient_status_is_quiet_without_tty(self) -> None:
        stream = io.StringIO()
        ui = TerminalUI(stream=stream, enabled=False, log_level="debug", force_plain=True)

        ui.debug("running: llm refine article", elapsed_s=75.06, transient=True)
        ui.debug("ok: llm refine article", elapsed_s=80.12)

        self.assertEqual(stream.getvalue(), "DEBUG  80.12s ok: llm refine article\n")

    def test_disabled_ui_stays_quiet_for_status_lines(self) -> None:
        stream = io.StringIO()
        ui = TerminalUI(stream=stream, enabled=False)

        ui.banner()
        ui.info("Work")
        ui.success("Done")

        self.assertEqual(stream.getvalue(), "")

    def test_forced_plain_report_includes_timing_and_tokens(self) -> None:
        stream = io.StringIO()
        stats = BuildStats()
        stats.steps.append(StepTiming(name="write epub", duration_s=1.25))
        stats.llm_usage.append(
            LLMUsage(
                provider="anthropic",
                model="fake",
                input_tokens=10,
                output_tokens=20,
                extra={"server_tool_use.web_fetch_requests": 1},
            )
        )
        stats.finish()
        result = BuildResult(
            article=Article(
                title="Title",
                html="<article><p>Body.</p></article>",
                text="Body.",
                source_url="https://example.com",
            ),
            epub_path=Path(__file__),
            stats=stats,
        )
        ui = TerminalUI(stream=stream, enabled=False, log_level="info", force_plain=True)

        ui.report(result)

        output = stream.getvalue()
        self.assertIn("INFO  Run summary", output)
        self.assertIn("OK      1.25s write epub", output)
        self.assertIn("INFO  anthropic/fake input=10 output=20", output)
        self.assertIn("server_tool_use.web_fetch_requests=1", output)

    def test_spinner_displays_elapsed_time(self) -> None:
        stream = TtyBuffer()
        ui = TerminalUI(stream=stream, enabled=True)

        with ui.spinner("Working", "Done"):
            time.sleep(0.01)

        output = stream.getvalue()
        self.assertIn("Working (", output)
        self.assertIn("Done (", output)
