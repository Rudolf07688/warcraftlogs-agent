"""Browser-controlled telemetry context (feature 057): one validation for every entry point.

The browser sends a W3C ``traceparent`` and the Faro session id, in headers on REST calls and
in the message on the chat socket (a browser WebSocket cannot set headers). Both are attacker
controlled, so nothing here raises or stores an unbounded value: an unusable value is dropped
and the request or turn runs as before, with a fresh root trace and no ``session.id``.

``session.id`` is a span attribute only (spec §9.3): it is never a metric label.
"""

from __future__ import annotations

import re

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp, Receive, Scope, Send

# A version-00 traceparent is exactly 55 characters; the cap leaves room for later versions.
MAX_TRACEPARENT_LENGTH = 128
# Faro session ids are about ten alphanumerics.
_SESSION_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")
SESSION_ID_HEADER = b"x-faro-session-id"

_propagator = TraceContextTextMapPropagator()


def parent_context(traceparent: object) -> Context | None:
    """The browser's span as a parent context, or ``None`` for anything unusable: not a
    string, too long, malformed (the OTel propagator decides), an all-zero id, or unsampled
    (the backend takes its own sampling decision rather than inherit the browser's)."""
    if not isinstance(traceparent, str) or len(traceparent) > MAX_TRACEPARENT_LENGTH:
        return None
    context = _propagator.extract({"traceparent": traceparent})
    span_context = trace.get_current_span(context).get_span_context()
    if not span_context.is_valid or not span_context.trace_flags.sampled:
        return None
    return context


def session_id(value: object) -> str | None:
    """``value`` when it is a short token of safe characters, else ``None``."""
    if isinstance(value, str) and _SESSION_ID.fullmatch(value):
        return value
    return None


def tag_current_span(value: object) -> None:
    """Set ``session.id`` on the current span when ``value`` is usable (no-op when off)."""
    valid = session_id(value)
    span = trace.get_current_span()
    if valid is not None and span.is_recording():
        span.set_attribute("session.id", valid)


class FaroSessionMiddleware:
    """Pure ASGI: copy ``x-faro-session-id`` to ``session.id`` on the server span.

    Registered inside the FastAPI instrumentation, whose server span is current here; without
    telemetry there is no recording span and this does nothing.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            for name, value in scope["headers"]:
                if name == SESSION_ID_HEADER:
                    tag_current_span(value.decode("latin-1"))
                    break
        await self.app(scope, receive, send)
