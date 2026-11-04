"""Providers, exporters and instrumentation for the API process (feature 054, spec §6.1–6.2).

One resource and one pipeline per signal, all OTLP over http/protobuf (decision 12: no grpcio).
Batch processors with bounded queues keep export off the request path: a down collector costs
dropped data, never a blocked request. The builders take the exporter so tests can run the
same processors on in-memory exporters.
"""

from __future__ import annotations

import functools
import os
import re
from typing import Any

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
from opentelemetry.sdk.metrics import (
    Counter,
    Histogram,
    MeterProvider,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    MetricExporter,
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.metrics.view import ExponentialBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanLimits, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span
from starlette.routing import compile_path

from .config import TelemetryConfig
from .redaction import MAX_VALUE_LENGTH, RedactingLogExporter, RedactingSpanExporter

SERVICE_NAME = "api"
SERVICE_NAMESPACE = "wcl-agent"
# Not traced: health/readiness polls, and the chat websocket, whose connection lasts the whole
# session (each turn gets its own root span instead, see chat_turn_span). Regexes searched in
# the request URL.
EXCLUDED_URLS = r"/health$,/ws/chat$"
# One export attempt, retries included, waits at most this long, so a down collector costs at
# most a few seconds at shutdown (QA SEC-005).
EXPORT_TIMEOUT_S = 2.0
# Span attribute values are cut to the length the redaction scrubs (QA SEC-002, SEC-008).
SPAN_LIMITS = SpanLimits(max_attribute_length=MAX_VALUE_LENGTH)
# The only attributes a metric may carry (spec §9.3; QA SEC-003): bounded enums and templates.
# Never the Host header (http.host, http.server_name, net.host.name, server.address), an id, a
# raw path or a URL.
METRIC_ATTRIBUTES = frozenset(
    {
        # HTTP server and client, old and new semantic conventions
        "http.method",
        "http.request.method",
        "http.status_code",
        "http.response.status_code",
        "http.route",
        "http.target",  # the route template on server metrics, never set from the raw path
        "http.scheme",
        "url.scheme",
        "http.flavor",
        "network.protocol.version",
        "net.peer.name",  # outbound host: Warcraft Logs and the model APIs
        "error.type",
        # SQLAlchemy connection pool
        "pool.name",
        "state",
        # GenAI (ADK)
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.system",
        "gen_ai.request.model",
        "gen_ai.response.model",
        "gen_ai.token.type",
        "gen_ai.agent.name",
        "gen_ai.tool.name",
        "gen_ai.tool.type",
        "gen_ai.workflow.nested",
    }
)


def resource(config: TelemetryConfig) -> Resource:
    return Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.namespace": SERVICE_NAMESPACE,
            "service.version": config.version,
            "vcs.ref.head.revision": config.version,
            "deployment.environment.name": config.environment,
            "app.layer": "runtime",
        }
    )


def span_processor(exporter: SpanExporter, *, content_allowed: bool) -> BatchSpanProcessor:
    return BatchSpanProcessor(RedactingSpanExporter(exporter, content_allowed=content_allowed))


def log_processor(exporter: LogRecordExporter, *, content_allowed: bool) -> BatchLogRecordProcessor:
    return BatchLogRecordProcessor(RedactingLogExporter(exporter, content_allowed=content_allowed))


def metric_exporter() -> MetricExporter:
    """OTLP metrics: cumulative for every instrument, exponential histograms."""
    cumulative = AggregationTemporality.CUMULATIVE
    return OTLPMetricExporter(
        timeout=EXPORT_TIMEOUT_S,
        preferred_temporality={
            kind: cumulative
            for kind in (
                Counter,
                UpDownCounter,
                Histogram,
                ObservableCounter,
                ObservableUpDownCounter,
                ObservableGauge,
            )
        },
        preferred_aggregation={Histogram: ExponentialBucketHistogramAggregation()},
    )


def meter_provider(res: Resource, reader: MetricReader) -> MeterProvider:
    """Every instrument keeps only the allowlisted attributes, whoever recorded it."""
    return MeterProvider(
        resource=res,
        metric_readers=[reader],
        views=[View(instrument_name="*", attribute_keys=METRIC_ATTRIBUTES)],
    )


@functools.cache
def _route_templates(app: Any) -> tuple[tuple[re.Pattern[str], str], ...]:
    """The app's HTTP route templates with their regexes, literal routes first."""
    templates = sorted(app.openapi()["paths"], key=lambda path: (path.count("{"), path))
    return tuple((compile_path(path)[0], path) for path in templates)


def name_span_by_route(span: Span, scope: dict[str, Any]) -> None:
    """``server_request_hook``: name the server span by its route template.

    FastAPI includes routers lazily now, and the instrumentation's route lookup can't see
    inside them, so it would fall back to the raw path (ids and all). The OpenAPI paths are
    the templates.
    """
    if scope.get("type") != "http" or not span.is_recording():
        return
    path = scope.get("path", "")
    for regex, template in _route_templates(scope["app"]):
        if regex.match(path):
            span.set_attribute("http.route", template)
            span.update_name(f"{scope.get('method', 'HTTP')} {template}")
            return


FASTAPI_OPTIONS: dict[str, Any] = {
    "excluded_urls": EXCLUDED_URLS,
    "exclude_spans": ["receive", "send"],
    "server_request_hook": name_span_by_route,
}


def instrument() -> None:
    """Patch the libraries globally; must run before FastAPI apps and engines are created.

    No google-genai instrumentation: ADK's own generate_content span covers model calls.
    """
    FastAPIInstrumentor().instrument(**FASTAPI_OPTIONS)
    # Its declared range stops below SQLAlchemy 2.1 (we run 2.1.x); the engine events it uses
    # are unchanged, and the in-memory trace test proves the SQL spans.
    SQLAlchemyInstrumentor().instrument(skip_dep_check=True)
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()


def install(config: TelemetryConfig) -> None:
    """Set the global providers (before ADK is imported) and instrument the libraries."""
    res = resource(config)
    tracer_provider = TracerProvider(resource=res, span_limits=SPAN_LIMITS)
    tracer_provider.add_span_processor(
        span_processor(OTLPSpanExporter(timeout=EXPORT_TIMEOUT_S), content_allowed=config.content_allowed)
    )
    # Log records take their limits from the environment only.
    os.environ.setdefault("OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT", str(MAX_VALUE_LENGTH))
    logger_provider = LoggerProvider(resource=res)
    logger_provider.add_log_record_processor(
        log_processor(OTLPLogExporter(timeout=EXPORT_TIMEOUT_S), content_allowed=config.content_allowed)
    )
    trace.set_tracer_provider(tracer_provider)
    _logs.set_logger_provider(logger_provider)
    metrics.set_meter_provider(meter_provider(res, PeriodicExportingMetricReader(metric_exporter())))
    instrument()
