"""Startup tracker + readiness gate (boot overlay support)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.startup import ReadinessGate, StartupTracker


# --- tracker ------------------------------------------------------------------


async def test_tracker_happy_path_records_steps_and_ready():
    t = StartupTracker((("a", "A"), ("b", "B")))
    assert t.phase == "booting" and not t.ready

    async def one() -> int:
        return 3

    out = await t.run("a", one, detail=lambda n: f"{n} things")
    assert out == 3
    snap = t.snapshot()
    assert snap["steps"][0]["status"] == "done"
    assert snap["steps"][0]["detail"] == "3 things"
    assert snap["steps"][0]["ms"] is not None
    assert snap["current_step"] is None

    t.begin("b")
    assert t.snapshot()["current_step"] == "b"
    t.done("b")
    t.finish()
    assert t.ready and t.snapshot()["phase"] == "ready"


async def test_tracker_optional_failure_is_skipped_not_fatal():
    t = StartupTracker((("a", "A"),))

    async def boom() -> None:
        raise RuntimeError("table missing")

    assert await t.run("a", boom, optional=True) is None
    step = t.snapshot()["steps"][0]
    assert step["status"] == "skipped"
    assert "table missing" in step["detail"]
    t.finish()
    assert t.ready


async def test_tracker_required_failure_marks_boot_failed_and_reraises():
    t = StartupTracker((("a", "A"), ("b", "B")))

    async def boom() -> None:
        raise ValueError("no db")

    with pytest.raises(ValueError):
        await t.run("a", boom)
    snap = t.snapshot()
    assert snap["phase"] == "failed" and not snap["ready"]
    assert "A failed" in snap["error"] and "no db" in snap["error"]
    assert snap["steps"][1]["status"] == "pending"
    t.finish()  # must not flip a failed boot to ready
    assert t.phase == "failed"


# --- gate -----------------------------------------------------------------------


def _gated_app(tracker: StartupTracker | None) -> Starlette:
    async def ok(request):
        return JSONResponse({"ok": True})

    async def ws(websocket):
        await websocket.accept()
        await websocket.send_text("hi")
        await websocket.close()

    app = Starlette(
        routes=[
            Route("/api/health", ok),
            Route("/health", ok),
            Route("/api/thing", ok),
            WebSocketRoute("/ws", ws),
        ]
    )
    app.add_middleware(ReadinessGate)
    if tracker is not None:
        app.state.startup = tracker
    return app


async def test_gate_blocks_http_until_ready_but_allows_health():
    tracker = StartupTracker((("a", "A"),))
    tracker.begin("a")
    app = _gated_app(tracker)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/thing")
        assert r.status_code == 503
        assert r.headers["retry-after"] == "2"
        body = r.json()
        assert body["error"]["code"] == "backend_starting"
        assert "A" in body["error"]["message"]
        assert body["startup"]["current_step"] == "a"

        assert (await c.get("/api/health")).status_code == 200
        assert (await c.get("/health")).status_code == 200

        tracker.done("a")
        tracker.finish()
        assert (await c.get("/api/thing")).status_code == 200


async def test_gate_reports_failed_boot():
    tracker = StartupTracker((("a", "A"),))

    async def boom() -> None:
        raise RuntimeError("kaput")

    with pytest.raises(RuntimeError):
        await tracker.run("a", boom)
    app = _gated_app(tracker)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/thing")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "backend_failed"
        assert "kaput" in r.json()["error"]["message"]


async def test_gate_is_noop_without_tracker():
    app = _gated_app(None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/thing")).status_code == 200


def test_gate_rejects_websocket_while_booting_and_allows_after():
    tracker = StartupTracker((("a", "A"),))
    tracker.begin("a")
    app = _gated_app(tracker)
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws"):
            pass
    assert exc.value.code == 1013

    tracker.done("a")
    tracker.finish()
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_text() == "hi"


# --- wiring in the real app -------------------------------------------------------


def test_app_exposes_health_under_api_prefix_and_gate():
    from backend.app.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert {"/health", "/api/health"} <= paths
    assert any(m.cls is ReadinessGate for m in app.user_middleware)
