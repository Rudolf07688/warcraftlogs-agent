"""OpenTelemetry for the API process (feature 054).

``configure_telemetry()`` runs first in ``main.py``, before FastAPI and ADK are imported. It
does nothing unless ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, so the test suite and runs without
the observability stack are untouched. When on: the content policy for ``WCL_ENVIRONMENT``,
global tracer/meter/logger providers exporting to Alloy, and FastAPI, SQLAlchemy, Redis and
httpx instrumentation.

Traces: each websocket chat turn is the root of its own trace (``chat_turn_span``), with ADK's
``invoke_agent`` / ``generate_content`` / ``execute_tool`` spans and the WCL, SQL and Redis
spans beneath it. Queue-fed background writers (FetchWriter, KbIndexer) run in tasks started
at boot, so their spans start their own traces.
"""

from __future__ import annotations

import logging
import os
import warnings
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.context import Context

from ..auth.redaction import RedactionFilter
from . import policy
from .config import TelemetryConfig, load_config

_tracer = trace.get_tracer(__name__)
_active: TelemetryConfig | None = None
# The exporters report their own failures through these loggers; exporting those records
# would loop while the collector is down.
_EXPORT_LOGGERS = ("opentelemetry", "urllib3", "requests")


def configure_telemetry() -> TelemetryConfig | None:
    """Turn telemetry on when an OTLP endpoint is configured; ``None`` when it stays off."""
    global _active
    if _active is not None:
        return _active
    config = load_config()
    if not config.enabled:
        return None
    from . import setup  # the exporters and instrumentors load only when telemetry is on

    os.environ.update(policy.content_env(config.content_allowed, os.environ))
    setup.install(config)
    _active = config
    return config


class _NotFromExporters(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        return not record.name.startswith(_EXPORT_LOGGERS)


def otlp_log_handler() -> logging.Handler | None:
    """The OTLP log handler for the root logger (records carry their span's trace and span
    id), or ``None`` when telemetry is off.

    It carries ``RedactionFilter`` itself: ``_install_log_redaction`` in ``main.py`` only
    covers the handlers that exist when it runs.
    """
    if _active is None:
        return None
    from opentelemetry.sdk._logs import LoggingHandler

    with warnings.catch_warnings():
        # Deprecated in favour of opentelemetry-instrumentation-logging; same behaviour.
        warnings.simplefilter("ignore", DeprecationWarning)
        handler = LoggingHandler()
    handler.addFilter(_NotFromExporters())
    handler.addFilter(RedactionFilter())
    return handler


@contextmanager
def chat_turn_span() -> Iterator[trace.Span]:
    """One websocket chat turn as the root span of its own trace (no-op when telemetry is off)."""
    with _tracer.start_as_current_span(
        "chat turn",
        context=Context(),
        kind=trace.SpanKind.SERVER,
        attributes={"http.route": "/ws/chat"},
    ) as span:
        yield span
