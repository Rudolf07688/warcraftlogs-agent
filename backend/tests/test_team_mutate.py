"""mutate.py (.claude/team/mutate.py) with vitest: the same guarantees as with pytest.

A frontend --test runs under vitest (a fake `npx` from test_team_check, driven by the mutated
file), the baseline must pass, the file is restored byte for byte even on SIGTERM, and a suite
that fails to load is not a bite.
"""
from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from backend.tests.test_team_check import TEAM, calls, make_repo, run_tool, write

MUTATE = TEAM / "mutate.py"
SRC, TEST = "frontend/src/x.ts", "frontend/src/x.test.tsx"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def setup(tmp_path: Path) -> Path:
    repo = make_repo(tmp_path)
    (repo / "frontend" / "node_modules").mkdir()
    return repo


def test_a_behaviour_change_bites_under_vitest_and_the_file_is_restored(tmp_path: Path) -> None:
    repo = setup(tmp_path)
    before = sha(repo / SRC)
    out = run_tool(repo, MUTATE, SRC, "--old", "x = 1", "--new", "x = BAD", "--test", TEST)
    assert out.returncode == 0 and out.stdout.startswith("BITES"), out.stdout + out.stderr
    assert calls(repo) == ["npx vitest run src/x.test.tsx"] * 2   # baseline, then mutated
    assert sha(repo / SRC) == before


def test_a_suite_that_fails_to_load_is_not_a_bite(tmp_path: Path) -> None:
    repo = setup(tmp_path)
    before = sha(repo / SRC)
    out = run_tool(repo, MUTATE, SRC, "--old", "x = 1", "--new", "x = BROKEN(", "--test", TEST)
    assert out.returncode == 1 and "NOT A REAL BITE" in out.stdout, out.stdout + out.stderr
    assert sha(repo / SRC) == before


def test_a_red_baseline_refuses_before_mutating(tmp_path: Path) -> None:
    repo = setup(tmp_path)
    write(repo, SRC, "export const x = 1; // BAD\n")
    out = run_tool(repo, MUTATE, SRC, "--old", "x = 1", "--new", "x = 2", "--test", TEST)
    assert out.returncode == 1 and "baseline is not green" in out.stderr
    assert len(calls(repo)) == 1


def test_mixed_frontend_and_backend_tests_are_refused(tmp_path: Path) -> None:
    repo = setup(tmp_path)
    out = run_tool(repo, MUTATE, SRC, "--old", "x = 1", "--new", "x = 2",
                   "--test", TEST, "--test", "backend/tests/test_svc.py")
    assert out.returncode == 1 and "mixes frontend" in out.stderr and calls(repo) == []


def test_sigterm_mid_run_restores_the_file(tmp_path: Path) -> None:
    repo = setup(tmp_path)
    before = sha(repo / SRC)
    env = {"HOME": os.environ["HOME"], "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}
    proc = subprocess.Popen([sys.executable, str(MUTATE), SRC, "--old", "x = 1", "--new", "x = SLOW",
                             "--test", TEST], cwd=repo, env=env, start_new_session=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 60
        while not (tmp_path / "started").exists():
            assert time.monotonic() < deadline and proc.poll() is None, proc.communicate()
            time.sleep(0.1)
        assert (repo / SRC).read_text() != "export const x = 1;\n"   # mutated while vitest runs
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=30) == 130
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)   # whatever is left, e.g. the sleeping fake vitest
        except ProcessLookupError:
            pass
    assert sha(repo / SRC) == before
