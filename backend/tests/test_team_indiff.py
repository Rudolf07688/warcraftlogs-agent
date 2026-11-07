"""indiff.py (.claude/team/indiff.py, sc-537): is a finding in this sprint's diff or older code?

Each test builds a small history in a temporary git repo: main -> sprint-x -> a stream branch.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

INDIFF = Path(__file__).resolve().parents[2] / ".claude" / "team" / "indiff.py"


def git(repo: Path, *args: str, date: str = "2026-10-20T10:00:00+00:00") -> str:
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@x"}
    return subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True,
                          check=True).stdout.strip()


def commit(repo: Path, msg: str, date: str, **files: str) -> str:
    for name, text in files.items():
        (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg, date=date)
    return git(repo, "rev-parse", "HEAD")


def indiff(repo: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(INDIFF), *args], cwd=repo, input=stdin,
                          capture_output=True, text=True, timeout=60)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    commit(tmp_path, "old code", "2026-10-20T10:00:00+00:00", **{"a.py": "one\ntwo\nthree\nfour\n"})
    git(tmp_path, "checkout", "-qb", "sprint-x")
    commit(tmp_path, "sprint change", "2026-11-07T10:00:00+00:00", **{"a.py": "one\nTWO\nthree\nfour\n"})
    git(tmp_path, "checkout", "-qb", "067-stream")
    commit(tmp_path, "stream change", "2026-11-07T12:00:00+00:00", **{"a.py": "one\nTWO\nthree\nFOUR\n"})
    return tmp_path


def verdicts(out: str) -> dict[str, str]:
    return {line.split()[0]: line.split()[1] for line in out.splitlines()[1:]}


def test_changed_lines_are_in_diff_and_old_lines_show_their_commit_and_date(repo: Path) -> None:
    r = indiff(repo, "a.py:1", "a.py:2", "--base", "main")
    assert r.returncode == 0, r.stderr
    rows = r.stdout.splitlines()
    assert rows[1].startswith("a.py:1  OLDER") and "2026-10-20 old code" in rows[1]
    assert rows[2].startswith("a.py:2  IN DIFF") and "2026-11-07 sprint change" in rows[2]


def test_default_base_is_the_stream_diff_on_a_stream_and_the_sprint_diff_on_the_sprint(repo: Path) -> None:
    stream = verdicts(indiff(repo, "a.py:2", "a.py:4").stdout)
    assert stream == {"a.py:2": "OLDER", "a.py:4": "IN"}  # base: merge base with sprint-x
    git(repo, "checkout", "-q", "sprint-x")
    assert verdicts(indiff(repo, "a.py:2", "a.py:4").stdout) == {"a.py:2": "IN", "a.py:4": "OLDER"}
    assert "merge base with main" in indiff(repo, "a.py:2").stdout


def test_a_pasted_report_ranges_uncommitted_and_missing_lines(repo: Path) -> None:
    (repo / "a.py").write_text("one\nTWO\nthree\nFOUR\nfive\n")
    report = ("- **BUG-001** `a.py:5`: new line\n- **BUG-002** a.py:1-2 range\n"
              f"- {repo}/a.py:1 absolute path\n- gone.py:3 missing\n")
    r = indiff(repo, "--base", "main", stdin=report)
    rows = r.stdout.splitlines()[1:]
    assert rows[0].startswith("a.py:5  IN DIFF") and "uncommitted" in rows[0]
    assert rows[1].startswith("a.py:1-2  IN DIFF") and "(1/2 lines)" in rows[1]
    assert rows[2].startswith("a.py:1  OLDER")
    assert rows[3].startswith("gone.py:3  ?")
    assert len(rows) == 4
    assert "1 older" in r.stderr and "1 unresolved" in r.stderr
