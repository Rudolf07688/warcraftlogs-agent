"""Warcraft Logs v2 API client: native async, with interactive and background lanes.

OAuth2 client credentials + GraphQL over ``httpx.AsyncClient`` (feature 013, QA PERF-201).
One :class:`AsyncWCLClient` per event loop (:func:`get_async_client`), so asyncio primitives
and HTTP pools are never shared across loops. Every query goes through
:meth:`AsyncWCLClient.query`, the single chokepoint for caching, single-flight, timeouts and
the lane limiter (contracts/wcl-async-client.md G1-G9).

Lanes (PERF-211): background work (guides, the patch lookup, recent raids) runs inside
:func:`background_lane` and may hold at most ``WCL_BACKGROUND_CONCURRENCY`` of the
``WCL_MAX_CONCURRENCY`` slots, and never takes a slot while a chat lookup is waiting.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import weakref
from collections import deque
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Any, Literal

import httpx

from .cache import _env_int, cache_key, get_cache, is_rate_limit, ttl_for

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
GRAPHQL_URL = "https://www.warcraftlogs.com/api/v2/client"

# One cap for the whole process (per loop) on WCL requests in flight (PERF-001/002).
DEFAULT_MAX_CONCURRENCY = 6
DEFAULT_BACKGROUND_CONCURRENCY = 2
# Upper bound for one query: the wait for a slot plus the request (FR-021).
DEFAULT_QUERY_TIMEOUT_S = 75
# PERF-003: a hung connect fails fast; slow queries keep 60 s.
HTTP_TIMEOUT = httpx.Timeout(60, connect=5)
# Payloads above this are parsed off the loop so a big report can't stall streaming.
_PARSE_OFF_LOOP_BYTES = 256_000

Lane = Literal["interactive", "background"]
_lane: ContextVar[Lane] = ContextVar("wcl_lane", default="interactive")


@contextmanager
def background_lane() -> Iterator[None]:
    """Run WCL calls made in this context (and tasks it starts) in the background lane."""
    token = _lane.set("background")
    try:
        yield
    finally:
        _lane.reset(token)


class LaneLimiter:
    """Caps WCL requests in flight, keeping background work out of the interactive lane's way.

    Rules (contracts/wcl-async-client.md L1-L3): an interactive caller takes a slot whenever
    one is free; a background caller only when one is free, background holds fewer than
    ``background_cap`` and no interactive caller is waiting. Slots are handed to waiters in
    FIFO order on release. Release is synchronous, so a cancelled holder always frees its slot.
    """

    def __init__(self, total: int, background_cap: int):
        self.total = max(1, total)
        self.background_cap = max(1, min(background_cap, self.total - 1)) if self.total > 1 else 1
        self.in_use = 0
        self.bg_in_use = 0
        self._waiters: deque[tuple[Lane, asyncio.Future[None]]] = deque()

    @property
    def interactive_waiting(self) -> int:
        return sum(1 for lane, fut in self._waiters if lane == "interactive" and not fut.done())

    def _can_take(self, lane: Lane) -> bool:
        if self.in_use >= self.total:
            return False
        if lane == "background":
            return self.bg_in_use < self.background_cap and self.interactive_waiting == 0
        return True

    def _take(self, lane: Lane) -> None:
        self.in_use += 1
        if lane == "background":
            self.bg_in_use += 1

    def _wake(self) -> None:
        """Hand free slots to waiters, oldest first, each by its own lane's rule."""
        progressed = True
        while progressed:
            progressed = False
            for lane, fut in list(self._waiters):
                if fut.done():
                    self._waiters.remove((lane, fut))
                    continue
                if self._can_take(lane):
                    self._waiters.remove((lane, fut))
                    self._take(lane)
                    fut.set_result(None)
                    progressed = True
                    break

    async def acquire(self, lane: Lane | None = None) -> Lane:
        lane = lane or _lane.get()
        # Only jump in when nobody is queued, so FIFO order holds within the rules.
        if not self._waiters and self._can_take(lane):
            self._take(lane)
            return lane
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters.append((lane, fut))
        self._wake()  # queued waiters may all be ineligible (e.g. background at its cap)
        try:
            await fut
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self.release(lane)  # granted just as we were cancelled: give it back
            else:
                fut.cancel()
                self._wake()  # a leaving interactive waiter may unblock background
            raise
        return lane

    def release(self, lane: Lane) -> None:
        self.in_use -= 1
        if lane == "background":
            self.bg_in_use -= 1
        self._wake()

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[Lane]:
        lane = await self.acquire()
        try:
            yield lane
        finally:
            self.release(lane)


_limiters: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, LaneLimiter] = (
    weakref.WeakKeyDictionary()
)


def _limiter() -> LaneLimiter:
    """The lane limiter for the running loop (L5: one per loop)."""
    loop = asyncio.get_running_loop()
    limiter = _limiters.get(loop)
    if limiter is None:
        total = _env_int("WCL_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY)
        bg = _env_int("WCL_BACKGROUND_CONCURRENCY", DEFAULT_BACKGROUND_CONCURRENCY)
        limiter = _limiters[loop] = LaneLimiter(total, bg)
    return limiter


def _query_timeout() -> int:
    return max(1, _env_int("WCL_QUERY_TIMEOUT_S", DEFAULT_QUERY_TIMEOUT_S))


# Bearer tokens by client id, shared across loops: a token is valid ~1 year, so a fresh
# loop (CLI, tests) reuses it instead of authenticating again.
_tokens: dict[str, str] = {}


async def _loads(content: bytes) -> dict[str, Any]:
    if len(content) > _PARSE_OFF_LOOP_BYTES:
        return await asyncio.to_thread(json.loads, content)
    return json.loads(content)


class AsyncWCLClient:
    """Authenticates against Warcraft Logs and runs GraphQL queries on one event loop."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT, limits=httpx.Limits(max_connections=16), transport=transport
        )
        self._auth_lock = asyncio.Lock()
        # Single-flight (G3/G4): cache key -> [shared fetch task, waiter count].
        self._flights: dict[str, list[Any]] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def query(
        self, query: str, variables: dict[str, Any] | None = None, *, cache: bool = True
    ) -> dict[str, Any]:
        """Run a GraphQL query and return its payload (a fresh dict, owned by the caller)."""
        variables = variables or {}
        if not cache or is_rate_limit(query):
            return await _loads(await self._fetch(query, variables, None))
        key = cache_key(query, variables)
        while True:
            hit = get_cache().get(key)
            if hit is not None:
                return await _loads(hit)
            flight = self._flights.get(key)
            if flight is None:
                task = asyncio.ensure_future(self._fetch(query, variables, key))
                flight = self._flights[key] = [task, 0]
                task.add_done_callback(lambda t, k=key: self._drop_flight(k, t))
            task = flight[0]
            flight[1] += 1
            try:
                content = await asyncio.shield(task)
            except asyncio.CancelledError:
                me = asyncio.current_task()
                if me is not None and me.cancelling():
                    raise
                continue  # the shared fetch was abandoned by its other waiters: start over
            finally:
                flight[1] -= 1
                if flight[1] == 0 and not task.done():
                    # The last waiter left: stop the fetch and free its slot (G4).
                    self._drop_flight(key, task)
                    task.cancel()
            return await _loads(content)

    def _drop_flight(self, key: str, task: asyncio.Future[Any]) -> None:
        flight = self._flights.get(key)
        if flight is not None and flight[0] is task:
            del self._flights[key]

    async def _token(self, stale: str | None = None) -> str:
        token = _tokens.get(self.client_id)
        if token and token != stale:
            return token
        async with self._auth_lock:  # concurrent first calls fetch one token
            token = _tokens.get(self.client_id)
            if token and token != stale:
                return token
            resp = await self._http.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
            )
            resp.raise_for_status()
            token = _tokens[self.client_id] = resp.json()["access_token"]
            return token

    async def _post(self, query: str, variables: dict[str, Any], token: str) -> httpx.Response:
        return await self._http.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {token}"},
        )

    async def _fetch(self, query: str, variables: dict[str, Any], key: str | None) -> bytes:
        async with asyncio.timeout(_query_timeout()):
            token = await self._token()
            limiter = _limiter()
            async with limiter.slot() as lane:
                logger.debug("wcl inflight=%d lane=%s", limiter.in_use, lane)
                resp = await self._post(query, variables, token)
                if resp.status_code == 401:  # expired or revoked: refresh once and retry
                    token = await self._token(stale=token)
                    resp = await self._post(query, variables, token)
        resp.raise_for_status()
        content = resp.content
        if b'"errors"' in content:
            payload = json.loads(content)
            if "errors" in payload:
                raise RuntimeError(json.dumps(payload["errors"], indent=2))
        if key is not None:
            get_cache().set(key, content, ttl_for(query, variables), size=len(content))
        return content


_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncWCLClient] = (
    weakref.WeakKeyDictionary()
)


def get_async_client() -> AsyncWCLClient:
    """Return the client for the running event loop, creating it on first use.

    Reads ``WCL_CLIENT_ID`` / ``WCL_CLIENT_SECRET`` from the environment. Call on the loop.
    """
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None:
        client_id = os.getenv("WCL_CLIENT_ID")
        client_secret = os.getenv("WCL_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError(
                "WCL_CLIENT_ID and WCL_CLIENT_SECRET must be set "
                "(create an API client at https://www.warcraftlogs.com/api/clients/)."
            )
        client = _clients[loop] = AsyncWCLClient(client_id, client_secret)
    return client


async def aclose_clients() -> None:
    """Close every loop's client and HTTP pool (FastAPI lifespan shutdown)."""
    clients = list(_clients.items())
    _clients.clear()
    for _loop, client in clients:
        await client.aclose()


RATE_LIMIT_QUERY = "{ rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn } }"


async def acheck_rate_limit() -> dict[str, Any]:
    """Return the current API points budget (limit / spent / reset seconds)."""
    data = await get_async_client().query(RATE_LIMIT_QUERY)
    return data["data"]["rateLimitData"]
