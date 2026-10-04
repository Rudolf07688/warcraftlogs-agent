"""Background spec-guide / guild-summary generation (feature 005 / US6; feature 008 / US2-US3).

Locking a character or guild in the profile schedules a non-blocking task that:
1. resolves the character's active spec from Warcraft Logs (or the guild's identity),
2. for a character, persists the resolved ``(class, spec)`` and triggers the SHARED
   ``spec_guides`` guide for that pair (``ensure_spec_guide``) — reusing an already-ready
   guide (zero regeneration) or generating one; for a guild, generates its summary,
3. generation reuses ``stream_response`` over a disposable session (like the greeting primer)
   and flips the row's ``status``/``summary_status`` to ``ready`` (or ``failed``, retryable).

Every failure path is best-effort and non-blocking so the agent degrades gracefully
(FR-030) — a bogus name never blocks or errors the save, and ``failed`` is always retryable.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter

from sqlalchemy.exc import IntegrityError

from wcl_agent.constants import CLASS_SPECS

from ..config import settings
from ..db import repository as repo
from ..db import session as db_session
from ..tenancy.context import tenant_scope

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


# --- Shared spec-guide library (feature 008 / US2) ----------------------------
# One guide per (class, spec) in the GLOBAL ``spec_guides`` table, shared by all users.
# Reuses the same off-loop generation path as the per-character guide (Principle I —
# no second generation path) and the same ``_spawn`` dedup/GC machinery, re-keyed to
# the ``(class, spec)`` pair. Uses a plain (non-tenant) session: the table is global.


async def ensure_spec_guide(class_name: str, spec: str, *, force: bool = False) -> None:
    """Idempotent, best-effort generation of the ``(class, spec)`` guide into the library.

    - ``ready`` & not ``force``, or ``pending`` → no-op (dedup; FR-013, SC-004).
    - absent | ``failed`` | ``force``          → upsert ``pending``, spawn off-loop
      generation; success → ``ready`` + markdown, error/empty → ``failed`` (retryable).

    Never raises into the caller.
    """
    try:
        async with db_session.SessionLocal() as session:
            existing = await repo.get_spec_guide(
                session, class_name=class_name, spec=spec
            )
            if existing is not None and existing.status == "pending":
                return  # generation already in flight
            if existing is not None and existing.status == "ready" and not force:
                return  # dedup — reuse the ready guide
            try:
                await repo.upsert_spec_guide(
                    session, class_name=class_name, spec=spec, status="pending"
                )
                await session.commit()
            except IntegrityError:
                # A concurrent insert won the unique (class, spec) race; it owns
                # generation. Read nothing more — no-op.
                await session.rollback()
                return
    except Exception:  # noqa: BLE001 - scheduling is best-effort, never breaks the caller
        logger.exception("ensure_spec_guide bookkeeping failed for %s %s", class_name, spec)
        return

    _spawn(_run_spec_guide(class_name, spec), (class_name, spec))


async def _run_spec_guide(class_name: str, spec: str) -> None:
    """Generate the guide text off the event loop and persist ready/failed (global)."""
    cls_display = str(CLASS_SPECS.get(class_name, {}).get("display", class_name))
    try:
        markdown = await _generate_text(_GUIDE_PROMPT.format(cls=cls_display, spec=spec))
    except Exception:  # noqa: BLE001 - generation is best-effort
        logger.exception("Spec-guide generation failed for %s %s", class_name, spec)
        markdown = ""
    status = "ready" if markdown else "failed"
    async with db_session.SessionLocal() as session:
        await repo.upsert_spec_guide(
            session,
            class_name=class_name,
            spec=spec,
            status=status,
            guide_markdown=markdown or None,
        )
        await session.commit()


def build_guide_roster(guides: list) -> list[dict]:
    """Merge the full ``CLASS_SPECS`` roster with existing ``spec_guides`` rows (FR-008).

    Every class+spec appears exactly once (100% coverage, SC-002); a spec with no row
    reports ``status="none"``. Ordered by class display name, then spec.
    """
    by_key = {(g.class_name, g.spec): g for g in guides}
    items: list[dict] = []
    for class_name, info in CLASS_SPECS.items():
        display = str(info["display"])
        for spec in info["specs"]:  # type: ignore[attr-defined]
            g = by_key.get((class_name, spec))
            items.append(
                {
                    "class_name": class_name,
                    "class_display": display,
                    "spec": spec,
                    "status": g.status if g is not None else "none",
                    "updated_at": g.updated_at if g is not None else None,
                }
            )
    items.sort(key=lambda it: (it["class_display"], it["spec"]))
    return items


# --- Task bodies --------------------------------------------------------------


async def run_character_guide(char_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Resolve the character's spec and feed the shared guide library (feature 008 / US3).

    Resolves ``(class, spec)`` from Warcraft Logs (as before, per character), persists it on
    the character (tenant-scoped), then triggers the SHARED ``spec_guides`` guide for that
    pair. Reuses an already-``ready`` guide (zero regeneration; SC-004) or generates one.
    No per-character guide content is written — the guide is the global spec guide (FR-015,
    FR-016). An unresolved character simply gets no spec/guide (unchanged behavior).
    """
    async with tenant_scope(tenant_id) as session:
        char = await repo.get_character(session, char_id, tenant_id=tenant_id)
        if char is None:
            return
        name, server, region = char.name, char.server, char.region

    resolved = await resolve_active_spec(name, server, region)
    if resolved is None:
        return  # unresolved → no spec, no guide (character stays fully usable)
    cls, spec = resolved
    async with tenant_scope(tenant_id) as session:
        await repo.set_character_spec(
            session, char_id, tenant_id=tenant_id, class_name=cls, active_spec=spec
        )
    # WCL class/spec filter values key directly into the shared library.
    if cls and spec:
        await ensure_spec_guide(cls, spec)


async def run_guild_summary(guild_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    async with tenant_scope(tenant_id) as session:
        guild = await repo.get_guild_profile(session, tenant_id=tenant_id)
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
    async with tenant_scope(tenant_id) as session:
        await repo.set_guild_summary(
            session, guild_id, tenant_id=tenant_id, markdown=markdown or None, status=status
        )


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


def schedule_character_guide(char_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    _spawn(run_character_guide(char_id, tenant_id), char_id)


def schedule_guild_summary(guild_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    _spawn(run_guild_summary(guild_id, tenant_id), guild_id)
