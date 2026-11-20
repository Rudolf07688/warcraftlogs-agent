"""sc-570: an event pull with a start time also sends an end time.

Warcraft Logs returns no events for a ``startTime`` without an ``endTime``, so time
windows and page 2 (``nextPageTimestamp`` passed back as ``start_time``) came back empty.
The start time and page cursor come back from the model, so the hostile cases assert on
the variables actually sent to the fake client.
"""

from __future__ import annotations

import pytest

from backend.tests import wcl_fakes
from wcl_agent.tools import report_tools
from wcl_agent.tools.fight_time import fetch_dead_windows


def _events(next_ts=None):
    page = {"data": [{"timestamp": 821936}], "nextPageTimestamp": next_ts}
    return lambda q, v: {"data": {"reportData": {"report": {"events": page}}}}


async def _sent(monkeypatch, **kwargs) -> tuple[str, dict]:
    fake = wcl_fakes.install(monkeypatch, _events())
    res = await report_tools.get_report_events("bjXfNc92d8CPGhvB", "DamageTaken", **kwargs)
    assert res["status"] == "success"
    assert len(fake.calls) == 1
    return fake.calls[0]


async def test_start_time_carries_an_end_time(monkeypatch):
    """The live repro's page 2: start 821936 on fight 1 also sends an end past it."""
    query, sent = await _sent(monkeypatch, fight_id=1, source_id=11, limit=5, start_time=821936)
    assert "endTime: $endTime" in query and "$endTime: Float" in query
    assert sent["startTime"] == 821936
    assert sent["endTime"] is not None and sent["endTime"] > 821936
    assert sent["fightIDs"] == [1]


async def test_no_start_time_sends_neither(monkeypatch):
    _, sent = await _sent(monkeypatch, fight_id=1, limit=5)
    assert sent["startTime"] is None and sent["endTime"] is None


@pytest.mark.parametrize("start", [-5, 0])
async def test_negative_or_zero_start_is_the_fight_start(monkeypatch, start):
    _, sent = await _sent(monkeypatch, fight_id=1, start_time=start)
    assert sent["startTime"] is None and sent["endTime"] is None
    assert sent["fightIDs"] == [1]


async def test_start_past_the_fight_end_stays_inside_the_fight(monkeypatch):
    """A cursor past the fight (or from another fight or report) never drops the fight
    filter, so WCL's intersection keeps the window inside the caller's fight."""
    _, sent = await _sent(monkeypatch, fight_id=3, start_time=99_999_999)
    assert sent["fightIDs"] == [3]
    assert sent["startTime"] == 99_999_999
    assert sent["endTime"] > sent["startTime"]


async def test_whole_report_start_keeps_the_callers_start(monkeypatch):
    """No fight id: the window is [start, end of report]; the start is never moved earlier."""
    _, sent = await _sent(monkeypatch, start_time=1_089_000)
    assert sent["fightIDs"] is None
    assert sent["startTime"] == 1_089_000
    assert sent["endTime"] >= 1_089_000


async def test_next_cast_after_death_sends_an_end_time(monkeypatch):
    """fight_time's next-cast pull had the same bug: every death looked dead to fight end."""
    def responder(query, variables):
        if "dataType: Deaths" in query:
            entries = [{"name": "P", "id": 7, "timestamp": 100_000}]
            return {"data": {"reportData": {"report": {"table": {"data": {"entries": entries}}}}}}
        page = {"data": [{"timestamp": 130_000}], "nextPageTimestamp": None}
        return {"data": {"reportData": {"report": {"events": page}}}}

    fake = wcl_fakes.install(monkeypatch, responder)
    await fetch_dead_windows("ABC", 9, 7, 300_000)
    (query, sent), = [c for c in fake.calls if "dataType: Casts" in c[0]]
    assert "endTime: $endTime" in query
    assert sent["fightIDs"] == [9]
    assert sent["endTime"] > sent["startTime"] == 100_001
