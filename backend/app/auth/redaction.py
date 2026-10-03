"""Log/trace redaction (feature 006, FR-030).

A shared helper that strips the *values* of sensitive keys from structured data before
it reaches logs, APM, or error payloads. Keys matching ``password|token|authorization|
cookie|set-cookie|csrf`` (case-insensitive, substring) have their values replaced. The
logging wiring (T064) installs the ``RedactionFilter``; this module is the single source
of the rule so nothing redacts inconsistently.
"""

from __future__ import annotations

import logging
import re
from typing import Any

_SENSITIVE_KEY = re.compile(r"password|token|authorization|cookie|set-cookie|csrf", re.IGNORECASE)
REDACTED = "«redacted»"

_MAX_DEPTH = 6


def is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY.search(key))


def redact(value: Any, _depth: int = 0) -> Any:
    """Return a copy of ``value`` with sensitive dict values replaced by ``REDACTED``.

    Recurses into dicts and lists/tuples up to a bounded depth (defensive against
    cycles / pathological nesting). Non-container values pass through unchanged.
    """
    if _depth >= _MAX_DEPTH:
        return value
    if isinstance(value, dict):
        return {
            k: (REDACTED if isinstance(k, str) and is_sensitive_key(k) else redact(v, _depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(redact(v, _depth + 1) for v in value)
    return value


class RedactionFilter(logging.Filter):
    """Logging filter that redacts sensitive keys in a record's ``args`` and ``extra``.

    Scalar messages are left intact (they shouldn't carry secrets by construction); the
    filter targets structured ``extra`` dicts and dict-shaped ``args``.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        if isinstance(record.args, dict):
            record.args = redact(record.args)
        for key, val in list(vars(record).items()):
            if isinstance(key, str) and is_sensitive_key(key):
                setattr(record, key, REDACTED)
            elif isinstance(val, dict):
                setattr(record, key, redact(val))
        return True
