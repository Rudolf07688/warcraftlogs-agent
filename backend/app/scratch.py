"""Per-turn shared scratch store for tool outputs (US2).

When the model issues several tool calls in one turn, they run concurrently (ADK
worker threads). Each call's *complete* result is written here — one file per
`call_id` — so large payloads (full report tables, graph JSON) are preserved intact
and can be picked up once every call finishes, without being bound by any in-transit
frame size. The store is created at turn start and removed at turn end.

Concurrency-safe by construction: every call writes its own file via an atomic
temp-file + replace, so parallel writers never clobber one another.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from typing import Any

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_name(key: str) -> str:
    """Map an arbitrary call id to a filesystem-safe file stem."""
    return _SAFE.sub("_", key) or "unkeyed"


class TurnScratch:
    """A temporary directory holding one JSON file per tool call in a turn."""

    def __init__(self, turn_id: str) -> None:
        self.turn_id = turn_id
        self.dir = tempfile.mkdtemp(prefix=f"wcl-turn-{_safe_name(turn_id)}-")

    def _path(self, call_id: str) -> str:
        return os.path.join(self.dir, f"{_safe_name(call_id)}.json")

    def write(self, call_id: str, record: dict[str, Any]) -> str:
        """Atomically persist one tool call's full record; return its path."""
        path = self._path(call_id)
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(record, fh, default=str)
            os.replace(tmp, path)  # atomic: a reader sees whole file or nothing
        except BaseException:
            # Best effort: don't leak the temp file on failure.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return path

    def read(self, call_id: str) -> dict[str, Any] | None:
        """Return a previously written record, or None if absent/unreadable."""
        try:
            with open(self._path(call_id), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def cleanup(self) -> None:
        """Remove the scratch directory and all its files (idempotent)."""
        shutil.rmtree(self.dir, ignore_errors=True)
