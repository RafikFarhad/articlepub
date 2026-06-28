from unittest import TestCase

from articlepub.redaction import redact_secrets


class RedactionTest(TestCase):
    def test_redacts_secret_query_params_and_url_userinfo(self) -> None:
        text = "fetch https://user:pass@example.com/post?token=abc123&ok=1&api_key=key-secret"

        redacted = redact_secrets(text)

        self.assertNotIn("user:pass", redacted)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("key-secret", redacted)
        self.assertIn("https://redacted@example.com/post?token=[REDACTED]&ok=1&api_key=[REDACTED]", redacted)

    def test_redacts_key_value_and_bearer_tokens(self) -> None:
        text = "api_key=abc123 Authorization: Bearer bearer-secret password: pass-secret"

        redacted = redact_secrets(text)

        self.assertNotIn("abc123", redacted)
        self.assertNotIn("bearer-secret", redacted)
        self.assertNotIn("pass-secret", redacted)
        self.assertIn("api_key=[REDACTED]", redacted)
        self.assertIn("Bearer [REDACTED]", redacted)
        self.assertIn("password: [REDACTED]", redacted)

    def test_keeps_safe_status_values_visible(self) -> None:
        text = "api key: present calibre password: provided token: not"

        redacted = redact_secrets(text)

        self.assertEqual(redacted, text)
