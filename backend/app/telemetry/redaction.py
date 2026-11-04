"""App-side redaction of exported telemetry (feature 054, spec §6.1 and §10).

The span and log exporters are wrapped, so this runs in the SDK's export thread, never on the
event loop, and sees every record, ADK's own log events included. It always masks secrets: the
string value of a sensitive attribute key, and secret-shaped text anywhere (bearer tokens,
credentials in URLs, sensitive query parameters and ``key: value`` pairs, known API key and
JWT shapes). Outside dev it also removes content attributes and drops content events.
Defense in depth before Alloy's own redaction (053).
"""

from __future__ import annotations

import base64
import copy
import dataclasses
import re
from collections.abc import Mapping, Sequence
from typing import Any

from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk._logs.export import LogRecordExporter, LogRecordExportResult
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Link, Status

from ..auth.redaction import _SENSITIVE_KEY, REDACTED, is_sensitive_key
from .policy import CONTENT_EVENT_PREFIX, CONTENT_FLAG, is_content_attribute

# Key names the logging rule (auth.redaction) doesn't cover but telemetry must: the WCL client
# secret, API keys, DSNs. Composed with that rule, never instead of it.
_EXTRA_KEY_WORDS = r"secret|api[_-]?key|apikey|private[_-]?key|dsn|credential"
_EXTRA_SENSITIVE_KEY = re.compile(_EXTRA_KEY_WORDS, re.IGNORECASE)
_KEY = rf"[\w.-]*(?:{_SENSITIVE_KEY.pattern}|{_EXTRA_KEY_WORDS})[\w.-]*"
_PARAM = r"(?:password|passwd|[\w-]*token|api[_-]?key|apikey|key|[\w-]*secret|code|sig|signature|auth)"
_SECRET_TEXT = re.compile(
    "|".join(
        (
            # Authorization header values (Basic only when it decodes to user:password).
            r"(?P<scheme>(?-i:\bBearer)\s+)[A-Za-z0-9._~+/=-]{6,}",
            r"(?P<basic>(?-i:\bBasic)\s+)(?P<b64>[A-Za-z0-9+/]{8,}={0,2})",
            # user:password@ in any URL or DSN.
            r"(?P<url>\b[a-z][a-z0-9+.-]*://)[^\s/:@]+:[^\s/@]+@",
            # ?token=..., &key=..., ;sig=...
            rf"(?P<param>[?&;]{_PARAM}=)[^&\s#\"'\\]+",
            # "client_secret": "...", token='...', Cookie: ..., password=..., also inside
            # JSON that was encoded twice (\"token\": \"...\").
            rf"(?P<pair>\\?[\"']?{_KEY}\\?[\"']?\s*[:=]\s*)"
            r"(?P<value>(?:Bearer|Basic|Digest|Token)\s+[^\s,;\"'\\]+|\\\"(?:[^\\]|\\(?!\"))*\\\"|\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|[^\s,;&}\]\"'\\]+)",
            # Known key shapes: Anthropic/OpenAI-style, Google API keys and OAuth tokens, JWTs.
            r"\bsk-[A-Za-z0-9_-]{16,}",
            r"\bAIza[0-9A-Za-z_-]{30,}",
            r"\bya29\.[0-9A-Za-z._-]{10,}",
            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
        )
    ),
    re.IGNORECASE,
)
_NUMBER = re.compile(r"[\"']?-?\d+(?:\.\d+)?[\"']?")
_MAX_DEPTH = 8


def _basic_credentials(b64: str) -> bool:
    try:
        return ":" in base64.b64decode(b64, validate=True).decode()
    except ValueError:  # binascii.Error and UnicodeDecodeError are ValueErrors
        return False


def _replace(match: re.Match[str]) -> str:
    if match.group("basic") and not _basic_credentials(match.group("b64")):
        return match.group(0)  # "Basic strategy" is English
    for prefix in ("scheme", "basic", "url", "param"):
        if match.group(prefix):
            return match.group(prefix) + REDACTED + ("@" if prefix == "url" else "")
    if match.group("pair"):
        value = match.group("value")
        if _NUMBER.fullmatch(value):  # "input_tokens": 12 is a count, not a secret
            return match.group(0)
        return match.group("pair") + REDACTED
    return REDACTED


def scrub_text(text: str) -> str:
    """``text`` with every secret-shaped part replaced by the redaction marker."""
    return _SECRET_TEXT.sub(_replace, text)


def _is_secret_key(key: str) -> bool:
    return is_sensitive_key(key) or bool(_EXTRA_SENSITIVE_KEY.search(key))


def _has_text(value: Any) -> bool:
    if isinstance(value, str):
        return True
    if isinstance(value, Mapping):
        return True
    if isinstance(value, (list, tuple)):
        return any(_has_text(v) for v in value)
    return False


def scrub_value(value: Any, depth: int = 0) -> Any:
    """A copy of an attribute value or log body with secrets masked (maps by key as well)."""
    if isinstance(value, str):
        return scrub_text(value)
    if depth >= _MAX_DEPTH:
        return REDACTED if _has_text(value) else value
    if isinstance(value, bytes):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            k: (REDACTED if _is_secret_key(str(k)) and _has_text(v) else scrub_value(v, depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(scrub_value(v, depth + 1) for v in value)
    return value


def clean_attributes(attributes: Mapping[str, Any] | None, *, content_allowed: bool) -> dict[str, Any]:
    """Attributes ready to export: content keys dropped outside dev, secrets masked.

    Only text is masked under a sensitive key: ``gen_ai.usage.input_tokens`` is a number.
    """
    cleaned: dict[str, Any] = {}
    for key, value in (attributes or {}).items():
        if not content_allowed and is_content_attribute(key):
            continue
        cleaned[key] = REDACTED if _is_secret_key(key) and _has_text(value) else scrub_value(value)
    return cleaned


def redact_span(span: ReadableSpan, *, content_allowed: bool) -> ReadableSpan:
    """A copy of ``span`` fit to leave the process."""
    events = [
        Event(
            scrub_text(event.name),
            clean_attributes(event.attributes, content_allowed=content_allowed),
            event.timestamp,
        )
        for event in span.events
        if content_allowed or not event.name.startswith(CONTENT_EVENT_PREFIX)
    ]
    links = [
        Link(link.context, clean_attributes(link.attributes, content_allowed=content_allowed))
        for link in span.links
    ]
    status = span.status
    if status.description:
        status = Status(status.status_code, scrub_text(status.description))
    return ReadableSpan(
        name=scrub_text(span.name),
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=clean_attributes(span.attributes, content_allowed=content_allowed),
        events=events,
        links=links,
        kind=span.kind,
        status=status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


def redact_log(record: ReadableLogRecord, *, content_allowed: bool) -> ReadableLogRecord | None:
    """A copy of ``record`` fit to leave the process, or ``None`` when it must not leave.

    A content record (a ``gen_ai.*`` event, or one already marked ``app.content``) is dropped
    outside dev and marked for the 7-day content stream in dev.
    """
    original = record.log_record
    attributes = original.attributes or {}
    is_content = (original.event_name or "").startswith(CONTENT_EVENT_PREFIX) or (
        attributes.get(CONTENT_FLAG) == "true"
    )
    if is_content and not content_allowed:
        return None
    log_record = copy.copy(original)
    log_record.body = scrub_value(original.body)
    cleaned = clean_attributes(attributes, content_allowed=content_allowed)
    if is_content:
        cleaned[CONTENT_FLAG] = "true"
    log_record.attributes = cleaned
    return dataclasses.replace(record, log_record=log_record)


class RedactingSpanExporter(SpanExporter):
    """Hands the inner exporter redacted copies of the spans."""

    def __init__(self, inner: SpanExporter, *, content_allowed: bool) -> None:
        self._inner = inner
        self._content_allowed = content_allowed

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export(
            [redact_span(span, content_allowed=self._content_allowed) for span in spans]
        )

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


class RedactingLogExporter(LogRecordExporter):
    """Hands the inner exporter redacted copies of the log records, minus forbidden content."""

    def __init__(self, inner: LogRecordExporter, *, content_allowed: bool) -> None:
        self._inner = inner
        self._content_allowed = content_allowed

    def export(self, batch: Sequence[ReadableLogRecord]) -> LogRecordExportResult:
        kept = [
            redacted
            for record in batch
            if (redacted := redact_log(record, content_allowed=self._content_allowed)) is not None
        ]
        if not kept:
            return LogRecordExportResult.SUCCESS
        return self._inner.export(kept)

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)
