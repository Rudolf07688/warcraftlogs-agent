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
