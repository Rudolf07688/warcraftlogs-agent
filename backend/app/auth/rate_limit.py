"""In-process rate limiting (feature 006, research R7).

Progressive login throttling (per account + per source) and a fixed-window cap for public
token endpoints. Behind a small interface so a shared backend (Redis/Postgres) can replace
it when the app scales past one process — the single-process limitation is a recorded
Complexity-Tracking item, not a hidden one.

Delays are **capped** (never a permanent lockout) and responses never distinguish a known
from an unknown account (the caller returns the same generic error either way).
"""

from __future__ import annotations

import ipaddress
import logging
import time
from typing import Protocol

from starlette.requests import Request

from ..config import settings

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    def record_failure(self, key: str) -> None: ...
    def record_success(self, key: str) -> None: ...
    def retry_after(self, key: str) -> float: ...
    def allow_request(self, key: str) -> bool: ...


class InProcessRateLimiter:
    """Thread-unaware, single-process limiter. Adequate at the current scale (R7)."""

    def __init__(
        self,
        *,
        failure_threshold: int | None = None,
        max_delay_s: int | None = None,
        per_minute: int | None = None,
    ) -> None:
        self._failure_threshold = (
            failure_threshold
            if failure_threshold is not None
            else settings.login_failure_block_threshold
        )
        self._max_delay_s = (
            max_delay_s if max_delay_s is not None else settings.login_block_max_delay_s
        )
        self._per_minute = (
            per_minute if per_minute is not None else settings.rate_limit_token_per_minute
        )
        self._failures: dict[str, int] = {}
        self._blocked_until: dict[str, float] = {}
        self._windows: dict[str, tuple[float, int]] = {}

    def record_failure(self, key: str) -> None:
        n = self._failures.get(key, 0) + 1
        self._failures[key] = n
        if n >= self._failure_threshold:
            # Exponential backoff past the threshold, capped — never permanent.
            delay = min(self._max_delay_s, 2 ** (n - self._failure_threshold))
            self._blocked_until[key] = time.monotonic() + delay

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)
        self._blocked_until.pop(key, None)

    def retry_after(self, key: str) -> float:
        """Seconds the caller must wait before another attempt (0.0 if allowed now)."""
        until = self._blocked_until.get(key)
        if until is None:
            return 0.0
        return max(0.0, until - time.monotonic())

    def allow_request(self, key: str) -> bool:
        """Fixed-window per-minute cap for public token endpoints. False = over limit."""
        now = time.monotonic()
        start, count = self._windows.get(key, (now, 0))
        if now - start >= 60.0:
            start, count = now, 0
        count += 1
        self._windows[key] = (start, count)
        return count <= self._per_minute


def client_source(request: Request) -> str:
    """The client address the per-source limits key on (sc-158).

    The direct peer, unless it is a configured trusted proxy (``TRUSTED_PROXIES``); then
    the nearest ``X-Forwarded-For`` hop that isn't one. That is the address our own proxy
    saw, whereas the leftmost entries are whatever the client sent. With no trusted
    proxies, forwarded headers are ignored. Hops may carry a port (``1.2.3.4:5678``,
    ``[2001:db8::1]:443``), and IPv4-mapped addresses count as IPv4 (QA BUG-003). A chain
    of trusted hops only keys on the peer, never on a client-written entry (QA SEC-002).
    """
    peer = request.client.host if request.client else "unknown"
    peer_addr = _address(peer)
    if peer_addr is None:
        return peer
    trusted = settings.trusted_proxy_networks
    if not _trusted(peer_addr, trusted):
        return str(peer_addr)
    hops = [
        hop.strip()
        for header in request.headers.getlist("x-forwarded-for")
        for hop in header.split(",")
        if hop.strip()
    ]
    for hop in reversed(hops):
        addr = _address(hop)
        if addr is None:
            # A trusted proxy writes a real address; anything else keeps the safe peer key.
            _warn_unparsable(hop)
            return str(peer_addr)
        if not _trusted(addr, trusted):
            return str(addr)
    return str(peer_addr)


def _address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """``host`` as an IP address, without a port; an IPv4-mapped IPv6 becomes IPv4."""
    host = host.strip()
    if host.startswith("["):  # [v6] or [v6]:port
        host = host[1 : host.find("]")] if "]" in host else ""
    elif host.count(":") == 1:  # v4:port (a bare v6 has several colons)
        host = host.split(":", 1)[0]
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return addr.ipv4_mapped
    return addr


def _trusted(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    return any(addr in net for net in networks)


_warned_unparsable = False


def _warn_unparsable(hop: str) -> None:
    """Once per process: a trusted proxy sent a hop we can't read, so clients share its key."""
    global _warned_unparsable
    if not _warned_unparsable:
        _warned_unparsable = True
        logger.warning(
            "X-Forwarded-For hop %r from a trusted proxy is not an IP address; "
            "rate limits fall back to the proxy's address", hop[:64]
        )


# Process-wide default instances. The login limiter keys on account+source; the token
# limiter keys on source for the public invite/reset endpoints.
login_limiter = InProcessRateLimiter()
token_limiter = InProcessRateLimiter()
# Per-user cap on manual spec-guide generation (feature 008 / US2, FR-014). Keyed by user_id.
guide_limiter = InProcessRateLimiter(per_minute=settings.wcl_guide_generate_per_minute)
# Feature 015: per-user cap on "report an inaccuracy".
guide_report_limiter = InProcessRateLimiter(per_minute=settings.wcl_guide_report_per_minute)
# 052 sc-352: per-user cap on recent-raid investigations. Keyed by user_id.
investigate_limiter = InProcessRateLimiter(per_minute=settings.wcl_investigate_per_minute)
