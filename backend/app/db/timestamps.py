"""Timestamps read back from the database (feature 029, PO decision D15).

SQLite (the test suite) returns ``DateTime(timezone=True)`` columns without a zone; the app
stores UTC everywhere, so a naive value is UTC. The older private copies of this rule are
moved here by Backlog chore sc-216.
"""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """``value`` with its zone; a naive timestamp (SQLite) is taken as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
