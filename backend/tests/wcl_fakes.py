"""Shared fake Warcraft Logs client for tool tests (feature 009).

``install(monkeypatch, responder)`` replaces ``get_client`` in every ``wcl_agent``
module that binds it, so a tool under test never touches the network. The
``responder(query, variables)`` callable returns the JSON payload for a query —
tests dispatch on the GraphQL text.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
