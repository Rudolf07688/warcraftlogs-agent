"""Thin Warcraft Logs v2 API client.

Reuses the OAuth2 client-credentials + GraphQL logic proven in the original
``app.py``. Exposes a process-wide singleton (:func:`get_client`) so the menu
and every agent tool share one authenticated client (the bearer token is cached
in-process for its ~1 year lifetime).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests

from .cache import cache_key, get_cache, is_rate_limit, ttl_for

TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
GRAPHQL_URL = "https://www.warcraftlogs.com/api/v2/client"


@dataclass
class WCLClient:
    """Authenticates against Warcraft Logs and runs GraphQL queries."""

    client_id: str
    client_secret: str
    access_token: str | None = None

    def authenticate(self) -> str:
        resp = requests.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        resp.raise_for_status()
        self.access_token = resp.json()["access_token"]
        return self.access_token

    def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        # US4: transparent read-through cache. A hit returns a deep copy and spends no
        # network / WCL API points; `rateLimitData` always bypasses (it IS the budget).
        # On a miss behavior is identical to an uncached call.
        variables = variables or {}
        cache = get_cache()
        key: str | None = None
        if not is_rate_limit(query):
            key = cache_key(query, variables)
            hit = cache.get(key)
            if hit is not None:
                return hit

        if not self.access_token:
            self.authenticate()
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise RuntimeError(json.dumps(payload["errors"], indent=2))
        if key is not None:
            cache.set(key, payload, ttl_for(query, variables))
        return payload


_client: WCLClient | None = None


def get_client() -> WCLClient:
    """Return the shared authenticated client, creating it on first use.

    Reads ``WCL_CLIENT_ID`` / ``WCL_CLIENT_SECRET`` from the environment.
    """
    global _client
    if _client is None:
        client_id = os.getenv("WCL_CLIENT_ID")
        client_secret = os.getenv("WCL_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError(
                "WCL_CLIENT_ID and WCL_CLIENT_SECRET must be set "
                "(create an API client at https://www.warcraftlogs.com/api/clients/)."
            )
        _client = WCLClient(client_id, client_secret)
    return _client


def check_rate_limit() -> dict[str, Any]:
    """Return the current API points budget (limit / spent / reset seconds)."""
    query = "{ rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn } }"
    data = get_client().query(query)
    return data["data"]["rateLimitData"]
