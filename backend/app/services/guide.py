"""Background spec-guide / guild-summary generation (feature 005 / US6).

Locking a character or guild in the profile schedules a non-blocking task that:
1. resolves the character's active spec from Warcraft Logs (or the guild's identity),
2. generates a concise guide/summary via the web-search-capable guide model
   (reusing ``stream_response`` over a disposable session, like the greeting primer),
3. persists the result and flips ``guide_status``/``summary_status`` to ``ready``.

Every failure path still leaves the profile entry saved with status ``failed`` so the
agent degrades gracefully (FR-030) — a bogus name never blocks or errors the save.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter

from ..config import settings
from ..db import repository as repo
from ..db.session import SessionLocal

logger = logging.getLogger(__name__)

# Keep references to in-flight tasks so they aren't garbage-collected mid-run, and
# a simple in-flight id set so a rapid re-lock doesn't run two tasks for one entry.
_bg_tasks: set[asyncio.Task] = set()
_inflight: set[uuid.UUID] = set()

_GUIDE_PROMPT = (
    "Write a concise, current-retail World of Warcraft guide for **{cls} {spec}**. "
    "Cover: core single-target rotation/priority, key secondary stats, and the "
    "standard talent/build choices. Keep it tight and practical (a few short "
    "sections). Use web search for current-patch accuracy and mention sources."
)

_GUILD_PROMPT = (
    "Using Warcraft Logs data, write a brief recent-progression summary for the guild "
    "**{name}** on {server} ({region}): the current raid tier, bosses killed on each "
    "difficulty, and any notable recent kills. Keep it to a few sentences; if the guild "
    "can't be found, say so plainly."
)


# --- WCL spec resolution ------------------------------------------------------


def _resolve_active_spec_sync(
    name: str, server: str, region: str
) -> tuple[str | None, str | None] | None:
    """Best-effort (class, spec) from a character's current-zone rankings.

    Returns ``None`` when the character can't be resolved or has no ranked specs,
    which the caller treats as a ``failed`` guide (entry still saved).
    """
    from wcl_agent.report_tools import get_character_zone_rankings

    res = get_character_zone_rankings(name, server, region)
    if res.get("status") != "success":
        return None
    zr = res.get("zoneRankings")
    if not isinstance(zr, dict):
        return None
    rankings = zr.get("rankings") or []
    specs = [r.get("spec") for r in rankings if isinstance(r, dict) and r.get("spec")]
    classes = [r.get("class") for r in rankings if isinstance(r, dict) and r.get("class")]
    spec = Counter(specs).most_common(1)[0][0] if specs else None
    cls = Counter(classes).most_common(1)[0][0] if classes else None
    if not spec:
        return None
    return cls, spec


async def resolve_active_spec(
    name: str, server: str, region: str
) -> tuple[str | None, str | None] | None:
    """Async wrapper — the WCL client is blocking, so run it off the event loop."""
    try:
        return await asyncio.to_thread(_resolve_active_spec_sync, name, server, region)
    except Exception:  # noqa: BLE001 - resolution is best-effort
        logger.exception("Active-spec resolution failed for %s-%s (%s)", name, server, region)
        return None


# --- Guide / summary text generation -----------------------------------------


async def _generate_text(prompt: str) -> str:
    """Run ``prompt`` through the guide model over a disposable session; collect text."""
    from ..agent_runner import stream_response

    session_id = f"guide-{uuid.uuid4().hex}"
    tokens: list[str] = []
    async for record in stream_response(settings.wcl_guide_model, session_id, prompt):
        if record.get("type") == "token":
            tokens.append(record["text"])
    return "".join(tokens).strip()


# --- Task bodies --------------------------------------------------------------


async def run_character_guide(char_id: uuid.UUID) -> None:
    """Resolve the spec, generate the guide, and persist status transitions."""
    async with SessionLocal() as session:
        char = await repo.get_character(session, char_id)
        if char is None:
            return
        name, server, region = char.name, char.server, char.region

    resolved = await resolve_active_spec(name, server, region)
    if resolved is None:
        await _finish_character(char_id, status="failed")
        return
    cls, spec = resolved
    try:
        markdown = await _generate_text(_GUIDE_PROMPT.format(cls=cls or "", spec=spec))
    except Exception:  # noqa: BLE001 - generation is best-effort
        logger.exception("Guide generation failed for character %s", char_id)
        await _finish_character(char_id, status="failed", class_name=cls, active_spec=spec)
        return
    if not markdown:
        await _finish_character(char_id, status="failed", class_name=cls, active_spec=spec)
        return
    await _finish_character(
        char_id, status="ready", class_name=cls, active_spec=spec, markdown=markdown
    )


async def _finish_character(
    char_id: uuid.UUID,
    *,
    status: str,
    class_name: str | None = None,
    active_spec: str | None = None,
    markdown: str | None = None,
) -> None:
    async with SessionLocal() as session:
        await repo.set_character_guide(
            session,
            char_id,
            class_name=class_name,
            active_spec=active_spec,
            markdown=markdown,
            status=status,
        )
        await session.commit()


async def run_guild_summary(guild_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        guild = await repo.get_guild_profile(session)
        if guild is None or guild.id != guild_id:
            return
        name, server, region = guild.name, guild.server, guild.region

    try:
        markdown = await _generate_text(
            _GUILD_PROMPT.format(name=name, server=server, region=region)
        )
    except Exception:  # noqa: BLE001
        logger.exception("Guild summary generation failed for %s", guild_id)
        markdown = ""

    status = "ready" if markdown else "failed"
    async with SessionLocal() as session:
        await repo.set_guild_summary(
            session, guild_id, markdown=markdown or None, status=status
        )
        await session.commit()


# --- Scheduling (called from the profile router) ------------------------------


def _spawn(coro, key: uuid.UUID) -> None:
    """Fire-and-forget a background task with GC-safe referencing + idempotency.

    No-op when there's no running loop (e.g. a sync unit test that isn't exercising
    the lifecycle) so scheduling never raises into the request path.
    """
    if key in _inflight:
        coro.close()  # discard the duplicate coroutine so it isn't left un-awaited
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        return
    _inflight.add(key)
    task = loop.create_task(coro)
    _bg_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _bg_tasks.discard(t)
        _inflight.discard(key)

    task.add_done_callback(_done)


def schedule_character_guide(char_id: uuid.UUID) -> None:
    _spawn(run_character_guide(char_id), char_id)


def schedule_guild_summary(guild_id: uuid.UUID) -> None:
    _spawn(run_guild_summary(guild_id), guild_id)
