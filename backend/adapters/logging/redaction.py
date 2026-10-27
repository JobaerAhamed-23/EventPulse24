"""What may reach a log sink (AD-13): an allowlist of fields, and pattern scrubbing of values.

Patterns can't recognise free text (a personal event title). That is why project loggers never
interpolate their args and exception messages are never logged; see formatter.py.
"""

import re
from typing import Any

REDACTED = "[redacted]"
EMAIL = "[email]"
TOKEN = "[token]"  # noqa: S105 - a redaction marker, not a secret

# Ids, counts, durations, slugs. Never put free text in one of these.
ALLOWED_FIELDS = frozenset(
    {
        "event_id",
        "source_id",
        "user_id",
        "state_change_id",
        "send_id",
        "idempotency_key",
        "count",
        "duration_ms",
        "attempt",
        "model",
        "input_tokens",
        "output_tokens",
        "cost_micros",
        "stream",
        "slot",
        "status_code",
        "method",
        "error_code",
        "error_type",
        "job",
    }
)

# Order matters: URL credentials before the email pattern, which would match "pass@host".
_TOKEN_PATTERNS = [
    # The user part may be empty: managed Redis URLs are often redis://:password@host.
    (re.compile(r"(?<=://)[^/\s:@]*:[^/\s@]+(?=@)"), TOKEN),
    (re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"), TOKEN),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), TOKEN),
    # Word boundary + minimum body, so `network_check`, `work_item`, `task-…` are untouched.
    (
        re.compile(r"\b(?:sk-ant|sk_live|sk_test|rk_live|rk_test|sk|rk|ghp|whsec)[-_][\w-]{16,}"),
        TOKEN,
    ),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{16,}"), TOKEN),
    (re.compile(r"(?i)\bwebcals?://\S+"), TOKEN),
    (re.compile(r"private-[A-Za-z0-9]{8,}"), TOKEN),
    (
        re.compile(
            r"(?i)\b(token|access_token|refresh_token|api_key|apikey|key|secret|password|"
            r"passwd|signature|sig)=[^&\s#]+"
        ),
        r"\1=" + TOKEN,
    ),
    (re.compile(r"[A-Za-z0-9._%+-]+(?:@|%40)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), EMAIL),
    # Opaque secrets. Ids stay below 40: a dashed UUID is 36, a hex UUID or trace id is 32,
    # and send keys are ":"-separated (shared.constants.SEND_KEY_SEPARATOR).
    (re.compile(r"[A-Za-z0-9_-]{40,}"), TOKEN),
]


def scrub(text: str) -> str:
    for pattern, replacement in _TOKEN_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def scrub_value(value: Any) -> Any:
    """Scrub strings anywhere in `value`; anything not JSON-native becomes a scrubbed string."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {str(key): scrub_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [scrub_value(item) for item in value]
    return scrub(str(value))
