from unittest import TestCase
from unittest.mock import patch

from articlepub.cli_support import make_provider
from articlepub.llm.anthropic import AnthropicProvider


class CliSupportTest(TestCase):
    def test_make_provider_forwards_anthropic_tuning(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}):
            provider = make_provider(
                "anthropic",
                timeout=600,
                retries=3,
                max_tokens=12000,
            )

        self.assertIsInstance(provider, AnthropicProvider)
        self.assertEqual(provider.timeout, 600)
        self.assertEqual(provider.retries, 3)
        self.assertEqual(provider.max_tokens, 12000)
