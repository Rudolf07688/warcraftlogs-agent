"""Recent-raid kickoff pre-fetch, playbook and tool-call count (046, sc-339).

The WCL tool functions are faked: the pre-fetch must call them as the clicking workspace,
once per click, never twice at once for one workspace and report, and never for a report the
endpoint refuses. Failures are logged, never raised.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import pytest

from backend.app.main import app
from backend.app.services import background, kickoff_prefetch
from backend.app.services.kickoff_prefetch import MAX_BOSS_TABLES, pick_boss_fights
from backend.app.tenancy.context import RequestIdentity, current_identity
from backend.tests.test_raids import _store_recent
from wcl_agent.agent import INSTRUCTION
from wcl_agent.cache.cache_models import FightSummary, ReportSummary


def _summary(*fights: tuple[int, int, int | None, bool]) -> ReportSummary:
    """fights: (fight id, encounter id, difficulty, kill)."""
    return ReportSummary(
        code="RECENT1", start_time_ms=0, end_time_ms=1,
        fights=[FightSummary(id=i, name=f"f{i}", encounter_id=e, difficulty=d, kill=k) for i, e, d, k in fights],
    )


def test_one_fight_per_boss_last_kill_else_last_pull():
    summary = _summary(
        (1, 0, None, False),  # trash
        (2, 100, 4, False), (3, 100, 4, True), (4, 100, 4, False),  # killed, then a wipe after
        (5, 200, 4, False), (6, 200, 4, False),  # never killed
        (7, 100, 5, True),  # same boss, other difficulty
    )
    assert pick_boss_fights(summary) == [3, 6, 7]


def test_the_pre_fetch_is_bounded():
    summary = _summary(*[(i, 1000 + i, 4, True) for i in range(1, 16)])
    assert pick_boss_fights(summary) == list(range(1, MAX_BOSS_TABLES + 1))


class _FakeWcl:
    """Records each call and the workspace it ran as; ``gate`` holds the summary load open."""

    def __init__(self, monkeypatch, summary=None, fail: Exception | None = None):
        self.summaries: list[uuid.UUID | None] = []
        self.tables: list[tuple[str, str, int, uuid.UUID | None]] = []
        self.gate: asyncio.Event | None = None
        self.summary = summary or _summary((2, 100, 4, True), (5, 200, 4, False))

        async def load(code):
            self.summaries.append(_tenant())
            if self.gate is not None:
                await self.gate.wait()
            if fail is not None:
                raise fail
            return self.summary

        async def table(code, data_type, fight_id=0, **_kwargs):
            self.tables.append((code, data_type, fight_id, _tenant()))
            return {"status": "success"}

        monkeypatch.setattr(kickoff_prefetch, "load_report_summary", load)
        monkeypatch.setattr(kickoff_prefetch, "get_report_table", table)


def _tenant() -> uuid.UUID | None:
    identity = current_identity.get()
    return identity.tenant_id if identity is not None else None


async def _drain():
    while background._bg_tasks:
        await asyncio.gather(*list(background._bg_tasks))


@pytest.fixture
def store_running(monkeypatch):
    monkeypatch.setattr(app.state, "fetch_writer", object(), raising=False)


async def test_a_click_pre_fetches_once_as_the_workspace(as_user, session_factory, store_running, monkeypatch):
    wcl = _FakeWcl(monkeypatch)
    await _store_recent(session_factory, as_user.tenant_id)
    resp = await as_user.client.post("/api/raids/RECENT1/investigate", json={})
    assert resp.status_code == 201
    await _drain()
    assert wcl.summaries == [as_user.tenant_id]
    assert wcl.tables == [("RECENT1", "Summary", 2, as_user.tenant_id), ("RECENT1", "Summary", 5, as_user.tenant_id)]
    assert current_identity.get() is None  # nothing leaks into the request's own context

    again = await as_user.client.post("/api/raids/RECENT1/investigate", json={})
    assert again.status_code == 201
    await _drain()
    assert len(wcl.summaries) == 2  # once per click


async def test_a_click_while_the_pre_fetch_runs_starts_no_second_one(as_user, session_factory, store_running, monkeypatch):
    # Two clicks overlap in the pre-fetch, not in the request (the SQLite test DB serves one
    # request at a time): the second arrives while the first job is still loading.
    wcl = _FakeWcl(monkeypatch)
    wcl.gate = asyncio.Event()
    await _store_recent(session_factory, as_user.tenant_id)
    first = await as_user.client.post("/api/raids/RECENT1/investigate", json={})
    second = await as_user.client.post("/api/raids/RECENT1/investigate", json={})
    assert (first.status_code, second.status_code) == (201, 201)  # the response never waits
    assert len(background._bg_tasks) == 1
    wcl.gate.set()
    await _drain()
    assert len(wcl.summaries) == 1 and len(wcl.tables) == 2


async def test_a_failure_is_only_logged(as_user, session_factory, store_running, monkeypatch, caplog):
    wcl = _FakeWcl(monkeypatch, fail=RuntimeError("WCL down"))
    await _store_recent(session_factory, as_user.tenant_id)
    with caplog.at_level(logging.WARNING, logger="backend.app.services.kickoff_prefetch"):
        resp = await as_user.client.post("/api/raids/RECENT1/investigate", json={})
        await _drain()
    assert resp.status_code == 201
    assert wcl.tables == []
    assert any("kickoff prefetch failed" in r.getMessage() and "RuntimeError" in r.getMessage() for r in caplog.records)


async def test_a_refused_report_fetches_nothing(as_user, make_authed_client, session_factory, store_running, monkeypatch):
    wcl = _FakeWcl(monkeypatch)
    other = await make_authed_client("other@example.com")
    try:
        await _store_recent(session_factory, other.tenant_id, code="THEIRS")
        assert (await as_user.client.post("/api/raids/THEIRS/investigate", json={})).status_code == 404
        assert (await as_user.client.post("/api/raids/NOPE/investigate", json={})).status_code == 404
        await _drain()
    finally:
        await other.client.aclose()
    assert wcl.summaries == [] and wcl.tables == []


async def test_no_pre_fetch_without_the_raw_store(as_user, session_factory, monkeypatch):
    wcl = _FakeWcl(monkeypatch)
    await _store_recent(session_factory, as_user.tenant_id)
    assert (await as_user.client.post("/api/raids/RECENT1/investigate", json={})).status_code == 201
    await _drain()
    assert wcl.summaries == []


async def test_prefetch_sets_the_identity_only_in_its_own_task(monkeypatch):
    wcl = _FakeWcl(monkeypatch)
    identity = RequestIdentity(uuid.uuid4(), uuid.uuid4(), "member", False, uuid.uuid4())
    kickoff_prefetch.schedule(identity, "RECENT1")
    kickoff_prefetch.schedule(identity, "RECENT1")  # the same workspace and report: deduplicated
    await _drain()
    assert wcl.summaries == [identity.tenant_id]
    assert current_identity.get() is None


def test_the_playbook_names_the_kickoff_sequence():
    body = INSTRUCTION.split("<RECENT_RAID_KICKOFF>")[1].split("</RECENT_RAID_KICKOFF>")[0]
    assert "`get_report_fights` once" in body
    assert 'ONE parallel round of `get_report_table` with data_type "Summary"' in body
    assert "last kill, or its last pull" in body
    assert "No per-player fetches" in body
    assert body.index("get_report_fights") < body.index("get_report_table")
