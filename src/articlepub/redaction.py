from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REDACTED = "[REDACTED]"
URL_USERINFO_REDACTED = "redacted"
SECRET_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "password",
    "passwd",
    "pass",
    "secret",
    "client_secret",
    "signature",
    "sig",
    "auth",
    "authorization",
}
SAFE_STATUS_VALUES = {
    "%5bredacted%5d",
    "[redacted]",
    "bearer",
    "disabled",
    "enabled",
    "not",
    "none",
    "present",
    "provided",
    "required",
    "set",
}
URL_RE = re.compile(r"\b(?:https?|file)://[^\s<>'\"]+")
BEARER_RE = re.compile(r"(?i)\b(authorization\s*[:=]\s*bearer\s+)[^\s,;]+")
KEY_VALUE_RE = re.compile(
    r"(?i)\b("
    r"api[-_]?key|access[-_]?token|refresh[-_]?token|id[-_]?token|token|password|passwd|pass|"
    r"secret|client[-_]?secret|authorization|auth"
    r")(\s*[:=]\s*)([^\s,;&]+)"
)


def redact_secrets(value: object) -> str:
    text = str(value)
    text = URL_RE.sub(lambda match: redact_url(match.group(0)), text)
    text = BEARER_RE.sub(rf"\1{REDACTED}", text)
    text = KEY_VALUE_RE.sub(_redact_key_value, text)
    return text


def redact_url(value: str) -> str:
    split = urlsplit(value)
    netloc = split.netloc
    if "@" in split.netloc:
        hostport = split.netloc.rsplit("@", 1)[-1]
        netloc = f"{URL_USERINFO_REDACTED}@{hostport}"

    query = urlencode(
        [
            (key, REDACTED if _is_secret_key(key) else val)
            for key, val in parse_qsl(split.query, keep_blank_values=True)
        ],
        doseq=True,
    ).replace("%5BREDACTED%5D", REDACTED)
    return urlunsplit((split.scheme, netloc, split.path, query, split.fragment))


def _is_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    if normalized in SECRET_KEYS:
        return True
    return normalized.endswith("_token") or normalized.endswith("_secret") or normalized.endswith("_key")


def _redact_key_value(match: re.Match[str]) -> str:
    value = match.group(3).strip("'\"").casefold()
    if value in SAFE_STATUS_VALUES:
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}{REDACTED}"
