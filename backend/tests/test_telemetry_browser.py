"""Feature 057 (sc-415): the browser's trace context and Faro session id reach backend spans.

Both values are attacker controlled, so the edge cases come first: whatever the browser sends,
a turn or request runs, with a fresh root trace or without the attribute, and no attribute is
unbounded. The happy paths follow: a valid message context parents "chat turn", and the REST
header lands on the server span.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from backend.app.api import ws as ws_mod
from backend.app.main import app
from backend.app.telemetry import browser, chat_turn_span, setup
from backend.tests.test_llm_provider_agent import CLAUDE
from backend.tests.test_telemetry_support import otel  # noqa: F401 - fixture

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SPAN_ID = "b7ad6b7169203331"
VALID = f"00-{TRACE_ID}-{SPAN_ID}-01"

BAD_TRACEPARENTS = [
    None,
    "",
    123,
    ["00", TRACE_ID],
    "garbage",
    f"00-{TRACE_ID}-{SPAN_ID}",  # a field is missing
    f"00-{'0' * 32}-{SPAN_ID}-01",  # all-zero trace id
    f"00-{TRACE_ID}-{'0' * 16}-01",  # all-zero span id
    f"00-{TRACE_ID}-{SPAN_ID}-00",  # unsampled
    f"ff-{TRACE_ID}-{SPAN_ID}-01",  # forbidden version
    f"00-{TRACE_ID.upper()}-{SPAN_ID}-01",  # W3C ids are lower case
    VALID + "-extra",  # version 00 has no extra field
    VALID + "x" * 10_000,  # oversized
    "00-" + "a" * 10_000,
    f"01-{TRACE_ID}-{SPAN_ID}-01-" + "x" * 10_000,  # a later version may append fields, within the bound
    f"00-{TRACE_ID}-{SPAN_ID}-01\x00",
]

BAD_SESSION_IDS = [
    None,
    "",
    42,
    {"id": "abc"},
    "has space",
    "line\nbreak",
    "tab\there",
    "nul\x00byte",
    "esc\x1b[31m",
    "abc\n",  # `$` would let a trailing newline through
    "x" * 65,
    "y" * 10_000,
    "café",
    "<script>",
]


@pytest.mark.parametrize("value", BAD_TRACEPARENTS)
def test_an_unusable_traceparent_is_no_parent(value):
    assert browser.parent_context(value) is None


@pytest.mark.parametrize("value", BAD_SESSION_IDS)
def test_an_unusable_session_id_is_dropped(value):
    assert browser.session_id(value) is None


def test_a_valid_traceparent_is_the_parent():
    context = browser.parent_context(VALID)
    span_context = trace.get_current_span(context).get_span_context()
    assert (format(span_context.trace_id, "032x"), format(span_context.span_id, "016x")) == (TRACE_ID, SPAN_ID)


@pytest.mark.parametrize("value", ["a1B2c3D4e5", "abc-123_x.y:z", "x" * 64])
def test_a_safe_short_session_id_is_kept(value):
    assert browser.session_id(value) == value


@pytest.mark.parametrize("traceparent", BAD_TRACEPARENTS)
def test_an_unusable_message_context_starts_a_fresh_root_turn(otel, traceparent):
    capture = otel(environment="prod")
    with chat_turn_span(traceparent, "bad id with spaces"):
        pass

    [turn] = capture.spans()
    assert turn.name == "chat turn" and turn.parent is None
    assert format(turn.context.trace_id, "032x") != TRACE_ID
    assert "session.id" not in turn.attributes


@pytest.mark.parametrize("session", BAD_SESSION_IDS)
def test_a_valid_traceparent_with_an_unusable_session_id_still_parents_the_turn(otel, session):
    capture = otel(environment="prod")
    with chat_turn_span(VALID, session):
        pass

    [turn] = capture.spans()
    assert format(turn.context.trace_id, "032x") == TRACE_ID
    assert "session.id" not in turn.attributes


def test_an_old_frontend_sends_neither_field(otel):
    capture = otel(environment="prod")
    with chat_turn_span():
        pass

    [turn] = capture.spans()
    assert turn.parent is None and "session.id" not in turn.attributes


def test_a_valid_message_context_parents_the_turn_and_tags_the_session(otel):
    capture = otel(environment="prod")
    with trace.get_tracer("t").start_as_current_span("websocket connection"):
        with chat_turn_span(VALID, "a1B2c3D4e5"):
            with trace.get_tracer("t").start_as_current_span("child"):
                pass

    spans = {s.name: s for s in capture.spans()}
    turn = spans["chat turn"]
    assert format(turn.context.trace_id, "032x") == TRACE_ID
    assert format(turn.parent.span_id, "016x") == SPAN_ID and turn.parent.is_remote
    assert turn.attributes["session.id"] == "a1B2c3D4e5"
    assert turn.attributes["http.route"] == "/ws/chat"
    assert spans["child"].context.trace_id == turn.context.trace_id
    assert spans["websocket connection"].context.trace_id != turn.context.trace_id


def test_with_telemetry_off_the_turn_still_runs_on_any_input():
    # No provider: the tracer is the no-op one.
    for traceparent in (VALID, *BAD_TRACEPARENTS):
        with chat_turn_span(traceparent, "x" * 10_000) as span:
            assert not span.is_recording()


class _ClientSocket:
    def __init__(self, *turns: dict) -> None:
        self.turns = list(turns)
        self.headers = {"origin": "http://test"}
        self.cookies: dict[str, str] = {}
        self.app = app

    async def accept(self) -> None:
        pass

    async def receive_json(self) -> dict:
        if not self.turns:
            raise WebSocketDisconnect()
        return self.turns.pop(0)

    async def send_json(self, payload: dict) -> None:
        pass


@pytest.fixture
def chat_socket(monkeypatch):
    """``ws.chat`` with auth and the turn stubbed: what the frame reaches is the span."""
    identity = SimpleNamespace(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
    started = []

    async def authenticate(_cookie):
        return identity

    async def start_turn(sock, turn, ident, *, fallback_model=None):
        started.append(turn.content)

    monkeypatch.setattr(ws_mod, "origin_matches", lambda _origin: True)
    monkeypatch.setattr(ws_mod, "authenticate_session", authenticate)
    monkeypatch.setattr(ws_mod, "resolve_chat_model", lambda _app, model: model)
    monkeypatch.setattr(ws_mod, "fallback_model_for", lambda _app, _model: None)
    monkeypatch.setattr(ws_mod, "_start_turn", start_turn)
    return started


async def test_the_chat_frame_fields_parent_the_turn(otel, chat_socket):
    capture = otel(environment="prod")
    frame = {"model": CLAUDE, "content": "one", "traceparent": VALID, "faro_session_id": "a1B2c3D4e5"}
    await ws_mod.chat(_ClientSocket(frame))

    [turn] = [s for s in capture.spans() if s.name == "chat turn"]
    assert format(turn.context.trace_id, "032x") == TRACE_ID
    assert turn.attributes["session.id"] == "a1B2c3D4e5"
    assert chat_socket == ["one"]


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"traceparent": "x" * 10_000, "faro_session_id": "y" * 10_000},
        {"traceparent": None, "faro_session_id": None},
        {"traceparent": 7, "faro_session_id": ["a"]},
        {"traceparent": f"00-{'0' * 32}-{SPAN_ID}-01", "faro_session_id": "bad\nid"},
    ],
)
async def test_a_bad_or_missing_frame_field_never_breaks_the_turn(otel, chat_socket, extra):
    capture = otel(environment="prod")
    await ws_mod.chat(_ClientSocket({"model": CLAUDE, "content": "one", **extra}))

    assert chat_socket == ["one"]  # the turn ran, nothing was sent back as an error
    [turn] = [s for s in capture.spans() if s.name == "chat turn"]
    assert turn.parent is None and "session.id" not in turn.attributes


@pytest.fixture
def instrumented_app(monkeypatch):
    FastAPIInstrumentor.instrument_app(app, **setup.FASTAPI_OPTIONS)
    monkeypatch.setattr(app, "middleware_stack", None)  # an earlier test built it uninstrumented
    yield
    FastAPIInstrumentor.uninstrument_app(app)


async def _server_span(capture, as_user, headers):
    await as_user.client.get(f"/api/conversations/{uuid.uuid4()}", headers=headers)
    [span] = [s for s in capture.spans() if s.kind is trace.SpanKind.SERVER]
    return span


async def test_a_rest_call_joins_the_browser_trace_and_carries_the_session(otel, as_user, instrumented_app):
    capture = otel(environment="prod")
    headers = {"traceparent": VALID, "x-faro-session-id": "a1B2c3D4e5"}
    span = await _server_span(capture, as_user, headers)

    assert format(span.context.trace_id, "032x") == TRACE_ID
    assert span.attributes["session.id"] == "a1B2c3D4e5"


@pytest.mark.parametrize("value", ["", "has space", "x" * 10_000, "café", "bad;id"])
async def test_an_unusable_rest_session_header_is_dropped(otel, as_user, instrumented_app, value):
    capture = otel(environment="prod")
    span = await _server_span(capture, as_user, {"x-faro-session-id": value.encode()})

    assert "session.id" not in span.attributes
    assert span.attributes["http.route"] == "/api/conversations/{conv_id}"


async def test_a_rest_call_without_the_header_has_no_session(otel, as_user, instrumented_app):
    capture = otel(environment="prod")
    span = await _server_span(capture, as_user, {})

    assert "session.id" not in span.attributes


async def test_the_session_header_with_telemetry_off_changes_nothing(as_user):
    response = await as_user.client.get(
        f"/api/conversations/{uuid.uuid4()}", headers={"x-faro-session-id": "a1B2c3D4e5"}
    )
    assert response.status_code == 404
