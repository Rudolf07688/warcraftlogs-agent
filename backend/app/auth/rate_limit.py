"""In-process rate limiting (feature 006, research R7).

Progressive login throttling (per account + per source) and a fixed-window cap for public
token endpoints. Behind a small interface so a shared backend (Redis/Postgres) can replace
it when the app scales past one process — the single-process limitation is a recorded
Complexity-Tracking item, not a hidden one.

Delays are **capped** (never a permanent lockout) and responses never distinguish a known
from an unknown account (the caller returns the same generic error either way).
"""

from __future__ import annotations

import time
from typing import Protocol

from ..config import settings


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


# Process-wide default instances. The login limiter keys on account+source; the token
# limiter keys on source for the public invite/reset endpoints.
login_limiter = InProcessRateLimiter()
token_limiter = InProcessRateLimiter()
# Per-user cap on manual spec-guide generation (feature 008 / US2, FR-014). Keyed by user_id.
guide_limiter = InProcessRateLimiter(per_minute=settings.wcl_guide_generate_per_minute)
