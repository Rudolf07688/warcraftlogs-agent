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
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from wcl_agent.constants import CLASS_SPECS
from wcl_agent.guide_meta import GuideCooldown, GuideMeta, set_guide_meta
from wcl_agent.patch import guide_freshness

from ..config import settings
from ..db import repository as repo
from ..db import session as db_session
from ..schemas import GuideMetaBlock
from ..tenancy.context import tenant_scope

logger = logging.getLogger(__name__)

# Keep references to in-flight tasks so they aren't garbage-collected mid-run, and
# a simple in-flight id set so a rapid re-lock doesn't run two tasks for one entry.
_bg_tasks: set[asyncio.Task] = set()
_inflight: set[uuid.UUID] = set()

# Feature 009 / US5 (research R15): an explicit *authoring* task, so the agent's
# evidence contract (which governs claims about logged play) does not starve the
# guide. Asks for the target patch, numeric major cooldowns, and one trailing
# machine-readable `guide-meta` block (data-model §2). Literal braces are doubled
# for str.format.
_GUIDE_PROMPT = (
    "You are writing a reference guide: a concise, current-retail World of Warcraft "
    "guide for **{cls} {spec}**. This is an authoring task — general class knowledge "
    "is allowed; use web search for current-patch accuracy when it is available and "
    "cite the sources you used. State the patch the guide targets near the top.\n\n"
    "Cover, in short practical sections: core single-target rotation/priority, key "
    "secondary stats, the standard talent/build choices, and a **Major cooldowns** "
    "section listing the spec's major throughput and defensive cooldowns with their "
    "cooldown in seconds (e.g. 'Combustion — 120 s', charges if more than one).\n\n"
    "End the guide with exactly one fenced code block labelled `guide-meta` containing "
    "JSON of this shape (up to 15 cooldowns — the ones in the Major cooldowns section; "
    "spell_id null when unknown; talent_modified true when a common talent changes the "
    "cooldown):\n"
    "```guide-meta\n"
    '{{"patch": "<major.minor>", "major_cooldowns": [{{"name": "<ability>", '
    '"spell_id": <id or null>, "cooldown_s": <seconds>, "charges": <n>, '
    '"talent_modified": <true or false>}}]}}\n'
    "```\n"
    "Nothing may follow that block."
)

# One repair turn on the same session when the block is missing/invalid (research R10).
_GUIDE_META_REPAIR_PROMPT = "Reply with only the guide-meta block for the guide above."

_META_BLOCK_RE = re.compile(r"```guide-meta[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)

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


@dataclass(frozen=True)
class GeneratedText:
    """Model output plus the web-grounding sources it used (feature 009, research R9)."""

    text: str
    sources: list[dict]  # [{title, uri}] — deterministic, from grounding records
    session_id: str


# PERF-012: one semaphore per event loop (tests run several loops) caps how many
# background generations run at once.
_generation_slots: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


def _generation_slot() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    slot = _generation_slots.get(loop)
    if slot is None:
        slot = _generation_slots[loop] = asyncio.Semaphore(max(1, settings.wcl_guide_max_concurrency))
    return slot


async def _generate_text(prompt: str, session_id: str | None = None) -> GeneratedText:
    """Run ``prompt`` through the guide model over a disposable session; collect text.

    ``session_id`` is reused when given (the guide-meta repair turn), else a fresh
    disposable session is created. Sources come from the ``grounding`` records
    ``stream_response`` emits (empty when the model has no web search). At most
    ``wcl_guide_max_concurrency`` generations run at once (PERF-012).
    """
    async with _generation_slot():
        return await _stream_text(prompt, session_id)


async def _stream_text(prompt: str, session_id: str | None) -> GeneratedText:
    from ..agent_runner import stream_response

    session_id = session_id or f"guide-{uuid.uuid4().hex}"
    tokens: list[str] = []
    sources: list[dict] = []
    seen: set[str] = set()
    async for record in stream_response(settings.wcl_guide_model, session_id, prompt):
        kind = record.get("type")
        if kind == "token":
            tokens.append(record["text"])
        elif kind == "grounding":
            for src in record.get("sources") or []:
                uri = src.get("uri") if isinstance(src, dict) else None
                if uri and uri not in seen:
                    seen.add(uri)
                    sources.append({"title": src.get("title"), "uri": uri})
    return GeneratedText("".join(tokens).strip(), sources, session_id)


def parse_guide_meta(text: str) -> tuple[str, GuideMetaBlock | None]:
    """Extract the last fenced ``guide-meta`` JSON block (data-model §2).

    Returns ``(markdown without the block, meta)``; when the block is missing or
    invalid, returns ``(text unchanged, None)`` so nothing the model wrote is lost.
    """
    matches = list(_META_BLOCK_RE.finditer(text or ""))
    if not matches:
        return text, None
    match = matches[-1]
    try:
        meta = GuideMetaBlock.model_validate_json(match.group(1).strip())
    except (ValidationError, ValueError):
        return text, None
    stripped = (text[: match.start()] + text[match.end():]).rstrip()
    return stripped, meta


def _parse_meta_reply(text: str) -> GuideMetaBlock | None:
    """A repair reply may be the fenced block or bare JSON."""
    _, meta = parse_guide_meta(text)
    if meta is not None:
        return meta
    try:
        return GuideMetaBlock.model_validate_json((text or "").strip())
    except (ValidationError, ValueError):
        return None


async def _repair_guide_meta(session_id: str) -> GuideMetaBlock | None:
    """Exactly one follow-up on the same session asking for the block only (R10)."""
    try:
        reply = await _generate_text(_GUIDE_META_REPAIR_PROMPT, session_id=session_id)
    except Exception:  # noqa: BLE001 - metadata is best-effort
        logger.exception("guide-meta repair turn failed")
        return None
    return _parse_meta_reply(reply.text)


def registry_meta(
    class_name: str,
    spec: str,
    game_patch: str | None,
    generated_at: datetime | None,
    cooldowns: list | None,
) -> GuideMeta:
    """Stored ``major_cooldowns`` JSON → the registry dataclass (bad rows skipped)."""
    parsed: list[GuideCooldown] = []
    for c in cooldowns or []:
        if not isinstance(c, dict) or not c.get("name") or not c.get("cooldown_s"):
            continue
        try:
            parsed.append(
                GuideCooldown(
                    name=str(c["name"]),
                    spell_id=int(c["spell_id"]) if c.get("spell_id") else None,
                    cooldown_s=float(c["cooldown_s"]),
                    charges=int(c.get("charges") or 1),
                    talent_modified=bool(c.get("talent_modified")),
                )
            )
        except (TypeError, ValueError):
            continue
    return GuideMeta(class_name, spec, game_patch, generated_at, tuple(parsed))


async def load_guide_registry() -> int:
    """Publish every ``ready`` guide's patch + cooldowns to the in-process registry.

    Called at startup (lifespan). Returns the number of guides loaded; never raises.
    """
    try:
        async with db_session.SessionLocal() as session:
            rows = await repo.list_spec_guides(session)
    except Exception:  # noqa: BLE001 - startup must not fail on an empty/unreachable table
        logger.exception("Guide registry load failed")
        return 0
    loaded = 0
    for g in rows:
        if g.status != "ready":
            continue
        set_guide_meta(registry_meta(g.class_name, g.spec, g.game_patch, g.generated_at, g.major_cooldowns))
        loaded += 1
    return loaded


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
    """Generate the guide off the event loop; persist ready/failed + provenance (global).

    Feature 009: the trailing ``guide-meta`` block is parsed (one repair turn if it is
    missing/invalid), stripped from the stored markdown, persisted with the patch,
    generation time and web sources, and published to the ``wcl_agent`` registry. A
    guide is ``ready`` whenever there is text — metadata is best-effort (NULL ⇒
    unknown freshness, rate-only coaching).
    """
    cls_display = str(CLASS_SPECS.get(class_name, {}).get("display", class_name))
    markdown, sources, meta = "", [], None
    try:
        generated = await _generate_text(_GUIDE_PROMPT.format(cls=cls_display, spec=spec))
        sources = generated.sources
        markdown, meta = parse_guide_meta(generated.text)
        if markdown and meta is None:
            meta = await _repair_guide_meta(generated.session_id)
    except Exception:  # noqa: BLE001 - generation is best-effort
        logger.exception("Spec-guide generation failed for %s %s", class_name, spec)
        markdown = ""
    status = "ready" if markdown else "failed"
    now = datetime.now(UTC)
    cooldowns = [c.model_dump() for c in meta.major_cooldowns] if meta is not None else None
    async with db_session.SessionLocal() as session:
        if status == "ready":
            await repo.upsert_spec_guide(
                session,
                class_name=class_name,
                spec=spec,
                status=status,
                guide_markdown=markdown,
                game_patch=meta.patch if meta is not None else None,
                generated_at=now,
                sources=sources,
                major_cooldowns=cooldowns,
            )
        else:
            await repo.upsert_spec_guide(session, class_name=class_name, spec=spec, status=status)
        await session.commit()
    if status == "ready":
        set_guide_meta(
            registry_meta(class_name, spec, meta.patch if meta is not None else None, now, cooldowns)
        )


def build_guide_roster(guides: list, current_patch: str | None = None) -> list[dict]:
    """Merge the full ``CLASS_SPECS`` roster with existing ``spec_guides`` rows (FR-008).

    Every class+spec appears exactly once (100% coverage, SC-002); a spec with no row
    reports ``status="none"``. Ordered by class display name, then spec. Feature 009:
    each item carries ``game_patch``, ``generated_at`` and a read-time ``freshness``
    (``None`` unless ready) computed against ``current_patch``.
    """
    by_key = {(g.class_name, g.spec): g for g in guides}
    items: list[dict] = []
    for class_name, info in CLASS_SPECS.items():
        display = str(info["display"])
        for spec in info["specs"]:  # type: ignore[attr-defined]
            g = by_key.get((class_name, spec))
            ready = g is not None and g.status == "ready"
            items.append(
                {
                    "class_name": class_name,
                    "class_display": display,
                    "spec": spec,
                    "status": g.status if g is not None else "none",
                    "updated_at": g.updated_at if g is not None else None,
                    "game_patch": g.game_patch if g is not None else None,
                    "generated_at": g.generated_at if g is not None else None,
                    "freshness": guide_freshness(g.game_patch, current_patch) if ready else None,
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
        generated = await _generate_text(
            _GUILD_PROMPT.format(name=name, server=server, region=region)
        )
        markdown = generated.text  # guild summaries ignore sources (feature 009)
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
