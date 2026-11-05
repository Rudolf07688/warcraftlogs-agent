"""Feature 059 (sc-421): span profiles are off unless configured, and when on they link each
server root span to its CPU samples (spec §6.7).

No profiler ever starts here: ``pyroscope.configure`` and the thread tags are replaced by
recorders, and the spans run on a private tracer provider (the request test on the shared one).
The fix round (QA PERF-001, SEC-001, SEC-002): only bounded tags, every tag removed again, and no
tag from background SQL.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pyroscope
import pytest
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from backend.app.telemetry import setup
from backend.app.telemetry.config import TelemetryConfig, load_config
from backend.tests import test_telemetry_support
from backend.tests.test_telemetry_support import otel  # noqa: F401 - fixture

ROOT = Path(__file__).resolve().parents[2]

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
    with tracer.start_as_current_span("chat turn", kind=SpanKind.SERVER) as root:
        with tracer.start_as_current_span("execute_tool"):
            pass
        root_id = format(root.get_span_context().span_id, "016x")
        root.update_name("renamed")  # the tags added at the start are the ones removed
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["renamed"].attributes["pyroscope.profile.id"] == root_id
    assert "pyroscope.profile.id" not in spans["execute_tool"].attributes
    added = [("span_id", root_id), ("span_name", "chat turn")]  # no trace id: a new value per trace
    assert fake_pyroscope["tags"] == [("+", *tag) for tag in added] + [("-", *tag) for tag in added]


@pytest.mark.parametrize("kind", [SpanKind.INTERNAL, SpanKind.CLIENT])
def test_roots_other_than_server_spans_are_not_profiled(fake_pyroscope, kind):
    """Background work: an indexer's SQL, a sweep's Redis call, a boot step's HTTP request."""
    provider = TracerProvider()
    provider.add_span_processor(setup.SpanProfiles(pyroscope))
    with provider.get_tracer("t").start_as_current_span("SELECT", kind=kind) as span:
        assert "pyroscope.profile.id" not in span.attributes
    assert fake_pyroscope["tags"] == []


async def test_a_request_tags_its_route_template_and_leaves_no_tag_behind(otel, client, monkeypatch, fake_pyroscope):  # noqa: F811
    """QA SEC-001/SEC-002: ids and client text in the path never reach a profile label."""
    from backend.app.main import app

    otel(environment="prod")
    monkeypatch.setattr(test_telemetry_support._SPANS, "target", setup.SpanProfiles(pyroscope))
    FastAPIInstrumentor.instrument_app(app, **setup.FASTAPI_OPTIONS)
    monkeypatch.setattr(app, "middleware_stack", None)  # rebuilt with the instrumentation
    conversation = uuid.uuid4()
    try:
        await client.get(f"/api/conversations/{conversation}")
        await client.get("/api/no-such-route/client-chosen-text")
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    added = [tag[1:] for tag in fake_pyroscope["tags"] if tag[0] == "+"]
    removed = [tag[1:] for tag in fake_pyroscope["tags"] if tag[0] == "-"]
    assert [value for key, value in added if key == "span_name"] == ["GET /api/conversations/{conv_id}", "GET"]
    assert sorted(added) == sorted(removed)
    assert str(conversation) not in str(added) and "client-chosen-text" not in str(added)


# Runs in a fresh interpreter: instrument() patches SQLAlchemy globally. Statements outside any
# span, as the fetch writer, the KB indexer and the boot steps run them.
_BACKGROUND_SQL = r"""
import asyncio, json
import pyroscope
from opentelemetry import trace
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from backend.app.telemetry import setup

tags = []
pyroscope.add_thread_tag = lambda key, value: tags.append(("+", key, value))
pyroscope.remove_thread_tag = lambda key, value: tags.append(("-", key, value))
counts = {"started": [], "ended": []}
class Count(SpanProcessor):
    def on_start(self, span, parent_context=None): counts["started"].append(span.name)
    def on_end(self, span): counts["ended"].append(span.name)
provider = TracerProvider()
provider.add_span_processor(Count())
provider.add_span_processor(setup.SpanProfiles(pyroscope))
trace.set_tracer_provider(provider)
setup.instrument()
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sent = []
    event.listen(engine.sync_engine, "after_cursor_execute", lambda c, cur, statement, *a: sent.append(statement))
    async with engine.connect() as conn:
        for i in range(3):
            await conn.execute(text("SELECT :a AS answer"), {"a": i})
    checkout_listeners = len(engine.sync_engine.pool.dispatch.checkout)
    await engine.dispose()
    print(json.dumps({"sent": sent, "counts": counts, "tags": tags, "checkout_listeners": checkout_listeners}))

asyncio.run(main())
"""


def test_sql_outside_a_request_has_one_ended_span_per_statement_and_no_profile_tag():
    """QA PERF-001 / sc-474: one tracer per async engine. Two left a never-ended root span per
    statement, whose thread tags stayed for the life of the process."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("OTEL_")}
    r = subprocess.run([sys.executable, "-c", _BACKGROUND_SQL], cwd=ROOT, env=env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    got = json.loads(r.stdout.strip().splitlines()[-1])
    statements = [s for s in got["sent"] if s.startswith("SELECT ? AS answer")]
    assert len(statements) == 3
    assert all(s.count("traceparent=") == 1 for s in statements), statements
    started, ended = got["counts"]["started"], got["counts"]["ended"]
    assert sorted(started) == sorted(ended)  # every span ended
    assert [name for name in started if name.startswith("SELECT")] == ["SELECT :memory:"] * 3
    assert got["checkout_listeners"] == 1  # the pool's events are counted once
    assert got["tags"] == []
