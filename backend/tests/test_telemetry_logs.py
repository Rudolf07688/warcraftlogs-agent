"""Feature 054 (sc-405): app logs go out over OTLP with their trace ids, redacted.

The handler under test is the one ``main.py`` adds to the root logger (``otlp_log_handler``);
here it hangs on a private logger so the rest of the suite's logging is untouched.
"""

from __future__ import annotations

import logging

import pytest
from opentelemetry import trace

from backend.app import telemetry
from backend.app.auth.redaction import REDACTED, RedactionFilter
from backend.app.telemetry.config import TelemetryConfig
from backend.tests.test_telemetry_support import otel  # noqa: F401 - fixture

SECRET = "tok-SECRET-054-log"


@pytest.fixture
def app_logger(monkeypatch):
    monkeypatch.setattr(telemetry, "_active", TelemetryConfig(enabled=True, environment="prod", version="t"))
    handler = telemetry.otlp_log_handler()
    loggers = []

    def get(name: str) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        loggers.append(logger)
        return logger

    yield get
    for logger in loggers:
        logger.removeHandler(handler)


def test_a_log_line_carries_its_spans_trace_and_span_id(otel, app_logger):
    capture = otel(environment="prod")
    log = app_logger("backend.app.test054")
    with trace.get_tracer("t").start_as_current_span("turn") as span:
        log.info("turn stats %s", "ok")

    [record] = [r.log_record for r in capture.logs()]
    assert record.body == "turn stats ok"
    assert record.trace_id == span.get_span_context().trace_id != 0
    assert record.span_id == span.get_span_context().span_id


def test_a_token_in_extra_is_exported_redacted(otel, app_logger):
    capture = otel(environment="prod")
    app_logger("backend.app.test054").warning(
        "refresh failed", extra={"token": SECRET, "request": {"password": SECRET, "attempt": 2}}
    )

    [record] = [r.log_record for r in capture.logs()]
    assert record.attributes["token"] == REDACTED
    assert record.attributes["request"] == {"password": REDACTED, "attempt": 2}
    assert SECRET not in str(dict(record.attributes))


def test_the_handler_carries_the_redaction_filter_itself(app_logger):
    """``_install_log_redaction`` only covers handlers that exist when it runs."""
    handler = telemetry.otlp_log_handler()
    record = logging.LogRecord("backend.app.x", logging.INFO, __file__, 1, "m", None, None)
    record.token = SECRET
    assert handler.filter(record) and record.token == REDACTED
    assert any(isinstance(f, RedactionFilter) for f in handler.filters)


def test_the_exporters_own_failure_logs_are_not_exported(otel, app_logger):
    """A down collector makes the exporter log; exporting those records would feed itself."""
    capture = otel(environment="prod")
    for name in ("opentelemetry.exporter.otlp.proto.http._log_exporter", "urllib3.connectionpool"):
        app_logger(name).warning("Failed to export logs batch")
    app_logger("backend.app.test054").warning("kept")

    assert [r.log_record.body for r in capture.logs()] == ["kept"]


def test_no_handler_while_telemetry_is_off(monkeypatch):
    monkeypatch.setattr(telemetry, "_active", None)
    assert telemetry.otlp_log_handler() is None
