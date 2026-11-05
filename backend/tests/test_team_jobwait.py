"""Team job waiter (.claude/team/jobwait.py): detached jobs and warm-tick waits."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

JOBWAIT = Path(__file__).resolve().parents[2] / ".claude" / "team" / "jobwait.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def jw(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    e = {k: v for k, v in os.environ.items() if k != "TEAM_JOBS_DIR"}
    e.update({"JOBWAIT_TICK": "1", "JOBWAIT_POLL": "0.1", **(env or {})})
    return subprocess.run([sys.executable, str(JOBWAIT), *args], cwd=cwd, env=e,
                          capture_output=True, text=True, timeout=30)


def test_start_wait_exit_0_with_tail_and_grep(repo: Path) -> None:
    r = jw(repo, "start", "ok", "--", "sh", "-c", "echo RESULT one; seq 1 30; echo bye >&2")
    assert r.returncode == 0 and r.stdout.strip().endswith("ok.log")
    w = jw(repo, "wait", "ok", "--tail", "2", "--grep", "RESULT")
    assert w.returncode == 0
    assert "bye" in w.stdout and "RESULT one" in w.stdout and "exited 0" in w.stdout


def test_wait_exit_1_prints_status(repo: Path) -> None:
    jw(repo, "start", "bad", "--", "sh", "-c", "echo boom; exit 7")
    w = jw(repo, "wait", "bad")
    assert w.returncode == 1 and "exit 7" in w.stdout and "boom" in w.stdout


def test_job_uses_callers_cwd(repo: Path) -> None:
    jw(repo, "start", "pwd", "--", "pwd")
    assert str(repo.resolve()) in jw(repo, "wait", "pwd").stdout


def test_warm_tick_then_window_over(repo: Path) -> None:
    jw(repo, "start", "slow", "--", "sleep", "30")
    t = jw(repo, "wait", "slow", "--warm")
    assert t.returncode == 3 and "warm tick" in t.stdout and "identical command" in t.stdout
    o = jw(repo, "wait", "slow", "--warm", "--warm-for", "0")
    assert o.returncode == 2 and "warm window over; re-arm without --warm" in o.stdout
    p = jw(repo, "wait", "slow", "--timeout", "1")
    assert p.returncode == 2
    jw(repo, "clean", "slow")  # running: kept
    assert "running" in jw(repo, "status", "slow").stdout


def test_lost_job(repo: Path) -> None:
    jw(repo, "start", "gone", "--", "sleep", "30")
    pid = int(jw(repo, "status").stdout and next(
        int(x) for x in [__import__("json").load(open(next(
            (repo / ".git" / "team-jobs").glob("*/gone.json"))))["pid"]]))
    os.kill(pid, signal.SIGKILL)
    deadline = time.time() + 5
    while time.time() < deadline:
        w = jw(repo, "wait", "gone", "--timeout", "1")
        if w.returncode != 2:
            break
    assert w.returncode == 1 and "lost" in w.stdout


def test_status_clean_and_duplicate_refused(repo: Path) -> None:
    jw(repo, "start", "dup", "--", "sleep", "30")
    again = jw(repo, "start", "dup", "--", "true")
    assert again.returncode != 0 and "still running" in again.stderr
    jw(repo, "start", "done", "--", "true")
    jw(repo, "wait", "done")
    st = jw(repo, "status").stdout
    assert "dup  running" in st and "done  exit 0" in st
    assert "removed done" in jw(repo, "clean", "done").stdout
    assert "done" not in jw(repo, "status").stdout


def test_worktree_safe_and_separate_names(repo: Path, tmp_path_factory) -> None:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"], cwd=repo, check=True,
                   env={**os.environ, **env})
    wt = tmp_path_factory.mktemp("wt") / "feature"
    subprocess.run(["git", "worktree", "add", "-q", str(wt)], cwd=repo, check=True)
    assert (wt / ".git").is_file()
    jw(repo, "start", "same", "--", "echo", "main-tree")
    jw(wt, "start", "same", "--", "echo", "wt-tree")
    assert "main-tree" in jw(repo, "wait", "same").stdout
    assert "wt-tree" in jw(wt, "wait", "same").stdout
    assert len(list((repo / ".git" / "team-jobs").iterdir())) == 2
