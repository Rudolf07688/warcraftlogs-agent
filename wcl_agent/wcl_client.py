"""Thin Warcraft Logs v2 API client.

Reuses the OAuth2 client-credentials + GraphQL logic proven in the original
``app.py``. Exposes a process-wide singleton (:func:`get_client`) so the menu
and every agent tool share one authenticated client (the bearer token is cached
in-process for its ~1 year lifetime).
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from .cache import _env_int, cache_key, get_cache, is_rate_limit, ttl_for

TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
GRAPHQL_URL = "https://www.warcraftlogs.com/api/v2/client"

# PERF-001/002: tools now run in threads and fan out inside a tool, so cap how many WCL
# requests are in flight at once across the whole process (one cap for both sources).
DEFAULT_MAX_CONCURRENCY = 6
_inflight = threading.BoundedSemaphore(max(1, _env_int("WCL_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY)))

# PERF-003: (connect, read) timeouts. A hung connect fails fast; slow queries keep 60 s.
QUERY_TIMEOUT = (5, 60)
AUTH_TIMEOUT = (5, 30)
# How long a caller waits for another thread's identical in-flight query (PERF-009).
_FLIGHT_WAIT_S = 90


def _make_session() -> requests.Session:
    """One pooled HTTP session per client: reuses TCP+TLS connections across queries."""
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=2, pool_maxsize=16)
    session.mount("https://", adapter)
    return session


@dataclass
class WCLClient:
    """Authenticates against Warcraft Logs and runs GraphQL queries."""

    client_id: str
    client_secret: str
    access_token: str | None = None
    _auth_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _http: requests.Session = field(default_factory=_make_session, repr=False, compare=False)
    # PERF-009 single-flight: cache key -> event set when the leading fetch finishes.
    _flights: dict[str, threading.Event] = field(default_factory=dict, repr=False, compare=False)
    _flights_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def authenticate(self) -> str:
        resp = self._http.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=AUTH_TIMEOUT,
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
        if is_rate_limit(query):
            return self._fetch(query, variables, None)
        key = cache_key(query, variables)
        hit = cache.get(key)
        if hit is not None:
            return hit

        # Single-flight: concurrent identical queries (now common, with tools running in
        # parallel) wait for the first one and read its cached result instead of refetching.
        with self._flights_lock:
            event = self._flights.get(key)
            leader = event is None
            if leader:
                event = self._flights[key] = threading.Event()
        if not leader:
            event.wait(_FLIGHT_WAIT_S)
            hit = cache.get(key)
            if hit is not None:
                return hit
            return self._fetch(query, variables, key)  # the leader failed: fetch ourselves
        try:
            return self._fetch(query, variables, key)
        finally:
            with self._flights_lock:
                self._flights.pop(key, None)
            event.set()

    def _fetch(self, query: str, variables: dict[str, Any], key: str | None) -> dict[str, Any]:
        cache = get_cache()
        if not self.access_token:
            with self._auth_lock:  # concurrent first calls fetch one token
                if not self.access_token:
                    self.authenticate()
        with _inflight:
            resp = self._http.post(
                GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=QUERY_TIMEOUT,
            )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise RuntimeError(json.dumps(payload["errors"], indent=2))
        if key is not None:
            cache.set(key, payload, ttl_for(query, variables), size=len(resp.content or b""))
        return payload


_client: WCLClient | None = None
_client_lock = threading.Lock()


def get_client() -> WCLClient:
    """Return the shared authenticated client, creating it on first use.

    Reads ``WCL_CLIENT_ID`` / ``WCL_CLIENT_SECRET`` from the environment.
    """
    global _client
    if _client is None:
        with _client_lock:  # tools call this from several threads at once
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
