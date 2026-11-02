"""Recent-raid investigate: a per-user limit and a careful pre-fetch (feature 052, sc-352).

One user may start at most ``WCL_INVESTIGATE_PER_MINUTE`` investigations a minute (429 past it,
before the 404 rule). The kickoff pre-fetch never starts while the raw-store breaker is open
(asked without touching its state), and only after the endpoint's transaction committed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from backend.app.api import raids as raids_mod
from backend.app.auth import dependencies
from backend.app.auth.rate_limit import InProcessRateLimiter
from backend.app.config import Settings, settings
from backend.app.db.models import Conversation
from backend.app.services import kickoff_prefetch, raw_fetch_reads
from backend.app.services.raw_fetch_reads import Breaker
from backend.tests.test_046_kickoff_prefetch import _drain, _FakeWcl
from backend.tests.test_raids import _store_recent
from wcl_agent.client import wcl_client


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(kickoff_prefetch, "_started", {})
    monkeypatch.setattr(raw_fetch_reads, "breaker", Breaker())
    monkeypatch.setattr(settings, "wcl_store_reads_enabled", True)
    monkeypatch.setattr(wcl_client, "_fetch_source", object())


async def _conversations(session_factory) -> int:
    async with session_factory() as s:
        return await s.scalar(select(func.count()).select_from(Conversation))


def test_the_limit_is_configurable_with_a_sensible_default(monkeypatch):
    assert Settings().wcl_investigate_per_minute == 5
    monkeypatch.setenv("WCL_INVESTIGATE_PER_MINUTE", "2")
    assert Settings().wcl_investigate_per_minute == 2


async def test_over_the_limit_is_429_and_starts_nothing(as_user, session_factory, monkeypatch):
    monkeypatch.setattr(raids_mod, "investigate_limiter", InProcessRateLimiter(per_minute=2))
    wcl = _FakeWcl(monkeypatch)
    await _store_recent(session_factory, as_user.tenant_id)
    for _ in range(2):
        assert (await as_user.client.post("/api/raids/RECENT1/investigate", json={})).status_code == 201
        await _drain()
    before = await _conversations(session_factory)
    monkeypatch.setattr(kickoff_prefetch, "_started", {})  # no cooldown hides a pre-fetch
    resp = await as_user.client.post("/api/raids/RECENT1/investigate", json={})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited" and resp.headers["Retry-After"]
    await _drain()
    assert await _conversations(session_factory) == before
    assert len(wcl.summaries) == 1  # the first click's only


async def test_the_limit_comes_before_the_404_rule(as_user, monkeypatch):
    monkeypatch.setattr(raids_mod, "investigate_limiter", InProcessRateLimiter(per_minute=1))
    assert (await as_user.client.post("/api/raids/NOPE1/investigate", json={})).status_code == 404
    assert (await as_user.client.post("/api/raids/NOPE2/investigate", json={})).status_code == 429


async def test_a_limited_request_takes_no_tenant_transaction(as_user, monkeypatch):
    monkeypatch.setattr(raids_mod, "investigate_limiter", InProcessRateLimiter(per_minute=1))
    opened: list[object] = []
    real = dependencies.tenant_session

    def counting(identity, *args, **kwargs):
        opened.append(identity)
        return real(identity, *args, **kwargs)

    monkeypatch.setattr(dependencies, "tenant_session", counting)
    assert (await as_user.client.post("/api/raids/NOPE1/investigate", json={})).status_code == 404
    assert len(opened) == 1
    assert (await as_user.client.post("/api/raids/NOPE2/investigate", json={})).status_code == 429
    assert len(opened) == 1  # P7 hardening: the 429 came before the endpoint's DB transaction


async def test_the_limit_is_per_user(as_user, make_authed_client, monkeypatch):
    monkeypatch.setattr(raids_mod, "investigate_limiter", InProcessRateLimiter(per_minute=1))
    other = await make_authed_client("other@example.com")
    try:
        assert (await as_user.client.post("/api/raids/NOPE/investigate", json={})).status_code == 404
        assert (await other.client.post("/api/raids/NOPE/investigate", json={})).status_code == 404
    finally:
        await other.client.aclose()


async def test_no_pre_fetch_while_the_breaker_is_open(as_user, session_factory, monkeypatch):
    wcl = _FakeWcl(monkeypatch)
    await _store_recent(session_factory, as_user.tenant_id)
    breaker = raw_fetch_reads.breaker
    breaker.failed()
    state = (breaker.open_until, breaker.trial)
    assert (await as_user.client.post("/api/raids/RECENT1/investigate", json={})).status_code == 201
    await _drain()
    assert wcl.summaries == [] and kickoff_prefetch._started == {}  # no cooldown spent either
    assert (breaker.open_until, breaker.trial) == state  # asking took no trial


async def test_a_half_open_breaker_lets_the_pre_fetch_try(as_user, session_factory, monkeypatch):
    wcl = _FakeWcl(monkeypatch)
    await _store_recent(session_factory, as_user.tenant_id)
    raw_fetch_reads.breaker.open_until = raw_fetch_reads.breaker.clock() - 1  # the wait is over
    assert (await as_user.client.post("/api/raids/RECENT1/investigate", json={})).status_code == 201
    await _drain()
    assert wcl.summaries == [as_user.tenant_id]


async def test_a_failing_commit_schedules_nothing(as_user, session_factory, monkeypatch):
    await _store_recent(session_factory, as_user.tenant_id)
    scheduled: list[str] = []
    monkeypatch.setattr(kickoff_prefetch, "schedule", lambda identity, code: scheduled.append(code))
    create = raids_mod.repo.create_conversation

    async def create_then_break_commit(db, **kwargs):
        conv = await create(db, **kwargs)

        async def commit():
            raise RuntimeError("commit failed")

        monkeypatch.setattr(db, "commit", commit)
        return conv

    monkeypatch.setattr(raids_mod.repo, "create_conversation", create_then_break_commit)
    try:
        resp = await as_user.client.post("/api/raids/RECENT1/investigate", json={})
    except RuntimeError:  # the test transport re-raises the app's error
        pass
    else:
        assert resp.status_code == 500
    assert scheduled == []
