"""Warcraft Logs v2 API client: native async, with interactive and background lanes.

OAuth2 client credentials + GraphQL over ``httpx.AsyncClient`` (feature 013, QA PERF-201).
One :class:`AsyncWCLClient` per event loop (:func:`get_async_client`), so asyncio primitives
and HTTP pools are never shared across loops. Every query goes through
:meth:`AsyncWCLClient.query`, the single chokepoint for single-flight, timeouts, retries,
API-cost logging and the lane limiter (contracts/wcl-async-client.md G1-G9). Result caching
moved out in feature 014: callers use the typed key families in :mod:`wcl_agent.cache`.

Lanes (PERF-211): background work (guides, the patch lookup, recent raids) runs inside
:func:`background_lane` and may hold at most ``WCL_BACKGROUND_CONCURRENCY`` of the
``WCL_MAX_CONCURRENCY`` slots, and never takes a slot while a chat lookup is waiting.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import time
import weakref
from collections import deque
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from .cache import CacheFamily, _env_int, aclose_redis, get_or_load, keys
from .cache_models import OAuthToken

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


# Bearer tokens by client id, shared across loops: a fresh loop (CLI, tests) reuses one
# instead of authenticating again. Feature 014: the memo sits in front of the shared
# ``oauth_token`` cache entry, so a Redis outage never means an OAuth request per WCL call.
_tokens: dict[str, OAuthToken] = {}
_TOKEN_MARGIN_S = 60  # renew this long before expiry
_DEFAULT_TOKEN_LIFETIME_S = 3600  # if the token response has no expires_in

# feature 014 (FR-017): retry rate-limited and server errors, with backoff.
MAX_RETRIES = 2
_MAX_RETRY_AFTER_S = 10.0

# feature 014 (FR-016): every request also asks for the hour's points budget, under an
# alias that can't clash with a caller's own rateLimitData selection. The latest snapshot
# answers rate-limit checks without a request of their own (PERF-009).
_COST_ALIAS = "_cost"
_COST_FIELD = f"{_COST_ALIAS}: rateLimitData {{ limitPerHour pointsSpentThisHour pointsResetIn }}"
_COST_RE = re.compile(rb'"_cost"\s*:\s*(\{[^{}]*\})')
_OP_RE = re.compile(r"^\s*query\s+(\w+)")
_last_points: float | None = None
BUDGET_MAX_AGE_S = 30.0  # a snapshot younger than this answers acheck_rate_limit


@dataclass(frozen=True)
class _Budget:
    limit_per_hour: float
    spent_this_hour: float
    reset_in_s: float
    seen_at: float  # time.monotonic()


_budget: _Budget | None = None
# After a 429 whose Retry-After is longer than we'd wait, every call fails fast until then
# instead of retrying into a budget that is already spent (PERF-004).
_blocked_until = 0.0


def _with_cost(query: str) -> str:
    """Insert the cost field into the operation's top-level selection set.

    Queries with fragments are left alone: their first top-level ``{`` may not be the
    operation's.
    """
    if "fragment " in query:
        return query
    depth = 0
    for i, ch in enumerate(query):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "{" and depth == 0:
            return f"{query[: i + 1]} {_COST_FIELD}{query[i + 1 :]}"
    return query


def _log_cost(query: str, content: bytes) -> None:
    """Log the points this hour and the change since this process last saw them, and keep
    the budget snapshot."""
    global _last_points, _budget
    match = _COST_RE.search(content)
    if match is None:
        return
    try:
        cost = json.loads(match.group(1))
        points = float(cost["pointsSpentThisHour"])
    except (ValueError, KeyError, TypeError):
        return
    try:
        _budget = _Budget(
            float(cost["limitPerHour"]), points, float(cost["pointsResetIn"]), time.monotonic()
        )
    except (KeyError, TypeError, ValueError):
        pass
    last = _last_points
    _last_points = points
    # Points reset hourly: a drop means a new hour, so the whole value is this request's.
    delta = "-" if last is None else f"{points - last if points >= last else points:g}"
    op = _OP_RE.match(query)
    logger.info(
        "wcl_cost op=%s points_this_hour=%g delta=%s", op.group(1) if op else "anonymous", points, delta
    )


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def _retry_after(resp: httpx.Response) -> float | None:
    after = resp.headers.get("Retry-After")
    if not after:
        return None
    try:
        return max(0.0, float(after))
    except ValueError:
        return None


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    after = _retry_after(resp)
    if after is not None:
        return min(_MAX_RETRY_AFTER_S, after)
    return 0.5 * 2**attempt + random.uniform(0, 0.25)


def _blocked_response() -> httpx.Response:
    """A synthetic 429 for calls made while the budget is known to be spent."""
    wait = max(1, int(_blocked_until - time.monotonic()))
    return httpx.Response(
        429, headers={"Retry-After": str(wait)}, request=httpx.Request("POST", GRAPHQL_URL)
    )


def _flight_key(query: str, variables: dict[str, Any]) -> str:
    """Identity of a request for single-flight: the full query plus all variables, sorted."""
    serialized = json.dumps(variables, sort_keys=True, default=str)
    return hashlib.sha256(f"{query} {serialized}".encode()).hexdigest()


async def _loads(content: bytes) -> dict[str, Any]:
    if len(content) > _PARSE_OFF_LOOP_BYTES:
        payload = await asyncio.to_thread(json.loads, content)
    else:
        payload = json.loads(content)
    data = payload.get("data")
    if isinstance(data, dict):
        data.pop(_COST_ALIAS, None)  # injected by _with_cost; callers never see it
    return payload


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
        # Single-flight (G3/G4): request key -> [shared fetch task, waiter count].
        self._flights: dict[str, list[Any]] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a GraphQL query and return its payload (a fresh dict, owned by the caller).

        Results are not cached here (feature 014): callers that want caching go through
        ``cache.get_or_load`` with a typed key family. Identical concurrent queries still
        share one request (single-flight).
        """
        variables = variables or {}
        key = _flight_key(query, variables)
        while True:
            flight = self._flights.get(key)
            if flight is None:
                task = asyncio.ensure_future(self._fetch(query, variables))
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

    def _memo(self, stale: str | None) -> str | None:
        memo = _tokens.get(self.client_id)
        if memo is None or memo.access_token == stale:
            return None
        if memo.expires_at - _TOKEN_MARGIN_S <= time.time():
            return None
        return memo.access_token

    async def _token(self, stale: str | None = None) -> str:
        """Bearer token: process memo, then the shared ``oauth_token`` entry, then OAuth.

        ``stale`` is a token WCL just rejected (401): it is never returned again, and the
        shared entry is reloaded instead of read.
        """
        token = self._memo(stale)
        if token:
            return token
        async with self._auth_lock:  # concurrent first calls fetch one token
            token = self._memo(stale)
            if token:
                return token
            loaded = await get_or_load(
                CacheFamily.OAUTH_TOKEN,
                keys.OAUTH_TOKEN,
                OAuthToken,
                self._request_token,
                ttl=lambda t: int(t.expires_at - time.time()) - _TOKEN_MARGIN_S,
                force_refresh=stale is not None,
            )
            if loaded is None or loaded.access_token == stale:
                # Another process's copy was the rejected one: fetch our own.
                loaded = await self._request_token()
            _tokens[self.client_id] = loaded
            return loaded.access_token

    async def _request_token(self) -> OAuthToken:
        resp = await self._http.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
        )
        resp.raise_for_status()
        body = resp.json()
        lifetime = int(body.get("expires_in") or _DEFAULT_TOKEN_LIFETIME_S)
        return OAuthToken(access_token=body["access_token"], expires_at=time.time() + lifetime)

    async def _post(self, query: str, variables: dict[str, Any], token: str) -> httpx.Response:
        return await self._http.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {token}"},
        )

    async def _fetch(self, query: str, variables: dict[str, Any]) -> bytes:
        global _blocked_until
        if time.monotonic() < _blocked_until:
            _blocked_response().raise_for_status()
        sent = _with_cost(query)
        async with asyncio.timeout(_query_timeout()) as deadline:
            limiter = _limiter()
            for attempt in range(MAX_RETRIES + 1):
                token = await self._token()
                async with limiter.slot() as lane:
                    logger.debug("wcl inflight=%d lane=%s", limiter.in_use, lane)
                    resp = await self._post(sent, variables, token)
                    if resp.status_code == 401:  # expired or revoked: refresh once and retry
                        token = await self._token(stale=token)
                        resp = await self._post(sent, variables, token)
                if not _retryable(resp.status_code) or attempt == MAX_RETRIES:
                    break
                after = _retry_after(resp)
                if resp.status_code == 429 and after is not None and after > _MAX_RETRY_AFTER_S:
                    # The hourly budget is spent: retrying can't succeed, so fail now and let
                    # every other call fail fast until it resets (PERF-004).
                    _blocked_until = time.monotonic() + after
                    break
                # The backoff waits outside the slot, so it never holds back other queries.
                delay = _retry_delay(resp, attempt)
                when = deadline.when()
                if when is not None and delay >= when - asyncio.get_running_loop().time():
                    break  # the wait would outlast the query timeout: fail with this response
                logger.info("wcl %d, retry %d/%d in %.1fs", resp.status_code, attempt + 1, MAX_RETRIES, delay)
                await asyncio.sleep(delay)
        resp.raise_for_status()
        content = resp.content
        _log_cost(query, content)
        if b'"errors"' in content:
            payload = json.loads(content)
            if "errors" in payload:
                raise RuntimeError(json.dumps(payload["errors"], indent=2))
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
    """Close every loop's client and HTTP pool, and the cache's Redis clients (lifespan shutdown)."""
    clients = list(_clients.items())
    _clients.clear()
    for _loop, client in clients:
        await client.aclose()
    await aclose_redis()


RATE_LIMIT_QUERY = "{ rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn } }"


async def acheck_rate_limit(max_age_s: float = BUDGET_MAX_AGE_S) -> dict[str, Any]:
    """Return the current API points budget (limit / spent / reset seconds).

    Every WCL response carries the budget, so a snapshot younger than ``max_age_s`` answers
    without a request of its own (PERF-009).
    """
    budget = _budget
    if budget is not None:
        age = time.monotonic() - budget.seen_at
        if age <= max_age_s:
            return {
                "limitPerHour": budget.limit_per_hour,
                "pointsSpentThisHour": budget.spent_this_hour,
                "pointsResetIn": max(0, round(budget.reset_in_s - age)),
            }
    data = await get_async_client().query(RATE_LIMIT_QUERY)
    return data["data"]["rateLimitData"]
