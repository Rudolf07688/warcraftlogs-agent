"""In-process registry of guide metadata for the WCL tools (feature 009, US5/US4).

The backend fills it at startup (every ``ready`` spec guide) and after each
successful guide generation; ``get_cooldown_usage`` reads it synchronously from an
ADK worker thread. ``wcl_agent`` never imports the backend (dependency direction is
backend → wcl_agent), so this tiny registry is the transport (research R7). The CLI
leaves it empty, and the tools fall back to rate-only coaching.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GuideCooldown:
    name: str
    spell_id: int | None
    cooldown_s: float
    charges: int = 1
    talent_modified: bool = False


@dataclass(frozen=True)
class GuideMeta:
    class_name: str  # WCL PascalCase, e.g. "Mage"
    spec: str  # e.g. "Fire"
    game_patch: str | None
    generated_at: datetime | None
    cooldowns: tuple[GuideCooldown, ...] = ()


_registry: dict[tuple[str, str], GuideMeta] = {}
_lock = threading.Lock()


def _key(class_name: str, spec: str) -> tuple[str, str]:
    return (class_name or "").strip().casefold(), (spec or "").strip().casefold()


def set_guide_meta(meta: GuideMeta) -> None:
    with _lock:
        _registry[_key(meta.class_name, meta.spec)] = meta


def get_guide_meta(class_name: str, spec: str) -> GuideMeta | None:
    with _lock:
        return _registry.get(_key(class_name, spec))


def clear_guide_meta() -> None:
    """Tests only."""
    with _lock:
        _registry.clear()


def registry_size() -> int:
    with _lock:
        return len(_registry)
