"""Minimal backend tests (no DB required).

Covers the model-listing endpoint and schema validation. Conversation CRUD and
the WebSocket stream are exercised live in quickstart.md against a real Postgres.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from backend.app.main import app
from backend.app.schemas import ChatTurn


async def test_models_endpoint_returns_list_and_default():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/models")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["models"], list)
    assert body["default"]


def test_chatturn_rejects_empty_content():
    with pytest.raises(ValidationError):
        ChatTurn(model="gemini-3.6-flash", content="")


def test_chatturn_accepts_valid():
    turn = ChatTurn(model="gemini-3.6-flash", content="hi")
    assert turn.conversation_id is None
    assert turn.content == "hi"


def test_ws_module_has_required_names_bound():
    # Guard against missing imports used inside _handle_turn (which no offline test
    # can execute, since it needs Postgres + ADK). Catches NameErrors at the surface.
    from backend.app.api import ws

    for name in ("TurnScratch", "generate_followups", "SuggestionsFrame"):
        assert hasattr(ws, name), f"ws.py is missing `{name}`"


# --- US4/US6: tool_end handling (encounters frame + summary/ms) ----------------


class _FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload):
        self.sent.append(payload)


_FIGHTS_RESULT = {
    "status": "success",
    "zone": {"id": 1, "name": "Nerub-ar Palace"},
    "fights": [
        {"id": 1, "name": "Ulgrax", "encounterID": 2902, "difficulty": 5, "kill": True},
        {"id": 2, "name": "Ulgrax", "encounterID": 2902, "difficulty": 5, "kill": False},
        {"id": 3, "name": "Trash", "encounterID": 0, "kill": False},
    ],
}


async def test_handle_tool_end_emits_encounters_and_telemetry(session, monkeypatch):
    from backend.app.api import ws as ws_mod
    from backend.app.services import raids as raids_service

    monkeypatch.setattr(raids_service, "get_report_metadata", lambda code: {"status": "error"})
    ws = _FakeWS()
    record = {
        "name": "get_report_fights",
        "ok": True,
        "args": {"report_code": "ABCD"},
        "result": _FIGHTS_RESULT,
        "ms": 812,
    }
    await ws_mod._handle_tool_end(ws, session, record, None)

    enc = [f for f in ws.sent if f.get("type") == "encounters"]
    assert len(enc) == 1
    assert enc[0]["report_code"] == "ABCD"
    assert [e["encounter_id"] for e in enc[0]["encounters"]] == [2902]  # deduped

    tool_end = next(f for f in ws.sent if f.get("type") == "tool_end")
    assert tool_end["ms"] == 812  # US6 elapsed
    assert tool_end.get("summary")  # US6 human-readable summary


async def test_handle_tool_end_omits_encounters_for_trash_only(session, monkeypatch):
    from backend.app.api import ws as ws_mod
    from backend.app.services import raids as raids_service

    monkeypatch.setattr(raids_service, "get_report_metadata", lambda code: {"status": "error"})
    ws = _FakeWS()
    record = {
        "name": "get_report_fights",
        "ok": True,
        "args": {"report_code": "ABCD"},
        "result": {"status": "success", "fights": [{"id": 1, "encounterID": 0, "kill": False}]},
    }
    await ws_mod._handle_tool_end(ws, session, record, None)
    assert not any(f.get("type") == "encounters" for f in ws.sent)
