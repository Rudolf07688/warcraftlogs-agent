"""Shared fake Warcraft Logs client for tool tests (feature 009).

``install(monkeypatch, responder)`` replaces ``get_client`` in every ``wcl_agent``
module that binds it, so a tool under test never touches the network. The
``responder(query, variables)`` callable returns the JSON payload for a query —
tests dispatch on the GraphQL text.

``mock_async_client(handler)`` builds a real ``AsyncWCLClient`` over an
``httpx.MockTransport`` (feature 013), for tests of the client itself. The token
endpoint is answered automatically; ``handler(request)`` sees only GraphQL posts.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from wcl_agent import report_tools, tools, wcl_client

Responder = Callable[[str, dict[str, Any]], dict[str, Any]]


class FakeClient:
    def __init__(self, responder: Responder):
        self._responder = responder
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = variables or {}
        self.calls.append((query, variables))
        return self._responder(query, variables)

    def count(self, needle: str) -> int:
        return sum(1 for q, _ in self.calls if needle in q)


def install(monkeypatch, responder: Responder) -> FakeClient:
    fake = FakeClient(responder)
    for module in (report_tools, tools, wcl_client):
        monkeypatch.setattr(module, "get_client", lambda: fake)
    return fake


def rate_limit_payload(remaining: float, limit: int = 720) -> dict[str, Any]:
    return {
        "data": {
            "rateLimitData": {
                "limitPerHour": limit,
                "pointsSpentThisHour": limit - remaining,
                "pointsResetIn": 1800,
            }
        }
    }


def gql_response(payload: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(payload).encode())


def mock_async_client(
    handler: Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]],
    *,
    client_id: str = "test-client",
    tokens: list[str] | None = None,
) -> wcl_client.AsyncWCLClient:
    """An ``AsyncWCLClient`` whose HTTP goes to ``handler``; tokens come from ``tokens``."""
    issued = iter(tokens or [f"tok{i}" for i in range(1, 100)])

    async def route(request: httpx.Request) -> httpx.Response:
        if str(request.url) == wcl_client.TOKEN_URL:
            return httpx.Response(200, json={"access_token": next(issued)})
        result = handler(request)
        if isinstance(result, Awaitable):
            result = await result
        return result

    wcl_client._tokens.pop(client_id, None)
    return wcl_client.AsyncWCLClient(client_id, "secret", transport=httpx.MockTransport(route))
