"""Shared fixture for the 054 telemetry tests: the production processors on in-memory exporters.

The global providers can be set once per process, and ADK's module-level proxies cache the
real tracer and logger they first resolve, so one tracer and one logger provider serve every
telemetry test. Each test plugs in fresh production processors (``setup.span_processor`` /
``setup.log_processor``: the redacting exporter wrappers behind batch processors) around
in-memory exporters, with the content policy applied through ``monkeypatch``. Between tests the
processors are unplugged and every tracer and logger is disabled, so nothing records in other
tests.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import anthropic
import httpx2
import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from opentelemetry import _logs, trace
from opentelemetry.sdk._logs import LoggerProvider, LogRecordProcessor, ReadableLogRecord
from opentelemetry.sdk._logs._internal import _disable_logger_configurator
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace import (
    ReadableSpan,
    SpanProcessor,
    TracerProvider,
    _default_tracer_configurator,
    _disable_tracer_configurator,
)
from opentelemetry.sdk._logs._internal import _default_logger_configurator
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend.app import agent_runner
from backend.app.telemetry import policy, setup
from backend.app.telemetry.config import TelemetryConfig
from backend.tests.test_llm_provider_agent import CLAUDE, ScriptedApi, _message_start, _sse
from wcl_agent.agent import build_agent
from wcl_agent.capabilities import ToolGroup
from wcl_agent.llm import model_retry, provider
from wcl_agent.llm.model_retry import RetryPolicy


class _SpanSwitch(SpanProcessor):
    target: SpanProcessor | None = None

    def on_start(self, span, parent_context=None) -> None:
        if self.target is not None:
            self.target.on_start(span, parent_context)

    def on_end(self, span) -> None:
        if self.target is not None:
            self.target.on_end(span)


class _LogSwitch(LogRecordProcessor):
    target: LogRecordProcessor | None = None

    def on_emit(self, log_record) -> None:
        if self.target is not None:
            self.target.on_emit(log_record)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


_SPANS, _LOGS = _SpanSwitch(), _LogSwitch()
_providers: tuple[TracerProvider, LoggerProvider] | None = None


def _global_providers() -> tuple[TracerProvider, LoggerProvider]:
    global _providers
    if _providers is None:
        res = setup.resource(TelemetryConfig(enabled=True, environment="dev", version="test"))
        tracer_provider = TracerProvider(resource=res)
        tracer_provider.add_span_processor(_SPANS)
        logger_provider = LoggerProvider(resource=res)
        logger_provider.add_log_record_processor(_LOGS)
        trace.set_tracer_provider(tracer_provider)
        _logs.set_logger_provider(logger_provider)
        _providers = (tracer_provider, logger_provider)
    return _providers


def _enable(on: bool) -> None:
    tracer_provider, logger_provider = _global_providers()
    tracer_provider._set_tracer_configurator(
        tracer_configurator=_default_tracer_configurator if on else _disable_tracer_configurator
    )
    logger_provider._set_logger_configurator(
        logger_configurator=_default_logger_configurator if on else _disable_logger_configurator
    )


@dataclass
class Capture:
    span_processor: SpanProcessor
    log_processor: LogRecordProcessor
    span_exporter: InMemorySpanExporter
    log_exporter: InMemoryLogRecordExporter

    def spans(self) -> list[ReadableSpan]:
        self.span_processor.force_flush()
        return list(self.span_exporter.get_finished_spans())

    def logs(self) -> list[ReadableLogRecord]:
        self.log_processor.force_flush()
        return list(self.log_exporter.get_finished_logs())


@pytest.fixture
def otel(monkeypatch):
    captures: list[Capture] = []

    def install(*, environment: str = "dev", exporter_content: bool | None = None) -> Capture:
        """``exporter_content`` overrides the exporters' half of the policy, to test each half
        (ADK's env settings, the app-side wrappers) on its own."""
        allowed = TelemetryConfig(enabled=True, environment=environment, version="test").content_allowed
        for key, value in policy.content_env(allowed, os.environ).items():
            monkeypatch.setenv(key, value)
        exported = allowed if exporter_content is None else exporter_content
        spans, logs = InMemorySpanExporter(), InMemoryLogRecordExporter()
        capture = Capture(
            setup.span_processor(spans, content_allowed=exported),
            setup.log_processor(logs, content_allowed=exported),
            spans,
            logs,
        )
        _SPANS.target, _LOGS.target = capture.span_processor, capture.log_processor
        _enable(True)
        captures.append(capture)
        return capture

    yield install
    _enable(False)
    _SPANS.target = _LOGS.target = None
    for capture in captures:
        capture.span_processor.shutdown()
        capture.log_processor.shutdown()


def everything(capture: Capture) -> str:
    """Every exported span and log record as one string, for "does X appear anywhere" checks."""
    parts: list[str] = []
    for span in capture.spans():
        parts += [span.name, str(dict(span.attributes or {})), str(span.status.description)]
        for event in span.events:
            parts += [event.name, str(dict(event.attributes or {}))]
    for record in capture.logs():
        log = record.log_record
        parts += [str(log.event_name), str(log.body), str(dict(log.attributes or {}))]
    return "\n".join(parts)


# --- a scripted ADK turn --------------------------------------------------------------------


def tool_call_with(name: str, arguments: dict) -> bytes:
    """A scripted Claude reply that calls ``name`` with ``arguments``."""
    return _sse(
        _message_start(CLAUDE),
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "toolu_1", "name": name, "input": {}},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": json.dumps(arguments)},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use", "stop_sequence": None},
            "usage": {"output_tokens": 5},
        },
        {"type": "message_stop"},
    )


def scripted_agent(monkeypatch, api: ScriptedApi, *tools) -> None:
    """Chat turns run the real ``build_agent`` with ``tools`` on Claude answered by ``api``."""
    real = provider.async_anthropic_client

    def build(**kwargs):
        http = anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(api))
        return real(http_client=http, **kwargs)

    monkeypatch.setattr(model_retry, "async_anthropic_client", build)
    sessions = InMemorySessionService()
    monkeypatch.setattr(agent_runner, "_session_service", sessions)

    def runner(model: str) -> Runner:
        agent = build_agent(
            model, retry=RetryPolicy(initial_s=0, jitter_s=0), extra_groups=(ToolGroup("Test", tools),)
        )
        return Runner(agent=agent, app_name=agent_runner.APP_NAME, session_service=sessions)

    monkeypatch.setattr(agent_runner, "_get_runner", runner)
