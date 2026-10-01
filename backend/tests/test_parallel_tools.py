"""US2: shared per-turn scratch store for concurrent tool outputs.

These cover what the app owns: large outputs survive intact, concurrent writers
don't clobber each other, successful and failed tool results coexist, and the
store cleans up. ADK-level parallel execution timing is verified in quickstart.md.
"""

from __future__ import annotations

import asyncio
import os

from backend.app.scratch import TurnScratch


def test_large_payload_round_trips_intact():
    scratch = TurnScratch("conv-1")
    try:
        big = "x" * (2 * 1024 * 1024)  # 2 MB, simulating a full report table
        record = {"name": "get_report_table", "ok": True, "result": {"data": big}}
        scratch.write("call-1", record)
        got = scratch.read("call-1")
        assert got is not None
        assert got["result"]["data"] == big  # no truncation (FR-008)
    finally:
        scratch.cleanup()


async def test_concurrent_writers_do_not_clobber():
    scratch = TurnScratch("conv-2")
    try:
        async def write(i: int) -> None:
            await asyncio.to_thread(
                scratch.write, f"call-{i}", {"i": i, "result": "y" * (100 * 1024)}
            )

        await asyncio.gather(*(write(i) for i in range(20)))

        # Every concurrent call's full result is present and correct (FR-007).
        for i in range(20):
            rec = scratch.read(f"call-{i}")
            assert rec is not None and rec["i"] == i
    finally:
        scratch.cleanup()


def test_success_and_failure_results_coexist():
    scratch = TurnScratch("conv-3")
    try:
        scratch.write("ok-call", {"ok": True, "result": {"status": "success"}})
        scratch.write("bad-call", {"ok": False, "result": {"status": "error"}})
        # A failed tool's result is still captured alongside the successful ones,
        # so the turn can use the good results and report the failure (FR-009).
        assert scratch.read("ok-call")["ok"] is True
        assert scratch.read("bad-call")["ok"] is False
    finally:
        scratch.cleanup()


def test_missing_key_reads_none():
    scratch = TurnScratch("conv-4")
    try:
        assert scratch.read("never-written") is None
    finally:
        scratch.cleanup()


def test_cleanup_removes_directory():
    scratch = TurnScratch("conv-5")
    scratch.write("c", {"result": 1})
    assert os.path.isdir(scratch.dir)
    scratch.cleanup()
    assert not os.path.exists(scratch.dir)
    scratch.cleanup()  # idempotent — no error on second call


def test_stream_response_accepts_scratch_param():
    # Signature wiring guard: stream_response must accept the optional scratch arg.
    import inspect

    from backend.app.agent_runner import stream_response

    assert "scratch" in inspect.signature(stream_response).parameters
