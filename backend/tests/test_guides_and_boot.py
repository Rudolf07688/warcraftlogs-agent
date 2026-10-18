"""Guides and boot (PERF-012, PERF-014, PERF-015)."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from sqlalchemy import inspect

from backend.app import greeting as greeting_mod
from backend.app.db import repository as repo
from backend.app.services import guide
from wcl_agent import models as models_mod

# --- PERF-015: model probes run concurrently and keep their order -----------------------


def test_model_probes_run_concurrently(monkeypatch):
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: object())

    def slow_probe(client, mid):
        time.sleep(0.3)
        return mid != "gemini-bogus"

    monkeypatch.setattr(models_mod, "_probe_gemini", slow_probe)
    start = time.monotonic()
    result = models_mod.discover_models(
        gemini_ids=["gemini-a", "gemini-bogus", "gemini-b"],
        anthropic_ids=[],
        configured_default="gemini-a",
        fallback_models=["gemini-a"],
    )
    assert time.monotonic() - start < 0.6  # three 0.3 s probes overlapped
    assert result["models"] == ["gemini-a", "gemini-b"]  # configured order kept


def test_probe_that_raises_counts_as_failed(monkeypatch):
    monkeypatch.setattr(models_mod, "_make_gemini_client", lambda: object())

    def flaky(client, mid):
        if mid == "gemini-b":
            raise RuntimeError("boom")
        return True

    monkeypatch.setattr(models_mod, "_probe_gemini", flaky)
    result = models_mod.discover_models(
        gemini_ids=["gemini-a", "gemini-b"],
        anthropic_ids=[],
        configured_default="gemini-a",
        fallback_models=["gemini-a"],
    )
    assert result["models"] == ["gemini-a"]


async def test_concurrent_greeting_misses_generate_once(monkeypatch):
    calls = {"n": 0}

    async def gen(model):
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return "Well met!"

    monkeypatch.setattr(greeting_mod, "_generate_greeting", gen)
    app = SimpleNamespace(state=SimpleNamespace())
    results = await asyncio.gather(*(greeting_mod.get_greeting(app, "m") for _ in range(3)))
    assert results == ["Well met!"] * 3
    assert calls["n"] == 1


def test_greeting_session_is_per_boot():
    assert greeting_mod._BOOT_ID  # the session id differs per process run


# --- PERF-012: background generations are capped ----------------------------------------


async def test_guide_generations_are_capped(monkeypatch):
    running = peak = 0

    async def fake_stream(prompt, session_id):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        return guide.GeneratedText("text", [], "s")

    monkeypatch.setattr(guide, "_stream_text", fake_stream)
    monkeypatch.setattr(guide.settings, "wcl_guide_max_concurrency", 2)
    monkeypatch.setattr(guide, "_generation_slots", {})
    await asyncio.gather(*(guide._generate_text(f"p{i}") for i in range(6)))
    assert peak == 2


# --- PERF-014: lighter guide reads ---------------------------------------------------------


async def _seed_guides(session):
    for cls, spec, status in [
        ("Mage", "Fire", "ready"),
        ("Priest", "Holy", "pending"),
        ("Priest", "Fire", "ready"),  # matched by the old class × spec cross product
    ]:
        await repo.upsert_spec_guide(
            session, class_name=cls, spec=spec, status=status, guide_markdown=f"{cls} {spec} guide"
        )
    await session.commit()


async def test_guide_pairs_match_exactly_and_can_filter_ready(session):
    await _seed_guides(session)
    keys = [("Mage", "Fire", "raid"), ("Priest", "Holy", "raid")]
    rows = await repo.get_spec_guides_for(session, keys)
    assert set(rows) == {("Mage", "Fire", "raid"), ("Priest", "Holy", "raid")}
    ready = await repo.get_spec_guides_for(session, keys, ready_only=True)
    assert set(ready) == {("Mage", "Fire", "raid")}


async def test_status_only_reads_skip_the_guide_text(session):
    await _seed_guides(session)
    session.expunge_all()  # make sure rows are loaded fresh by the queries below
    roster = await repo.list_spec_guides(session, with_text=False)
    assert roster and all("guide_markdown" in inspect(g).unloaded for g in roster)
    session.expunge_all()
    status = await repo.get_spec_guides_for(session, [("Mage", "Fire", "raid")], with_text=False)
    g = status[("Mage", "Fire", "raid")]
    assert "guide_markdown" in inspect(g).unloaded
    assert g.status == "ready" and g.updated_at is not None
    assert repo.guide_has_published(g)
