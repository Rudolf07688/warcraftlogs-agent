"""In-process TTL + LRU cache for Warcraft Logs queries (feature 005 / US4).

Sits behind the single ``WCLClient.query`` chokepoint, so every tool (and
``run_wcl_graphql``) is cached transparently — one integration point, no per-tool
changes (DRY). A cache hit performs no network I/O and spends zero WCL API points.

Two freshness tiers (see contracts/caching.md):
* report-scoped queries are effectively immutable → long TTL (~24h),
* everything else (leaderboards/rankings) is volatile → short TTL (~1h),
* ``rateLimitData`` is never cached (always live).

Deliberately dependency-light and standalone (no backend/DB imports), so the
``wcl_agent`` package keeps running on its own.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from contextvars import ContextVar
from copy import deepcopy
from typing import Any, Callable

DEFAULT_MAXSIZE = 512

# feature 006: a caller-supplied scope prefix (e.g. the tenant id) folded into every cache
# key so cached lookups never cross scopes (FR-019). The backend sets this per chat turn;
# wcl_agent stays standalone (no DB import) — it only reads a string. Propagates into ADK's
# sync tool worker because asyncio.to_thread copies the context.
_scope_prefix: ContextVar[str] = ContextVar("wcl_cache_scope_prefix", default="")


def set_scope_prefix(prefix: str) -> None:
    """Set the per-context cache scope prefix (call before running a scoped turn)."""
    _scope_prefix.set(prefix or "")


def get_scope_prefix() -> str:
    return _scope_prefix.get()
DEFAULT_TTL_REPORT_S = 86400
DEFAULT_TTL_LEADERBOARD_S = 3600


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def report_ttl() -> int:
    return _env_int("WCL_CACHE_TTL_REPORT_S", DEFAULT_TTL_REPORT_S)


def leaderboard_ttl() -> int:
    return _env_int("WCL_CACHE_TTL_LEADERBOARD_S", DEFAULT_TTL_LEADERBOARD_S)


def cache_key(query: str, variables: dict[str, Any] | None, prefix: str | None = None) -> str:
    """Stable key over the scope prefix + full query + all variables (sorted), per FR-020.

    ``prefix`` defaults to the current context scope prefix (feature 006), so cached WCL
    lookups are never shared across tenants.
    """
    scope = prefix if prefix is not None else get_scope_prefix()
    serialized = json.dumps(variables or {}, sort_keys=True, default=str)
    return hashlib.sha256(f"{scope}\x1f{query} {serialized}".encode()).hexdigest()


def is_rate_limit(query: str) -> bool:
    """rateLimitData must never be cached (it's the live budget)."""
    return "rateLimitData" in query


def is_report_scoped(query: str, variables: dict[str, Any] | None) -> bool:
    """Report-scoped (immutable) vs leaderboard/other (volatile)."""
    if "reportData" in query or "report(" in query:
        return True
    return bool(variables and "code" in variables)


def ttl_for(query: str, variables: dict[str, Any] | None) -> int:
    return report_ttl() if is_report_scoped(query, variables) else leaderboard_ttl()


class TTLCache:
    """A small LRU cache with per-entry TTL and lazy expiry on read."""

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE, clock: Callable[[], float] = time.monotonic):
        self._data: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()
        self.maxsize = maxsize
        self._clock = clock

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires_at = item
        if self._clock() >= expires_at:
            del self._data[key]  # lazy expiry
            return None
        self._data.move_to_end(key)
        return deepcopy(value)  # callers can't mutate the stored entry

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._data[key] = (deepcopy(value), self._clock() + ttl)
        self._data.move_to_end(key)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)  # evict least-recently-used

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


_cache = TTLCache()


def get_cache() -> TTLCache:
    """Return the process-wide WCL query cache."""
    return _cache
