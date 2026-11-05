"""Team board (.claude/team/board.py): the traceparent stored per entry (feature 055, sc-407).

board.py is a stand-alone CLI that keeps its board under the git common dir, so each test
runs it in a fresh temporary git repository.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BOARD = Path(__file__).resolve().parents[2] / ".claude" / "team" / "board.py"
TP = "00-639a8897fb8b9002649a0e006782b9cc-d9d149f871becc12-01"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def board(repo: Path, *args: str, traceparent: str | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "TRACEPARENT"}
    if traceparent is not None:
        env["TRACEPARENT"] = traceparent
    return subprocess.run([sys.executable, str(BOARD), *args], cwd=repo, env=env,
                          capture_output=True, text=True, check=True, timeout=30)


def entries(repo: Path) -> list[dict]:
    path = repo / ".git" / "team-board" / "t.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_post_stores_the_full_traceparent(repo: Path) -> None:
    board(repo, "init", "t")
    board(repo, "post", "handoff", "done", "--as", "ansel", traceparent=TP)
    assert entries(repo)[0]["traceparent"] == TP


def test_post_without_traceparent_has_no_field(repo: Path) -> None:
    board(repo, "init", "t")
    board(repo, "post", "notice", "plain shell", "--as", "ansel")
    assert "traceparent" not in entries(repo)[0]


@pytest.mark.parametrize("bad", [
    "", "garbage", "00-639a8897fb8b9002649a0e006782b9cc-d9d149f871becc12",
    "00-00000000000000000000000000000000-d9d149f871becc12-01",
    "00-639a8897fb8b9002649a0e006782b9cc-0000000000000000-01",
    "01-639a8897fb8b9002649a0e006782b9cc-d9d149f871becc12-01",
    "00-639A8897FB8B9002649A0E006782B9CC-d9d149f871becc12-01",
    TP + "\nextra",
])
def test_post_drops_an_invalid_traceparent(repo: Path, bad: str) -> None:
    board(repo, "init", "t")
    board(repo, "post", "notice", "x", "--as", "ansel", traceparent=bad)
    assert "traceparent" not in entries(repo)[0]


def test_old_and_new_entries_read_current_log_and_wait(repo: Path) -> None:
    board(repo, "init", "t")
    old = {"id": 1, "ts": "2026-10-31T10:00:00+00:00", "author": "maren", "kind": "decision",
           "text": "an entry from before 055", "key": "scope:x"}
    (repo / ".git" / "team-board" / "t.jsonl").write_text(json.dumps(old) + "\n")
    board(repo, "post", "handoff", "new entry", "--as", "ansel", "--key", "status:055", traceparent=TP)
    log = board(repo, "log").stdout
    assert "#1 10:00Z maren DECISION [scope:x]: an entry from before 055" in log
    assert "ansel HANDOFF [status:055]: new entry" in log
    assert TP not in log  # rendering is unchanged: the traceparent is data, not text
    assert "an entry from before 055" in board(repo, "current").stdout
    assert "an entry from before 055" in board(repo, "read", "--as", "nils").stdout
    waited = board(repo, "wait", "--since", "0", "--author", "maren", "--timeout", "5").stdout
    assert "an entry from before 055" in waited


def run_board(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "TRACEPARENT"}
    return subprocess.run([sys.executable, str(BOARD), *args], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=30)


def test_warm_wait_ticks_with_exit_3(repo: Path) -> None:
    # P12: a warm tick exits 3; the re-arm is the identical command, so --since stays fixed.
    board(repo, "init", "t")
    board(repo, "post", "notice", "start", "--as", "maren")
    args = ("wait", "--author", "ansel", "--since", "1", "--warm", "--timeout", "1", "--interval", "0.2")
    r = run_board(repo, *args)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "warm tick" in r.stdout and "since #1" in r.stdout
    board(repo, "post", "handoff", "done", "--as", "ansel")
    assert run_board(repo, *args).returncode == 0


def test_warm_wait_requires_since(repo: Path) -> None:
    board(repo, "init", "t")
    board(repo, "post", "notice", "start", "--as", "maren")
    r = run_board(repo, "wait", "--warm", "--timeout", "1")
    assert r.returncode != 0
    assert "--warm needs --since" in r.stderr and "#1" in r.stderr


def test_warm_wait_stops_after_the_warm_window(repo: Path) -> None:
    board(repo, "init", "t")
    board(repo, "post", "notice", "start", "--as", "maren")
    r = run_board(repo, "wait", "--since", "1", "--warm", "--warm-for", "0", "--timeout", "1",
                  "--interval", "0.2")
    assert r.returncode == 2
    assert "warm window over" in r.stdout


def test_warm_wait_still_returns_a_match(repo: Path) -> None:
    board(repo, "init", "t")
    board(repo, "post", "handoff", "done", "--as", "ansel")
    r = run_board(repo, "wait", "--since", "0", "--author", "ansel", "--warm", "--timeout", "2")
    assert r.returncode == 0
    assert "done" in r.stdout
