"""The guide chunker and the publish hook (feature 043, sc-112 AC3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.db.models import KbChunk
from backend.app.kb import indexer as kb_indexer
from backend.app.kb.embedder import set_embedder
from backend.app.kb.guide_chunker import MAX_PARTS, GuideJob, _parts, chunk_guide
from backend.app.kb.indexer import KbIndexer
from backend.app.services.guide_pipeline import llm, run_guide_generation
from backend.app.services.guide_pipeline.llm import GuideModelError
from backend.tests.test_guide_pipeline_run import fakes  # noqa: F401 - the pipeline's fakes fixture

MARKDOWN = (
    "# Arms Warrior — Raid\n\nPatch 12.1.5\n\n"
    "## Rotation\n\n- Keep Mortal Strike on cooldown <!-- c1 -->\n- Execute below 20% <!-- c2 -->\n\n"
    "## Cooldowns\n\n- Avatar with Colossus Smash <!-- c3 -->\n"
)


def job(markdown: str = MARKDOWN, guide_id: uuid.UUID | None = None) -> GuideJob:
    return GuideJob(guide_id or uuid.uuid4(), "Warrior", "Arms", "raid", markdown, "12.1.5")


def test_one_chunk_per_section_with_the_labels_in_the_text():
    drafts = chunk_guide(job())
    assert [d.label for d in drafts] == ["Arms Warrior — Raid", "Rotation", "Cooldowns"]
    rotation = drafts[1]
    assert rotation.text == (
        "Arms Warrior (dps) raid guide, section Rotation:\n"
        "- Keep Mortal Strike on cooldown\n- Execute below 20%"
    )
    assert (rotation.class_name, rotation.spec, rotation.role, rotation.content_type, rotation.patch, rotation.section) == (
        "Warrior", "Arms", "dps", "raid", "12.1.5", "Rotation",
    )
    assert all("<!--" not in d.text for d in drafts)
    assert len({d.chunk_key for d in drafts}) == 3


def test_mythic_plus_guides_say_so_and_long_sections_split_into_bounded_parts():
    drafts = chunk_guide(GuideJob(uuid.uuid4(), "Priest", "Holy", "mplus", "## Healing\n\n" + "word " * 2000))
    assert drafts[0].text.startswith("Holy Priest (healer) Mythic+ guide, section Healing (1/")
    assert 1 < len(drafts) <= MAX_PARTS and all(len(d.text) <= 2000 for d in drafts)
    assert drafts[0].label.startswith("Healing (1/")


@pytest.mark.parametrize("title_length", [150, 1_940, 3_000])
def test_a_very_long_heading_still_chunks_within_bounds(title_length):
    drafts = chunk_guide(job(f"## {'T' * title_length}\n\n" + "word " * 1000))
    assert drafts and len(drafts) <= MAX_PARTS
    assert all(len(d.text) <= 2000 for d in drafts)


def test_parts_always_advance_even_for_no_room():
    assert _parts("word " * 50, 0) and _parts("word " * 50, -5)


@pytest.fixture
def db(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    return session_factory


async def test_a_republished_guide_replaces_its_chunks(db):
    class Fake:
        model = "fake"

        async def embed(self, texts, *, task):
            return [[1.0] + [0.0] * 767 for _ in texts]

    set_embedder(Fake())
    try:
        async with db() as s:
            guide = await repo.upsert_spec_guide(s, class_name="Warrior", spec="Arms", status="ready")
            await s.commit()
        indexer = KbIndexer(max_items=5, batch=8, sweep_s=600)
        await indexer.handle(job(guide_id=guide.id))
        await indexer.handle(job("## Rotation\n\n- Only Mortal Strike now\n", guide_id=guide.id))
        async with db() as s:
            rows = list(await s.scalars(select(KbChunk).where(KbChunk.guide_id == guide.id)))
    finally:
        set_embedder(None)
    assert [r.label for r in rows] == ["Rotation"]  # no stale sections
    assert "Only Mortal Strike now" in rows[0].text and rows[0].embedding is not None


async def test_publishing_offers_the_guide_and_a_failed_run_does_not(fakes, monkeypatch, session_factory):  # noqa: F811
    offered: list[GuideJob] = []
    monkeypatch.setattr(kb_indexer, "offer_guide", offered.append)
    assert (await run_guide_generation("Mage", "Fire", "raid")).outcome == "published"
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
    [sent] = offered
    assert (sent.guide_id, sent.class_name, sent.spec, sent.content_type, sent.patch) == (g.id, "Mage", "Fire", "raid", "12.1.5")
    assert sent.markdown == g.guide_markdown

    async def broken(*a, **k):
        raise GuideModelError("invalid structured output")

    monkeypatch.setattr(llm, "generate_structured", broken)
    assert (await run_guide_generation("Mage", "Fire", "raid")).reason == "model_error"
    assert len(offered) == 1
