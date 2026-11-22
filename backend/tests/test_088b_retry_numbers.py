"""088b (SPEC-004): every number on a ``model_retry`` frame is finite and non-negative.

A non-finite or non-numeric ``attempt``/``max_attempts`` must neither end the turn nor reach the
browser as bare ``NaN``. Asserted on the frames the socket sent and on the turn's answer.
"""

from __future__ import annotations

import json

import pytest

from backend.app.api import ws as ws_mod
from backend.app.schemas import ChatTurn
from backend.tests.test_080_thinking_ws import _stream
from backend.tests.test_proposal_ws import MODEL, _FakeSocket, _identity, _quiet


@pytest.mark.parametrize(
    "attempt, max_attempts",
    [
        (float("nan"), 5),
        (2, float("nan")),
        (float("inf"), float("-inf")),
        ("x", None),
        ([1], {"n": 2}),
    ],
)
async def test_odd_attempt_numbers_make_a_valid_frame_and_the_turn_goes_on(
    as_user, monkeypatch, attempt, max_attempts
):
    record = {"type": "model_retry", "attempt": attempt, "max_attempts": max_attempts, "wait_s": 4.0}
    _quiet(monkeypatch, _stream(record, {"type": "token", "text": "ok"}))
    sock = _FakeSocket()
    task = await ws_mod._handle_turn(sock, ChatTurn(model=MODEL, content="q"), _identity(as_user))
    if task is not None:
        await task
    types = [f["type"] for f in sock.frames]
    assert "error" not in types and types[-1] == "done"  # the turn went on to its answer
    (frame,) = [f for f in sock.frames if f["type"] == "model_retry"]
    json.dumps(frame, allow_nan=False)  # what the browser's JSON.parse accepts
    for key in ("attempt", "max_attempts"):
        assert isinstance(frame[key], int) and frame[key] >= 0
    assert frame["wait_s"] == 4.0
