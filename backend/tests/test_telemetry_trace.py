"""Feature 054 (sc-403): one chat turn is one trace, and web routes are traced by template.

The turn runs as ``ws.chat`` runs it: ``chat_turn_span`` around ``_start_turn`` on the SQLite
test DB, the real ADK runner on a scripted Claude, a tool that queries WCL over a mock
transport, and the OAuth token cached in fake Redis. The production bootstrap patches these
libraries globally before the app's objects exist; here the same instrumentors are applied to
the test's objects and removed afterwards.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from opentelemetry.util.http import parse_excluded_urls

from backend.app.api import ws as ws_mod
from backend.app.main import app
from backend.app.schemas import ChatTurn
from backend.app.telemetry import chat_turn_span, setup
from backend.app.tenancy.context import RequestIdentity
from backend.tests.test_llm_provider_agent import (  # noqa: F401 - fixture
    CLAUDE,
    SENTINEL_KEY,
    ScriptedApi,
    text_answer,
    use_provider,
)
from backend.tests.test_telemetry_support import otel, scripted_agent, tool_call_with  # noqa: F401
from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.client import wcl_client


async def report_title(code: str) -> dict:
    """The title of a Warcraft Logs report."""
    data = await wcl_client.get_async_client().query(
        "query($c: String) { reportData { report(code: $c) { title } } }", {"c": code}
    )
    return {"report": data}


class _FakeWs:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.frames.append(payload)


@pytest.fixture
def instrumented(engine):
    """SQL on the test engine and Redis, as the bootstrap instruments them in production."""
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, skip_dep_check=True)
    RedisInstrumentor().instrument()
    yield
    SQLAlchemyInstrumentor().uninstrument()
    RedisInstrumentor().uninstrument()


async def test_one_chat_turn_is_one_trace(
    otel, instrumented, as_user, fake_redis, monkeypatch, use_provider
):
    capture = otel(environment="prod")
    use_provider("anthropic", key=SENTINEL_KEY)
    scripted_agent(
        monkeypatch,
        ScriptedApi(tool_call_with("report_title", {"code": "a1B2c3"}), text_answer("It was Raid Night.")),
        report_title,
    )
    wcl = mock_async_client(lambda request: gql_response({"data": {"reportData": {"report": {"title": "Raid Night"}}}}))
    HTTPXClientInstrumentor.instrument_client(wcl._http)
    monkeypatch.setattr(wcl_client, "get_async_client", lambda: wcl)

    async def no_suggestions(*args, **kwargs):
        return []

    monkeypatch.setattr(ws_mod, "generate_followups", no_suggestions)
    identity = RequestIdentity(
        user_id=as_user.user_id,
        tenant_id=as_user.tenant_id,
        membership_role="tenant_admin",
        is_platform_admin=False,
        session_id=uuid.uuid4(),
    )
    sock = ws_mod._TurnSocket(_FakeWs())
    try:
        with chat_turn_span():
            await ws_mod._start_turn(sock, ChatTurn(model=CLAUDE, content="title of a1B2c3?"), identity)
        if sock.suggestions is not None:
            await sock.suggestions
    finally:
        HTTPXClientInstrumentor.uninstrument_client(wcl._http)
        await wcl.aclose()
    assert any(f.get("type") == "done" for f in sock.ws.frames)

    spans = capture.spans()
    by_id = {s.context.span_id: s for s in spans}
    assert len({s.context.trace_id for s in spans}) == 1
    [root] = [s for s in spans if s.parent is None]
    assert (root.name, root.kind, root.attributes["http.route"]) == ("chat turn", SpanKind.SERVER, "/ws/chat")

    def ancestry(span) -> list[str]:
        names = []
        while span.parent is not None:
            span = by_id[span.parent.span_id]
            names.append(span.name.split(" ")[0])
        return names

    graphql = [s for s in spans if s.kind is SpanKind.CLIENT and s.attributes.get("http.url") == wcl_client.GRAPHQL_URL]
    assert graphql
    assert {"execute_tool", "invoke_agent", "chat"} <= set(ancestry(graphql[0]))
    assert any(s.name.startswith("generate_content") for s in spans)
    sql = [s for s in spans if s.attributes.get("db.system") == "sqlite"]
    assert sql and all(ancestry(s)[-1] == "chat" for s in sql)
    redis = [s for s in spans if s.attributes.get("db.system") == "redis"]
    assert redis and any("execute_tool" in ancestry(s) for s in redis)


async def test_routes_are_traced_by_template_and_health_is_not(otel, as_user, monkeypatch):
    capture = otel(environment="prod")
    FastAPIInstrumentor.instrument_app(app, **setup.FASTAPI_OPTIONS)
    monkeypatch.setattr(app, "middleware_stack", None)  # an earlier test built it uninstrumented
    try:
        missing = uuid.uuid4()
        assert (await as_user.client.get(f"/api/conversations/{missing}")).status_code == 404
        assert (await as_user.client.get("/api/health")).status_code == 200
        assert (await as_user.client.get("/health")).status_code == 200
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    servers = [s for s in capture.spans() if s.kind is SpanKind.SERVER]
    assert [s.attributes["http.route"] for s in servers] == ["/api/conversations/{conv_id}"]
    assert servers[0].name == "GET /api/conversations/{conv_id}"
    assert as_user.session_token not in str([dict(s.attributes) for s in capture.spans()])


# Both only partly match a route in an included router (sc-461): the preflight matches the path
# but not the method, and the raids list is GET-only.
PARTIAL_MATCHES = (
    (
        "OPTIONS",
        "/api/conversations",
        {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    ),
    ("POST", "/api/raids", {}),
)


async def test_partial_route_matches_keep_their_status_with_telemetry_on(otel, as_user, monkeypatch):
    async def statuses() -> list[int]:
        return [
            (await as_user.client.request(method, path, headers=headers)).status_code
            for method, path, headers in PARTIAL_MATCHES
        ]

    off = await statuses()
    capture = otel(environment="prod")
    FastAPIInstrumentor.instrument_app(app, **setup.FASTAPI_OPTIONS)
    monkeypatch.setattr(app, "middleware_stack", None)  # an earlier request built it uninstrumented
    try:
        on = await statuses()
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    assert off == [200, 405]
    assert on == off
    servers = [s for s in capture.spans() if s.kind is SpanKind.SERVER]
    assert [(s.name, s.attributes["http.route"]) for s in servers] == [
        ("OPTIONS /api/conversations", "/api/conversations"),
        ("POST /api/raids", "/api/raids"),
    ]


def test_the_chat_socket_and_health_polls_are_excluded():
    excluded = parse_excluded_urls(setup.EXCLUDED_URLS)
    assert excluded.url_disabled("http://localhost:8000/ws/chat")
    assert excluded.url_disabled("http://localhost:8000/health")
    assert excluded.url_disabled("http://localhost:8000/api/health")
    assert not excluded.url_disabled("http://localhost:8000/api/conversations")
    assert not excluded.url_disabled("http://localhost:8000/api/conversations/1/chat")


def test_each_turn_starts_its_own_trace_even_inside_another_span(otel):
    capture = otel(environment="prod")
    with trace.get_tracer("t").start_as_current_span("websocket connection"):
        for _ in range(2):
            with chat_turn_span():
                pass

    turns = [s for s in capture.spans() if s.name == "chat turn"]
    assert len(turns) == 2 and all(s.parent is None for s in turns)
    assert len({s.context.trace_id for s in turns}) == 2


class _ClientSocket:
    """Just enough of a Starlette WebSocket for ``ws.chat``: two turns, then a disconnect."""

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


async def test_the_chat_socket_runs_every_turn_in_its_own_trace(otel, monkeypatch):
    capture = otel(environment="prod")
    identity = SimpleNamespace(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
    seen = []

    async def authenticate(_cookie):
        return identity

    async def start_turn(sock, turn, ident, *, fallback_model=None):
        seen.append(trace.get_current_span().get_span_context())

    monkeypatch.setattr(ws_mod, "origin_matches", lambda _origin: True)
    monkeypatch.setattr(ws_mod, "authenticate_session", authenticate)
    monkeypatch.setattr(ws_mod, "resolve_chat_model", lambda _app, model: model)
    monkeypatch.setattr(ws_mod, "fallback_model_for", lambda _app, _model: None)
    monkeypatch.setattr(ws_mod, "_start_turn", start_turn)
    with trace.get_tracer("t").start_as_current_span("websocket connection"):
        await ws_mod.chat(_ClientSocket({"model": CLAUDE, "content": "one"}, {"model": CLAUDE, "content": "two"}))

    turns = {s.context.span_id: s for s in capture.spans() if s.name == "chat turn"}
    assert [ctx.span_id in turns for ctx in seen] == [True, True]
    assert all(s.parent is None for s in turns.values())
    assert len({s.context.trace_id for s in turns.values()}) == 2
