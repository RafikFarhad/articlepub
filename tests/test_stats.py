import time
from unittest import TestCase

from articlepub.stats import BuildStats


class BuildStatsTest(TestCase):
    def test_step_logs_transient_heartbeat_while_running(self) -> None:
        logs: list[tuple[str, float | None, bool]] = []
        stats = BuildStats(heartbeat_interval_s=0.1)

        def log(message: str, elapsed_s: float | None = None, transient: bool = False) -> None:
            logs.append((message, elapsed_s, transient))

        with stats.step("slow llm step", log=log):
            time.sleep(0.13)

        messages = [message for message, _, _ in logs]
        self.assertEqual(messages[0], "start: slow llm step")
        self.assertIn("running: slow llm step", messages)
        self.assertEqual(messages[-1], "ok: slow llm step")

        heartbeat_elapsed = [elapsed_s for message, elapsed_s, _ in logs if message == "running: slow llm step"]
        heartbeat_transient = [transient for message, _, transient in logs if message == "running: slow llm step"]
        self.assertTrue(heartbeat_elapsed)
        self.assertGreaterEqual(heartbeat_elapsed[0] or 0, 0.1)
        self.assertEqual(heartbeat_transient, [True])
        self.assertFalse(logs[-1][2])

    def test_step_heartbeat_supports_log_callback_without_transient_keyword(self) -> None:
        logs: list[tuple[str, float | None]] = []
        stats = BuildStats(heartbeat_interval_s=0.1)

        with stats.step("slow llm step", log=lambda message, elapsed_s=None: logs.append((message, elapsed_s))):
            time.sleep(0.13)

        messages = [message for message, _ in logs]
        self.assertIn("running: slow llm step", messages)
        self.assertEqual(messages[-1], "ok: slow llm step")
