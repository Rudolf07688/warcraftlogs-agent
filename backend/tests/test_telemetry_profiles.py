"""Feature 059 (sc-421): span profiles are off unless configured, and when on they link each
root span to its CPU samples (spec §6.7).

No profiler ever starts here: ``pyroscope.configure`` and the thread tags are replaced by
recorders, and the spans run on a private tracer provider.
"""

from __future__ import annotations

import pyroscope
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend.app.telemetry import setup
from backend.app.telemetry.config import TelemetryConfig, load_config

ADDRESS = "http://pyroscope.test:4040"


@pytest.fixture
def fake_pyroscope(monkeypatch):
    calls: dict[str, list] = {"configure": [], "tags": []}
    monkeypatch.setattr(pyroscope, "configure", lambda **kwargs: calls["configure"].append(kwargs))
    monkeypatch.setattr(pyroscope, "add_thread_tag", lambda key, value: calls["tags"].append(("+", key, value)))
    monkeypatch.setattr(pyroscope, "remove_thread_tag", lambda key, value: calls["tags"].append(("-", key, value)))
    return calls


@pytest.mark.parametrize(
    ("env", "address"),
    [
        ({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://alloy:4318", "PYROSCOPE_SERVER_ADDRESS": ADDRESS}, ADDRESS),
        ({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://alloy:4318"}, ""),
        ({"PYROSCOPE_SERVER_ADDRESS": ADDRESS}, ""),  # telemetry off: no profiles either
        ({}, ""),
    ],
)
def test_profiles_need_telemetry_on_and_an_address(monkeypatch, env, address):
    for name in ("OTEL_EXPORTER_OTLP_ENDPOINT", "PYROSCOPE_SERVER_ADDRESS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("WCL_GIT_SHA", "abc1234")
    assert load_config().profiles_address == address


def test_without_an_address_no_profiler_starts(fake_pyroscope):
    provider = TracerProvider()
    assert setup.add_span_profiles(provider, TelemetryConfig(enabled=True, environment="dev", version="v")) is None
    with provider.get_tracer("t").start_as_current_span("root") as span:
        assert "pyroscope.profile.id" not in span.attributes
    assert fake_pyroscope == {"configure": [], "tags": []}


def test_root_spans_carry_the_profile_id_their_samples_are_tagged_with(fake_pyroscope):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    config = TelemetryConfig(enabled=True, environment="dev", version="abc1234", profiles_address=ADDRESS)
    assert setup.add_span_profiles(provider, config) is pyroscope

    [configured] = fake_pyroscope["configure"]
    assert configured == {
        "application_name": "api",
        "server_address": ADDRESS,
        "tags": {"service_namespace": "wcl-agent", "deployment_environment_name": "dev", "service_version": "abc1234"},
    }
    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span("chat turn") as root:
        with tracer.start_as_current_span("execute_tool"):
            pass
        root_id = format(root.get_span_context().span_id, "016x")
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["chat turn"].attributes["pyroscope.profile.id"] == root_id
    assert "pyroscope.profile.id" not in spans["execute_tool"].attributes
    assert ("+", "span_id", root_id) in fake_pyroscope["tags"]
    assert ("-", "span_id", root_id) in fake_pyroscope["tags"]  # untagged when the span ends
