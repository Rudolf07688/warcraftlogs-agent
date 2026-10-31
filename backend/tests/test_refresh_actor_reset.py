"""sc-276: the WCL refresh actor lives only for the turn that set it.

``set_refresh_actor`` is a ContextVar. If a turn leaves it set, tasks the socket starts later
in the same context (the follow-up suggestions) would act as that turn's user, like
``current_identity`` did before sc-222. Same harness as test_proposal_ws.py, but with the real
``set_refresh_actor``.
"""

from __future__ import annotations

import pytest

from backend.app.api import ws as ws_mod
from backend.tests.test_proposal_ws import _ctx_stream, _FakeSocket, _quiet, _run
from wcl_agent.cache.cache import get_refresh_actor, set_refresh_actor


@pytest.fixture(autouse=True)
def _clean_actor():
    set_refresh_actor(None)
    yield
    set_refresh_actor(None)


def _real_actor(monkeypatch) -> None:
    monkeypatch.setattr(ws_mod, "set_refresh_actor", set_refresh_actor)


@pytest.mark.parametrize("fail", [False, True])
async def test_the_actor_is_set_during_the_turn_and_cleared_after(as_user, monkeypatch, fail):
    seen: list = []

    async def records(ctx):
        seen.append(get_refresh_actor())
        yield {"type": "token", "text": "ok"}
        if fail:
            raise RuntimeError("model fell over")

    _quiet(monkeypatch, _ctx_stream(records))
    _real_actor(monkeypatch)
    sock = _FakeSocket()
    await _run(sock, as_user)
    assert seen == [str(as_user.user_id)]
    assert get_refresh_actor() is None
    assert ("error" in [f["type"] for f in sock.frames]) is fail


async def test_a_task_started_after_the_turn_does_not_inherit_the_actor(as_user, monkeypatch):
    # The follow-up suggestions are created in the socket's context once the answer is saved.
    inherited: list = []

    async def records(ctx):
        yield {"type": "token", "text": "ok"}

    async def followups(*args, **kwargs):
        inherited.append(get_refresh_actor())
        return []

    _quiet(monkeypatch, _ctx_stream(records))
    _real_actor(monkeypatch)
    monkeypatch.setattr(ws_mod, "generate_followups", followups)
    await _run(_FakeSocket(), as_user)
    assert inherited == [None]


async def test_the_actor_is_cleared_when_the_turn_cannot_start(as_user, monkeypatch):
    # The preamble build fails after the turn's setup: nothing may be left set.
    async def boom(*args, **kwargs):
        raise RuntimeError("db hiccup")

    _quiet(monkeypatch, _ctx_stream(lambda ctx: None))
    _real_actor(monkeypatch)
    monkeypatch.setattr(ws_mod, "_build_turn_preamble", boom)
    with pytest.raises(RuntimeError):
        await _run(_FakeSocket(), as_user)
    assert get_refresh_actor() is None
