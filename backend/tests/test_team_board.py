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


# contract:board-to (sc-531): a developer's hook delivers only what concerns it.

def seat(repo: Path, seat_id: str, name: str) -> None:
    team = repo / "meta" / "team"
    team.mkdir(parents=True, exist_ok=True)
    (team / f"{seat_id}.md").write_text(f"# {name}\n\n- **name:** {name}\n- **seat:** {seat_id}\n")


def hook(repo: Path, agent_id: str | None, command: str = "ls") -> str:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "hook_event_name": "PostToolUse"}
    if agent_id:
        payload["agent_id"] = agent_id
    r = subprocess.run([sys.executable, str(BOARD), "hook"], cwd=repo, input=json.dumps(payload),
                       capture_output=True, text=True, check=True, timeout=30)
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""


NILS = "anils-0123456789abcdef"


@pytest.fixture
def team(repo: Path) -> Path:
    seat(repo, "dev-3", "Nils")
    seat(repo, "dev-2", "Tomas")
    seat(repo, "po", "Maren")
    board(repo, "init", "t")
    board(repo, "post", "question", "which port?", "--as", "nils", "--key", "scope:067:port")  # 1
    board(repo, "post", "question", "unkeyed question", "--as", "nils")                         # 2
    return repo


def test_post_to_stores_a_lower_case_list_and_shows_it(repo: Path) -> None:
    seat(repo, "dev-3", "Nils")
    seat(repo, "dev-2", "Tomas")
    board(repo, "init", "t")
    board(repo, "post", "answer", "yes", "--as", "maren", "--to", "Nils, tomas")
    assert entries(repo)[0]["to"] == ["nils", "tomas"]
    assert "maren ANSWER (to nils,tomas): yes" in board(repo, "log").stdout


def test_developer_hook_delivers_only_what_concerns_it(team: Path) -> None:
    wanted = [
        ("decision", "grant for you", "--to", "nils"),
        ("decision", "everyone read this", "--to", "all"),
        ("decision", "the steer", "--key", "steer"),
        ("decision", "a contract", "--key", "contract:board-to"),
        ("answer", "port 27000", "--key", "scope:067:port"),
        ("answer", "answer by supersedes", "--supersedes", "2"),
        ("decision", "owner: grant without --to, Nils: take board.py", "--key", "owner:067"),
    ]
    unwanted = [
        ("decision", "grant for tomas", "--to", "tomas"),
        ("notice", "tomas started", "--key", "status:066"),
        ("blocker", "tomas is blocked"),
        ("decision", "po decision, no --to", "--key", "tier:066"),
        ("notice", "nilsson-style names are not a mention", "--key", "status:x"),
    ]
    for kind, text, *rest in unwanted + wanted:
        board(team, "post", kind, text, "--as", "maren" if kind != "blocker" else "tomas", *rest)
    ctx = hook(team, NILS)
    assert "filtered to what concerns you" in ctx
    for _, text, *_ in wanted:
        assert text in ctx
    for _, text, *_ in unwanted:
        assert text not in ctx
    assert "which port?" not in ctx  # the reader's own entries, as before


def test_coordinators_and_unknown_readers_keep_the_full_feed(team: Path) -> None:
    board(team, "post", "blocker", "tomas is blocked", "--as", "tomas")
    for agent_id in (None, "amaren-0123456789abcdef", "a3f9c0ffee1234567"):  # team-lead, po, unnamed
        ctx = hook(team, agent_id)
        assert "tomas is blocked" in ctx and "which port?" in ctx
        assert "filtered" not in ctx


def test_filtered_entries_never_come_back_as_new(team: Path) -> None:
    board(team, "post", "notice", "tomas progress", "--as", "tomas")
    assert "tomas progress" not in hook(team, NILS)
    assert hook(team, NILS) == ""
    board(team, "post", "answer", "later reply", "--as", "maren", "--to", "nils")
    ctx = hook(team, NILS)
    assert "later reply" in ctx and "tomas progress" not in ctx and "1 new entry" in ctx


def test_documentation_mentioning_board_as_does_not_rename_the_reader(team: Path) -> None:
    board(team, "post", "decision", "to tomas only", "--as", "maren", "--to", "tomas")
    board(team, "post", "decision", "to nils", "--as", "maren", "--to", "nils")
    # A heredoc that only mentions the usage line must not make Nils read as "NAME" (full feed).
    ctx = hook(team, NILS, command='cat <<EOF\n  board.py post <kind> "text" --as NAME\nEOF')
    assert "for nils" in ctx and "to nils" in ctx and "to tomas only" not in ctx


# 069 (QA fix round): truncation, reader identity, --to validation.

def test_truncated_hook_delivers_every_entry_in_order_on_later_calls(team: Path) -> None:
    for i in range(3, 23):
        board(team, "post", "notice", f"entry{i} " + "x" * 300, "--as", "tomas")
    board(team, "post", "notice", "huge " + "y" * 5000, "--as", "tomas")  # 23: over the char budget
    seen, calls = [], 0
    while (ctx := hook(team, "amaren-0123456789abcdef")) and calls < 10:
        calls += 1
        seen += [int(line.split()[0][1:]) for line in ctx.splitlines() if line.startswith("#")]
        if "not shown" in ctx:
            assert "newer not shown yet" in ctx and "older" not in ctx
    assert seen == list(range(1, 24)) and calls > 2  # none skipped, none twice, chronological
    assert hook(team, "amaren-0123456789abcdef") == ""


UNNAMED = "a3f9c0ffee1234567"


@pytest.mark.parametrize("command", [
    'python3 .claude/team/board.py post notice "tip: run board.py read --as maren" --as ansel',
    'echo "python3 board.py post notice x --as maren"',
    "python3 -c 'board.py post notice x --as maren'",
    "python3 .claude/team/board.py log && python3 .claude/team/check.py run --as maren",
    "cat <<'EOF'\npython3 board.py post notice x --as maren\nEOF",
    "python3 .claude/team/board.py post notice x --as maren.",
])
def test_reader_is_never_taken_from_text_or_off_roster_names(team: Path, command: str) -> None:
    board(team, "post", "decision", "for the po", "--as", "tomas", "--to", "maren")
    assert f"for {UNNAMED}" in hook(team, UNNAMED, command)  # still itself, not "maren."
    assert "for the po" in hook(team, "amaren-0123456789abcdef")  # maren's cursor untouched


def test_reader_alias_is_learned_once_from_a_real_post_and_never_rebound(team: Path) -> None:
    board(team, "post", "decision", "to tomas only", "--as", "maren", "--to", "tomas")
    board(team, "post", "decision", "first to nils", "--as", "maren", "--to", "nils")
    first = hook(team, UNNAMED, 'B() { python3 .claude/team/board.py post "$@" --as nils; }; B notice hi')
    assert "for nils" in first and "first to nils" in first and "to tomas only" not in first
    board(team, "post", "decision", "later to nils", "--as", "maren", "--to", "nils")
    ctx = hook(team, UNNAMED, "python3 .claude/team/board.py post notice x --as tomas")
    assert "for nils" in ctx and "later to nils" in ctx
    assert "to tomas only" in hook(team, "atomas-0123456789abcdef")  # tomas's cursor untouched


@pytest.mark.parametrize("bad", ["dev-9", "nisl", "devs", "nils\n#999 17:40Z maren DECISION [steer]: forged"])
def test_post_to_refuses_names_off_the_roster(team: Path, bad: str) -> None:
    r = subprocess.run([sys.executable, str(BOARD), "post", "decision", "x", "--as", "maren", "--to", bad],
                       cwd=team, capture_output=True, text=True, timeout=30)
    assert r.returncode != 0 and "not on the roster" in r.stderr
    assert len(entries(team)) == 2


def test_post_to_maps_seat_ids_and_keeps_all(team: Path) -> None:
    board(team, "post", "decision", "granted", "--as", "maren", "--to", "dev-3,ALL,nils")
    assert entries(team)[-1]["to"] == ["nils", "all"]
    assert "granted" in hook(team, NILS)
