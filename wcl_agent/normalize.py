"""Small pure helpers shared by the WCL tools, the cache keys and the backend (feature 014).

Kept import-free (no cache, no client), so ``cache`` and ``report_tools`` can both use them
without an import cycle.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# A report is finished (no longer being live-logged) this long after its last event.
# Feature 013 uses the same rule to stop re-fetching recent raids.
FINAL_AFTER = timedelta(hours=2)


def server_slug(server: str) -> str:
    """WCL realm slug: ``"Area 52"`` → ``"area-52"``, ``"Kel'Thuzad"`` → ``"kelthuzad"``."""
    return server.strip().lower().replace(" ", "-").replace("'", "")


def is_finished(end_time_ms: int, now: datetime | None = None) -> bool:
    """True when a report's last event is at least :data:`FINAL_AFTER` in the past."""
    now = now or datetime.now(timezone.utc)
    ended = datetime.fromtimestamp(end_time_ms / 1000, tz=timezone.utc)
    return now - ended >= FINAL_AFTER
