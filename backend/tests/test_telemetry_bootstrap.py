"""Feature 054 (sc-402): the telemetry bootstrap is off unless configured, and when on it is
in place before FastAPI and ADK load.

The real start is ``import backend.app.main``; the global providers and instrumentation it may
install can't be undone in-process, so those checks run in a fresh interpreter. The collector
endpoint is a refused port: nothing is ever sent.
"""

from __future__ import annotations

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import uuid
import subprocess
import sys
import time
from pathlib import Path

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import Counter, Histogram
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader
from opentelemetry.sdk.metrics._internal.point import ExponentialHistogramDataPoint

from backend.app import telemetry
from backend.app.telemetry import setup
from backend.app.telemetry.config import TelemetryConfig
from backend.app.telemetry.redaction import MAX_VALUE_LENGTH

ROOT = Path(__file__).resolve().parents[2]
DEAD_COLLECTOR = "http://127.0.0.1:9"
ADK_CONTENT_ENV = (
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
    "ADK_TELEMETRY_IGNORE_RUN_CONFIG",
    "OTEL_SEMCONV_STABILITY_OPT_IN",
)

# Imports the app the way uvicorn does and reports what the bootstrap left behind. The spies
# record whether ADK was already loaded when each global provider was set; the app being an
# instrumented FastAPI shows the patch came before main.py bound the name.
PROBE = r"""
import json, logging, os, sys, time
from opentelemetry import _logs, metrics, trace

loaded_at_set = {}
def spy(module, name):
    real = getattr(module, name)
    def wrapper(provider):
        loaded_at_set[name] = "google.adk" in sys.modules
        real(provider)
    setattr(module, name, wrapper)
for module, name in ((trace, "set_tracer_provider"), (_logs, "set_logger_provider"), (metrics, "set_meter_provider")):
    spy(module, name)

started = time.monotonic()
import backend.app.main as main
import_s = time.monotonic() - started

from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

tp = trace.get_tracer_provider()
report = {
    "import_s": import_s,
    "adk_loaded_at_set": loaded_at_set,
    "tracer_provider": type(tp).__name__,
    "logger_provider": type(_logs.get_logger_provider()).__name__,
    "meter_provider": type(metrics.get_meter_provider()).__name__,
    "app_class": type(main.app).__name__,
    "engine_listeners": len(main.engine.sync_engine.dispatch.before_cursor_execute),
    "redis": RedisInstrumentor().is_instrumented_by_opentelemetry,
    "httpx": HTTPXClientInstrumentor().is_instrumented_by_opentelemetry,
    "sqlalchemy": SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry,
    "root_handlers": [type(h).__name__ for h in logging.getLogger().handlers],
    "otlp_handler_filters": [type(f).__name__ for h in logging.getLogger().handlers if type(h).__name__ == "LoggingHandler" for f in h.filters],
    "env": {k: os.environ.get(k) for k in %(adk_env)r},
    "pyroscope_loaded": "pyroscope" in sys.modules,
}
if report["tracer_provider"] == "TracerProvider":
    report["resource"] = dict(tp.resource.attributes)
    batch = tp._active_span_processor._span_processors[0]._batch_processor
    report["span_exporter"] = [type(batch._exporter).__name__, type(batch._exporter._inner).__module__]

    # The collector is down: spans, logs and a request must not wait for it.
    from fastapi.testclient import TestClient
    started = time.monotonic()
    tracer = trace.get_tracer("probe")
    for i in range(200):
        with tracer.start_as_current_span("work"):
            logging.getLogger("backend.app.probe").warning("line %%d", i)
    report["health"] = TestClient(main.app).get("/health").status_code
    report["busy_s"] = time.monotonic() - started
    with tracer.start_as_current_span("big") as span:
        span.set_attribute("gen_ai.input.messages", "x" * 100000)
        report["span_value_length"] = len(span.attributes["gen_ai.input.messages"])
    report["log_value_limit"] = os.environ.get("OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT")
    for i in range(int(os.environ.get("PROBE_BACKLOG", "0"))):  # queued for the exit-time flush
        with tracer.start_as_current_span("backlog"):
            logging.getLogger("backend.app.probe").warning("backlog %%d", i)

report["reported_at"] = time.time()
print("REPORT" + json.dumps(report))
sys.stdout.flush()
if os.environ.get("PROBE_EXIT") != "normal":
    os._exit(0)  # skip the exit-time flush to the dead collector
""" % {"adk_env": ADK_CONTENT_ENV}


def _probe(**env: str) -> dict:
    return _run_probe(env)[0]


def _run_probe(env: dict[str, str]) -> tuple[dict, float]:
    """The probe's report, and how long the process took after reporting (its exit)."""
    clean = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OTEL_", "WCL_ENVIRONMENT", "WCL_GIT_SHA", "ADK_", "PYROSCOPE_"))
    }
    out = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=ROOT,
        env={**clean, **env},
        capture_output=True,
        text=True,
        timeout=180,
    )
    ended = time.time()
    lines = [line for line in out.stdout.splitlines() if line.startswith("REPORT")]
    assert lines, out.stderr[-3000:]
    report = json.loads(lines[0][len("REPORT") :])
    return report, ended - report["reported_at"]


def test_without_an_endpoint_nothing_is_installed():
    report = _probe()

    assert report["tracer_provider"] == "ProxyTracerProvider"
    assert report["logger_provider"] == "ProxyLoggerProvider"
    assert report["meter_provider"] == "_ProxyMeterProvider"
    assert report["app_class"] == "FastAPI"
    assert report["engine_listeners"] == 0
    assert not (report["redis"] or report["httpx"] or report["sqlalchemy"])
    assert "LoggingHandler" not in report["root_handlers"]
    assert report["env"] == dict.fromkeys(ADK_CONTENT_ENV)  # the process env is untouched
    assert not report["pyroscope_loaded"]


def test_with_an_endpoint_everything_is_in_place_before_adk_loads():
    report = _probe(
        OTEL_EXPORTER_OTLP_ENDPOINT=DEAD_COLLECTOR, WCL_ENVIRONMENT="dev", WCL_GIT_SHA="abc1234"
    )

    assert report["adk_loaded_at_set"] == {
        "set_tracer_provider": False,
        "set_logger_provider": False,
        "set_meter_provider": False,
    }
    assert (report["tracer_provider"], report["logger_provider"], report["meter_provider"]) == (
        "TracerProvider",
        "LoggerProvider",
        "MeterProvider",
    )
    assert {
        "service.name": "api",
        "service.namespace": "wcl-agent",
        "service.version": "abc1234",
        "vcs.ref.head.revision": "abc1234",
        "app.layer": "runtime",
        "deployment.environment.name": "dev",
    }.items() <= report["resource"].items()
    assert report["span_exporter"] == [
        "RedactingSpanExporter",
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
    ]
    assert report["app_class"] == "_InstrumentedFastAPI"
    assert report["engine_listeners"] >= 1  # the app's one engine, created after the bootstrap
    assert report["redis"] and report["httpx"] and report["sqlalchemy"]
    assert report["root_handlers"] == ["StreamHandler", "LoggingHandler"]  # stdout stays
    assert "RedactionFilter" in report["otlp_handler_filters"]
    assert not report["pyroscope_loaded"]  # feature 059: no profiler without PYROSCOPE_SERVER_ADDRESS


def test_a_down_collector_blocks_neither_startup_nor_requests():
    report = _probe(OTEL_EXPORTER_OTLP_ENDPOINT=DEAD_COLLECTOR, WCL_ENVIRONMENT="prod")

    assert report["health"] == 200
    # 200 spans, 200 log lines and a request: generous headroom, but well below one export
    # attempt's timeout (10 s), which any wait on the collector would cost.
    assert report["busy_s"] < 8
    assert report["env"] == {
        "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "false",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "NO_CONTENT",
        "ADK_TELEMETRY_IGNORE_RUN_CONFIG": "1",
        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
    }
    assert report["resource"]["deployment.environment.name"] == "prod"
    # Attribute values are capped at the redaction length (QA SEC-002, SEC-008).
    assert report["span_value_length"] == MAX_VALUE_LENGTH
    assert report["log_value_limit"] == str(MAX_VALUE_LENGTH)


def test_a_down_collector_delays_exit_by_a_few_seconds_at_most():
    """The exit-time flush retries until its export timeout; three signals in a row (QA SEC-005)."""
    _report, exit_s = _run_probe(
        {"OTEL_EXPORTER_OTLP_ENDPOINT": DEAD_COLLECTOR, "WCL_ENVIRONMENT": "prod", "PROBE_EXIT": "normal"}
    )
    assert exit_s < 7  # ~3.5 s measured; the SDK's 10 s default made it 8 s and more


def test_a_hung_collector_with_a_backlog_delays_exit_by_the_shutdown_bound_at_most():
    """A collector that accepts and never answers costs an export timeout per batch; the exit
    flush of all three signals stops at SHUTDOWN_TIMEOUT_S and drops the rest (QA BUG-003)."""
    with socket.socket() as hung:
        hung.bind(("127.0.0.1", 0))
        hung.listen(64)  # never accepted, never answered
        _report, exit_s = _run_probe(
            {
                "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{hung.getsockname()[1]}",
                "WCL_ENVIRONMENT": "prod",
                "PROBE_EXIT": "normal",
                "PROBE_BACKLOG": "3000",
            }
        )
    assert exit_s < setup.SHUTDOWN_TIMEOUT_S + 2.5  # unbounded: 9-11 s measured


class _HungProvider:
    def __init__(self) -> None:
        self.called = threading.Event()

    def shutdown(self) -> None:
        self.called.set()
        threading.Event().wait()  # an export into a collector that never answers


class _QuickProvider:
    def __init__(self) -> None:
        self.done = threading.Event()

    def shutdown(self) -> None:
        self.done.set()


def test_shutdown_waits_for_all_providers_together_and_no_longer_than_the_bound():
    hung = [_HungProvider() for _ in range(3)]
    quick = _QuickProvider()
    started = time.monotonic()
    setup.shutdown([*hung, quick], timeout_s=1.0)
    elapsed = time.monotonic() - started

    assert 0.9 < elapsed < 2.5  # one shared deadline, not one per provider (3 s)
    assert all(provider.called.is_set() for provider in hung) and quick.done.is_set()


def test_the_exit_flush_still_delivers_to_a_collector_that_answers():
    received: list[str] = []

    class Collector(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server API
            self.rfile.read(int(self.headers["Content-Length"]))
            received.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args) -> None:
            pass

    with HTTPServer(("127.0.0.1", 0), Collector) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _run_probe(
            {
                "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{server.server_address[1]}",
                "WCL_ENVIRONMENT": "prod",
                "PROBE_EXIT": "normal",
            }
        )
        server.shutdown()
    # The probe's spans and log lines wait in the queues until exit (fewer than one batch). It
    # records no metric (its one request is /health, which isn't traced), so none are sent.
    assert {"/v1/traces", "/v1/logs"} <= set(received)


def test_the_suite_runs_without_a_shells_otel_settings():
    """bin/claude-otel exports OTEL_EXPORTER_OTLP_ENDPOINT; conftest strips it (QA SEC-005)."""
    assert not [name for name in os.environ if name.startswith("OTEL_")]
    assert telemetry.configure_telemetry() is None


def test_configure_is_a_no_op_without_an_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    before = dict(os.environ)
    assert telemetry.configure_telemetry() is None
    assert dict(os.environ) == before


def test_metrics_are_cumulative_with_exponential_histograms():
    exporter = setup.metric_exporter()
    reader = InMemoryMetricReader(
        preferred_temporality=exporter._preferred_temporality,
        preferred_aggregation=exporter._preferred_aggregation,
    )
    provider = setup.meter_provider(
        setup.resource(TelemetryConfig(enabled=True, environment="ci", version="t")), reader
    )
    meter = provider.get_meter("t")
    meter.create_histogram("latency").record(0.25)
    meter.create_counter("calls").add(1)

    metrics = {
        m.name: m.data
        for rm in reader.get_metrics_data().resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    assert isinstance(metrics["latency"].data_points[0], ExponentialHistogramDataPoint)
    assert metrics["latency"].aggregation_temporality is AggregationTemporality.CUMULATIVE
    assert metrics["calls"].aggregation_temporality is AggregationTemporality.CUMULATIVE
    assert {Counter, Histogram} <= set(exporter._preferred_temporality)
    provider.shutdown()


async def test_no_request_value_becomes_a_metric_label(client, monkeypatch):
    """Host header, ids in the path: the View keeps only allowlisted keys (QA SEC-003)."""
    from backend.app.main import app

    reader = InMemoryMetricReader()
    provider = setup.meter_provider(
        setup.resource(TelemetryConfig(enabled=True, environment="ci", version="t")), reader
    )
    FastAPIInstrumentor.instrument_app(app, meter_provider=provider, **setup.FASTAPI_OPTIONS)
    monkeypatch.setattr(app, "middleware_stack", None)  # rebuilt with the instrumentation
    try:
        for i in range(40):
            await client.get(f"/api/conversations/{uuid.uuid4()}", headers={"host": f"h{i}.attacker.example"})
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    points = [
        point
        for rm in reader.get_metrics_data().resource_metrics
        for sm in rm.scope_metrics
        for metric in sm.metrics
        if metric.name.startswith("http.server")
        for point in metric.data.data_points
    ]
    assert points and all(set(p.attributes) <= setup.METRIC_ATTRIBUTES for p in points)
    assert "attacker" not in str([dict(p.attributes) for p in points])
    assert len(points) <= 6  # a few instruments x one status, not one series per request
    provider.shutdown()
