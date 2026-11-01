"""Backfill the knowledge base from what was stored before feature 043 (sc-113).

    uv run python -m backend.cli.kb_backfill [--kinds wcl,guide,chat] [--limit N] [--confirm]

Without ``--confirm`` it only counts: the chunks each kind would add plus the rows still
waiting for a vector, with an estimated embedding cost, and writes nothing. With ``--confirm``
it writes the chunks (one transaction per source, with the same chunkers as the live indexer)
and then embeds every row still without a vector, through the shared rate-limit layer.

Resumable and idempotent: sources that already have chunks are skipped and rows with a vector
are never embedded again, so an interrupted run simply continues. Never a startup task. Runs as
the app's runtime role; chat rows are read and written workspace by workspace under that
workspace's scope (RLS).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select

from backend.app.config import settings
from backend.app.db import session as db_session
from backend.app.db.models import KbChatChunk, KbChunk, Message, SpecGuide, Tenant
from backend.app.db.repository import guide_has_published
from backend.app.kb import store
from backend.app.kb.chat_chunker import ExchangeJob, chunk_exchange
from backend.app.kb.embedder import get_embedder
from backend.app.kb.guide_chunker import GuideJob, chunk_guide
from backend.app.kb.indexer import KbIndexer
from backend.app.kb.names import mentioned_characters
from backend.app.kb.wcl_chunker import FetchSource, chunk_fetch, needed_fights
from backend.app.repositories.raw_fetches import list_fetch_keys, load_fetch_for_index
from backend.app.tenancy.context import tenant_scope

KINDS = ("wcl", "guide", "chat")
PAGE = 200
_PARSE_OFF_LOOP_BYTES = 256_000
EMBED_ALL = 10**9  # no row cap for the backfill's embed pass


@dataclass(frozen=True)
class Options:
    kinds: tuple[str, ...]
    confirm: bool
    limit: int | None


@dataclass
class Tally:
    """Per kind: sources chunked, chunks to embed and their characters."""

    sources: int = 0
    chunks: int = 0
    chars: int = 0

    def add(self, texts: Sequence[str]) -> None:
        self.sources += 1
        self.chunks += len(texts)
        self.chars += sum(len(t) for t in texts)


@dataclass
class Plan:
    tallies: dict[str, Tally] = field(default_factory=dict)


def parse_args(argv: Sequence[str] | None) -> Options:
    parser = argparse.ArgumentParser(prog="kb_backfill", description=__doc__.split("\n\n")[0])
    parser.add_argument("--kinds", default=",".join(KINDS), help="comma list of wcl, guide, chat")
    parser.add_argument("--confirm", action="store_true", help="write and embed (default: count only)")
    parser.add_argument("--limit", type=int, default=None, help="at most N new sources per kind")
    args = parser.parse_args(argv)
    kinds = tuple(k.strip() for k in args.kinds.split(",") if k.strip())
    unknown = set(kinds) - set(KINDS)
    if unknown:
        parser.error(f"unknown kinds: {', '.join(sorted(unknown))}")
    return Options(kinds, args.confirm, args.limit)


def cost(chars: int) -> tuple[float, float]:
    """(million tokens, USD): about four characters per token."""
    mtok = chars / 4 / 1_000_000
    return mtok, mtok * settings.kb_embed_price_per_mtok


def _room(options: Options, tally: Tally) -> bool:
    return options.limit is None or tally.sources < options.limit


# --- sources ----------------------------------------------------------------------------------


async def _backfill_wcl(options: Options, tally: Tally) -> None:
    for summaries in (True, False):  # summaries first, so table chunks find their fight context
        after: str | None = None
        while _room(options, tally):
            async with db_session.SessionLocal() as session:
                keys = await list_fetch_keys(session, after=after, limit=PAGE, summaries=summaries)
                done = await store.indexed_fetch_ids(session, keys)
            if not keys:
                break
            after = keys[-1]
            for key in keys:
                if key in done or not _room(options, tally):
                    continue
                await _backfill_fetch(options, tally, key)


async def _backfill_fetch(options: Options, tally: Tally, key: str) -> None:
    async with db_session.SessionLocal() as session:
        row = await load_fetch_for_index(session, key)
        if row is None:
            return
        if len(row.body) > _PARSE_OFF_LOOP_BYTES:
            body = await asyncio.to_thread(json.loads, row.body)
        else:
            body = json.loads(row.body)
        # Stored rows keep no query text: the table metric is inferred from the body or the
        # table is skipped (decision clarify:043-backfill).
        source = FetchSource(key, tuple(row.report_codes), row.params, body)
        code, fights = needed_fights(source)
        contexts = await store.fight_contexts(session, code, fights) if code else {}
        drafts = chunk_fetch(source, contexts)
        if not drafts:
            return
        tally.add([d.text for d in drafts])
        if options.confirm:
            await store.replace_source_chunks(session, drafts, raw_fetch_id=key)
            await session.commit()


async def _backfill_guides(options: Options, tally: Tally) -> None:
    async with db_session.SessionLocal() as session:
        done = await store.indexed_guide_ids(session)
        guides = [g for g in await session.scalars(select(SpecGuide).order_by(SpecGuide.id)) if g.id not in done]
    for guide in guides:
        if not _room(options, tally):
            return
        if not guide_has_published(guide) or not guide.guide_markdown:
            continue
        job = GuideJob(guide.id, guide.class_name, guide.spec, guide.content_type, guide.guide_markdown, guide.game_patch)
        drafts = chunk_guide(job)
        if not drafts:
            continue
        tally.add([d.text for d in drafts])
        if options.confirm:
            async with db_session.SessionLocal() as session:
                await store.replace_source_chunks(session, drafts, guide_id=guide.id)
                await session.commit()


def exchanges(messages: Sequence[Message]) -> list[tuple[Message, Message]]:
    """(user message, complete agent answer) pairs of one conversation, in order."""
    pairs = []
    question: Message | None = None
    for message in messages:
        if message.role == "user":
            question = message
        elif message.role == "agent" and question is not None:
            if message.status == "complete":
                pairs.append((question, message))
            question = None
    return pairs


async def _backfill_chat(options: Options, tally: Tally) -> None:
    async with db_session.SessionLocal() as session:
        tenants = list(await session.scalars(select(Tenant.id).order_by(Tenant.id)))
    for tenant_id in tenants:
        if not _room(options, tally):
            return
        async with tenant_scope(tenant_id) as session:
            done = await store.indexed_exchanges(session, tenant_id)
            messages = list(
                await session.scalars(
                    select(Message)
                    .where(Message.tenant_id == tenant_id)
                    .order_by(Message.conversation_id, Message.seq)
                )
            )
            by_conversation: dict = {}
            for message in messages:
                by_conversation.setdefault(message.conversation_id, []).append(message)
            for conversation_id, rows in by_conversation.items():
                for question, answer in exchanges(rows):
                    if (conversation_id, answer.seq) in done or not _room(options, tally):
                        continue
                    job = ExchangeJob(tenant_id, conversation_id, answer.seq, question.content, answer.content, answer.created_at)
                    draft = chunk_exchange(job)
                    tally.add([draft.text])
                    if options.confirm:
                        characters = await mentioned_characters(session, tenant_id, f"{job.question}\n{job.answer}")
                        await store.upsert_chat_chunk(session, chunk_exchange(job, characters))


# --- run ----------------------------------------------------------------------------------------


async def _pending(kinds: Sequence[str]) -> Tally:
    """Rows already written but still without a vector (all kinds asked for)."""
    pending = Tally()
    async with db_session.SessionLocal() as session:
        if "wcl" in kinds or "guide" in kinds:
            pending.chunks, pending.chars = await store.pending_totals(session, KbChunk)
        tenants = list(await session.scalars(select(Tenant.id))) if "chat" in kinds else []
    for tenant_id in tenants:
        async with tenant_scope(tenant_id) as session:
            rows, chars = await store.pending_totals(session, KbChatChunk, tenant_id=tenant_id)
        pending.chunks += rows
        pending.chars += chars
    return pending


async def _embed(kinds: Sequence[str]) -> bool:
    indexer = KbIndexer(max_items=1, batch=settings.kb_embed_batch, sweep_s=settings.kb_embed_sweep_s)
    if ("wcl" in kinds or "guide" in kinds) and not await indexer.embed(KbChunk, max_rows=EMBED_ALL):
        return False
    if "chat" in kinds:
        async with db_session.SessionLocal() as session:
            tenants = list(await session.scalars(select(Tenant.id)))
        for tenant_id in tenants:
            if not await indexer.embed(KbChatChunk, tenant_id=tenant_id, max_rows=EMBED_ALL):
                return False
    return True


async def run(options: Options) -> int:
    steps = {"wcl": _backfill_wcl, "guide": _backfill_guides, "chat": _backfill_chat}
    plan = Plan()
    # The rows already waiting are counted before this run adds any.
    pending = await _pending(options.kinds)
    for kind in options.kinds:
        plan.tallies[kind] = Tally()
        await steps[kind](options, plan.tallies[kind])
    total = 0
    for kind, tally in plan.tallies.items():
        mtok, usd = cost(tally.chars)
        total += tally.chars
        print(f"{kind}: {tally.sources:,} sources, {tally.chunks:,} new chunks, ~{mtok:.2f}M tokens, ~USD {usd:.2f}")
    mtok, usd = cost(pending.chars)
    print(f"already written, not embedded: {pending.chunks:,} chunks, ~{mtok:.2f}M tokens, ~USD {usd:.2f}")
    mtok, usd = cost(total + pending.chars)
    print(f"total to embed with {settings.kb_embed_model}: ~{mtok:.2f}M tokens, ~USD {usd:.2f}")
    if not options.confirm:
        print("Nothing written. Run again with --confirm to write and embed.")
        return 0
    if get_embedder() is None:
        print("Chunks written; embeddings are unavailable, so they stay keyword-only for now.", file=sys.stderr)
        return 1
    if not await _embed(options.kinds):
        print("Embedding stopped on an error; run again to continue where it stopped.", file=sys.stderr)
        return 1
    print("Done.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
