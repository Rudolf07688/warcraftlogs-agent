"""check.py (.claude/team/check.py): the suite for the area a branch touched, with honest receipts.

check.py is a stand-alone CLI, so each test runs it in a fresh temporary git repository with fake
`uv` (pytest), `npm` and `npx` (vitest) first on PATH. The fakes log every call, so a test can see
which suites ran. They read a mode from the repo's files, never from the environment: check.py
runs them under `env -i`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TEAM = Path(__file__).resolve().parents[2] / ".claude" / "team"
CHECK = TEAM / "check.py"

FAKE_UV = '''#!/usr/bin/env python3
import sys
open({calls!r}, "a").write("pytest " + " ".join(a for a in sys.argv[1:] if a.startswith("tests") or a.endswith(".py")) + "\\n")
print("...\\n3 passed in 0.10s")
'''

FAKE_NPM = '''#!/usr/bin/env python3
import os, sys
open({calls!r}, "a").write("npm " + " ".join(sys.argv[1:]) + "\\n")
if sys.argv[1] == "ci":
    os.makedirs("node_modules")
elif sys.argv[1:3] == ["run", "build"]:
    open("tsconfig.tsbuildinfo", "a").write("rebuilt\\n")
    print("built in 1s")
'''

# vitest: the behaviour follows src/x.ts, the "code under test"
FAKE_NPX = '''#!/usr/bin/env python3
import os, sys, time
open({calls!r}, "a").write("npx " + " ".join(sys.argv[1:]) + "\\n")
code = open("src/x.ts").read()
if "SLOW" in code:
    open({started!r}, "w").write("1")
    time.sleep(60)
if "BROKEN" in code:
    print(" FAIL  src/x.test.tsx [ src/x.test.tsx ]\\nError: Transform failed\\n")
    print("\\u23af\\u23af Failed Suites 1 \\u23af\\u23af")
    print(" Test Files  1 failed (1)\\n      Tests  no tests\\n   Duration  10ms")
    sys.exit(1)
if "BAD" in code:
    print(" FAIL  src/x.test.tsx > x > returns one")
    print(" Test Files  1 failed (1)\\n      Tests  1 failed | 1 passed (2)\\n   Duration  10ms")
    sys.exit(1)
print(" Test Files  1 passed (1)\\n      Tests  2 passed (2)\\n   Duration  10ms")
'''


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def commit(repo: Path, msg: str = "c") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def make_repo(tmp_path: Path) -> Path:
    """A repo on branch `feature` cut from `main`, with backend, frontend and docs files, and
    fake uv/npm/npx in tmp_path/bin (calls logged to tmp_path/calls.log)."""
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "T")
    git(r, "config", "core.hooksPath", "/dev/null")
    write(r, ".gitignore", "node_modules/\n")
    write(r, "backend/app/svc.py", "X = 1\n")
    write(r, "backend/tests/test_svc.py", "def test_x():\n    assert True\n")
    write(r, "frontend/src/x.ts", "export const x = 1;\n")
    write(r, "frontend/src/x.test.tsx", "// test\n")
    write(r, "frontend/tsconfig.tsbuildinfo", "{}\n")
    write(r, "docs/notes.md", "notes\n")
    commit(r, "init")
    git(r, "switch", "-q", "-c", "feature")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls, started = str(tmp_path / "calls.log"), str(tmp_path / "started")
    for name, body in (("uv", FAKE_UV), ("npm", FAKE_NPM), ("npx", FAKE_NPX)):
        (bindir / name).write_text(body.format(calls=calls, started=started))
        (bindir / name).chmod(0o755)
    return r


def run_tool(repo: Path, tool: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"HOME": os.environ["HOME"], "PATH": f"{repo.parent / 'bin'}:{os.environ['PATH']}"}
    return subprocess.run([sys.executable, str(tool), *args], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=120)


def calls(repo: Path) -> list[str]:
    log = repo.parent / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def receipt(repo: Path) -> dict:
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    return json.loads((repo / ".git" / "team-checks" / "receipts" / f"{tree}.json").read_text())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def test_frontend_only_branch_runs_npm_ci_vitest_and_build_and_records_the_area(repo: Path) -> None:
    write(repo, "frontend/src/x.ts", "export const x = 2;\n")
    commit(repo)
    out = run_tool(repo, CHECK, "run", "--as", "tomas")
    assert out.returncode == 0, out.stdout + out.stderr
    assert calls(repo) == ["npm ci --no-audit --no-fund", "npx vitest run", "npm run build"]
    assert "RESULT PASS" in out.stdout and "area=frontend" in out.stdout
    rec = receipt(repo)
    assert rec["area"] == "frontend" and rec["commands"] == ["vitest run", "npm run build"]
    assert not git(repo, "status", "--porcelain")  # the build's tsbuildinfo rewrite was undone
    v = run_tool(repo, CHECK, "verify")
    assert v.returncode == 0 and "area=frontend" in v.stdout and "full suite" not in v.stdout
    assert run_tool(repo, CHECK, "verify", "--need-full").returncode == 1


def test_backend_branch_runs_pytest_only(repo: Path) -> None:
    write(repo, "backend/app/svc.py", "X = 2\n")
    commit(repo)
    out = run_tool(repo, CHECK, "run", "--as", "tomas")
    assert out.returncode == 0, out.stdout + out.stderr
    assert calls(repo) == ["pytest "]
    assert receipt(repo)["area"] == "backend"
    assert not (repo / "frontend" / "node_modules").exists()


def test_both_areas_and_existing_node_modules_skip_npm_ci(repo: Path) -> None:
    (repo / "frontend" / "node_modules").mkdir()
    write(repo, "backend/app/svc.py", "X = 2\n")
    write(repo, "frontend/src/x.ts", "export const x = 2;\n")
    commit(repo)
    out = run_tool(repo, CHECK, "run", "--as", "tomas")
    assert out.returncode == 0, out.stdout + out.stderr
    assert calls(repo) == ["pytest ", "npx vitest run", "npm run build"]
    assert receipt(repo)["area"] == "backend+frontend"


def test_config_only_branch_needs_targeted_tests_and_then_gets_a_receipt(repo: Path) -> None:
    write(repo, "docs/notes.md", "more notes\n")
    commit(repo)
    refused = run_tool(repo, CHECK, "run", "--as", "tomas")
    assert refused.returncode == 3 and "config files only" in refused.stdout and calls(repo) == []
    out = run_tool(repo, CHECK, "run", "backend/tests/test_svc.py", "--as", "tomas")
    assert out.returncode == 0, out.stdout + out.stderr
    assert calls(repo) == ["pytest backend/tests/test_svc.py"]
    rec = receipt(repo)
    assert rec["area"] == "config" and rec["commands"] == ["pytest backend/tests/test_svc.py"]


def test_targeted_run_on_a_code_branch_and_a_dirty_tree_write_no_receipt(repo: Path) -> None:
    write(repo, "backend/app/svc.py", "X = 2\n")
    commit(repo)
    targeted = run_tool(repo, CHECK, "run", "backend/tests/test_svc.py", "--as", "tomas")
    assert targeted.returncode == 0 and "RECEIPT" not in targeted.stdout
    write(repo, "backend/app/svc.py", "X = 3\n")
    dirty = run_tool(repo, CHECK, "run", "--as", "tomas")
    assert dirty.returncode == 0 and "no receipt: 1 uncommitted" in dirty.stdout
    assert run_tool(repo, CHECK, "verify").returncode == 1


def test_a_failing_vitest_is_a_fail_without_receipt(repo: Path) -> None:
    (repo / "frontend" / "node_modules").mkdir()
    write(repo, "frontend/src/x.ts", "BAD\n")
    commit(repo)
    out = run_tool(repo, CHECK, "run", "--as", "tomas")
    assert out.returncode == 1 and "RESULT FAIL" in out.stdout
    assert "FAIL  src/x.test.tsx > x > returns one" in out.stdout and "RECEIPT" not in out.stdout


def test_full_runs_every_suite_whatever_the_diff(repo: Path) -> None:
    (repo / "frontend" / "node_modules").mkdir()
    out = run_tool(repo, CHECK, "run", "--full", "--as", "maren")
    assert out.returncode == 0, out.stdout + out.stderr
    assert calls(repo) == ["pytest ", "npx vitest run", "npm run build"]
    assert receipt(repo)["area"] == "full"
    assert run_tool(repo, CHECK, "verify", "--need-full").returncode == 0
