"""check.py (.claude/team/check.py): the suite for the area a branch touched, with honest receipts.

check.py is a stand-alone CLI, so each test runs it in a fresh temporary git repository with fake
`uv` (pytest), `npm` and `npx` (vitest) first on PATH. The fakes log every call, so a test can see
which suites ran. They read a mode from the repo's files, never from the environment: check.py
runs them under `env -i`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TEAM = Path(__file__).resolve().parents[2] / ".claude" / "team"
CHECK = TEAM / "check.py"
_spec = importlib.util.spec_from_file_location("team_check", CHECK)
check_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_mod)

FAKE_UV = '''#!/usr/bin/env python3
import sys
open({calls!r}, "a").write("pytest " + " ".join(a for a in sys.argv[1:] if a.startswith("tests") or a.endswith(".py")) + "\\n")
print("...\\n3 passed in 0.10s")
'''

FAKE_NPM = '''#!/usr/bin/env python3
import os, shutil, sys
open({calls!r}, "a").write("npm " + " ".join(sys.argv[1:]) + "\\n")
if sys.argv[1] == "ci":
    shutil.rmtree("node_modules", ignore_errors=True)   # the real npm ci starts from nothing
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
    write(r, "frontend/package.json", '{"name": "f"}\n')
    write(r, "frontend/package-lock.json", '{"lockfileVersion": 3}\n')
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


def install_node_modules(repo: Path, stamped: bool = True) -> Path:
    """A frontend/node_modules as `npm ci` leaves it (stamped for the lockfile), or a bare one."""
    nm = repo / "frontend" / "node_modules"
    nm.mkdir(exist_ok=True)
    if stamped:
        (nm / check_mod.STAMP).write_text(check_mod.deps_stamp(str(repo / "frontend")))
    return nm


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
    install_node_modules(repo)
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
    install_node_modules(repo)
    write(repo, "frontend/src/x.ts", "BAD\n")
    commit(repo)
    out = run_tool(repo, CHECK, "run", "--as", "tomas")
    assert out.returncode == 1 and "RESULT FAIL" in out.stdout
    assert "FAIL  src/x.test.tsx > x > returns one" in out.stdout and "RECEIPT" not in out.stdout


def test_full_runs_every_suite_whatever_the_diff(repo: Path) -> None:
    install_node_modules(repo)
    out = run_tool(repo, CHECK, "run", "--full", "--as", "maren")
    assert out.returncode == 0, out.stdout + out.stderr
    assert calls(repo) == ["pytest ", "npx vitest run", "npm run build"]
    assert receipt(repo)["area"] == "full"
    assert run_tool(repo, CHECK, "verify", "--need-full").returncode == 0


def test_verify_refuses_a_receipt_whose_area_is_less_than_the_branch_touches(repo: Path) -> None:
    write(repo, "backend/app/svc.py", "X = 2\n")
    commit(repo, "backend change")
    write(repo, "docs/notes.md", "more notes\n")
    commit(repo, "docs")
    # a base chosen after the backend commit sees a config-only diff and the run writes a receipt
    out = run_tool(repo, CHECK, "run", "--base", "HEAD~1", "backend/tests/test_svc.py", "--as", "tomas")
    assert out.returncode == 0 and "area=config" in out.stdout, out.stdout + out.stderr
    assert receipt(repo)["area"] == "config"
    v = run_tool(repo, CHECK, "verify")
    assert v.returncode == 1 and "RUN NEEDED" in v.stdout and "area=config" in v.stdout
    assert "touches backend" in v.stdout
    # the receipt's own base is the merge target the caller names: then it is honest, and shown
    ok = run_tool(repo, CHECK, "verify", "--base", "HEAD~1")
    assert ok.returncode == 0 and "receipt base " + git(repo, "rev-parse", "HEAD~1")[:12] in ok.stdout


def test_verify_accepts_a_receipt_that_covers_the_branch_and_shows_the_base(repo: Path) -> None:
    write(repo, "backend/app/svc.py", "X = 2\n")
    commit(repo)
    assert run_tool(repo, CHECK, "run", "--as", "tomas").returncode == 0
    v = run_tool(repo, CHECK, "verify")
    assert v.returncode == 0 and f"receipt base {git(repo, 'rev-parse', 'main')[:12]}" in v.stdout


@pytest.mark.parametrize("cmd", ["run", "verify"])
def test_a_base_that_looks_like_a_git_option_is_refused_and_writes_nothing(
    repo: Path, tmp_path: Path, cmd: str
) -> None:
    write(repo, "docs/notes.md", "more notes\n")
    commit(repo)
    target = tmp_path / "pwned"
    out = run_tool(repo, CHECK, cmd, f"--base=--output={target}", *(["backend/tests/test_svc.py"] if cmd == "run" else []))
    assert out.returncode in (1, 3) and "REFUSED" in out.stdout
    assert not list(tmp_path.glob("pwned*")) and calls(repo) == []


# ---------------------------------------------------------------- BUG-013: a stale install is not reused

def frontend_change(repo: Path) -> None:
    write(repo, "frontend/src/x.ts", "export const x = 2;\n")
    commit(repo)


def test_a_bare_node_modules_without_the_stamp_is_reinstalled(repo: Path) -> None:
    install_node_modules(repo, stamped=False)   # e.g. an interrupted npm ci
    (repo / "frontend" / "node_modules" / "half-a-package").mkdir()
    frontend_change(repo)
    assert run_tool(repo, CHECK, "run", "--as", "tomas").returncode == 0
    assert calls(repo)[0] == "npm ci --no-audit --no-fund"
    assert not (repo / "frontend" / "node_modules" / "half-a-package").exists()


def test_a_changed_lockfile_reinstalls_and_an_unchanged_one_does_not(repo: Path) -> None:
    install_node_modules(repo)
    write(repo, "frontend/package-lock.json", '{"lockfileVersion": 3, "packages": {"a": 1}}\n')
    frontend_change(repo)
    assert run_tool(repo, CHECK, "run", "--as", "tomas").returncode == 0
    assert calls(repo) == ["npm ci --no-audit --no-fund", "npx vitest run", "npm run build"]
    # npm ci stamped the install it made: the next run (new tree, same lockfile) reuses it
    write(repo, "frontend/src/x.ts", "export const x = 3;\n")
    commit(repo)
    assert run_tool(repo, CHECK, "run", "--as", "tomas").returncode == 0
    assert calls(repo)[3:] == ["npx vitest run", "npm run build"]


def test_a_changed_package_json_reinstalls(repo: Path) -> None:
    install_node_modules(repo)
    write(repo, "frontend/package.json", '{"name": "f", "devDependencies": {"x": "1"}}\n')
    commit(repo)
    assert run_tool(repo, CHECK, "run", "--as", "tomas").returncode == 0
    assert calls(repo)[0] == "npm ci --no-audit --no-fund"


# ---------------------------------------------------------------- BUG-012: a weaker run keeps the stronger receipt

def both_areas(repo: Path) -> None:
    install_node_modules(repo)
    write(repo, "backend/app/svc.py", "X = 2\n")
    write(repo, "frontend/src/x.ts", "export const x = 2;\n")
    commit(repo)


def receipt_file(repo: Path) -> Path:
    return repo / ".git" / "team-checks" / "receipts" / f"{git(repo, 'rev-parse', 'HEAD^{tree}')}.json"


def test_an_area_run_does_not_overwrite_a_full_receipt_and_a_full_run_replaces_an_area_one(repo: Path) -> None:
    both_areas(repo)
    assert run_tool(repo, CHECK, "run", "--full", "--as", "maren").returncode == 0
    weaker = run_tool(repo, CHECK, "run", "--as", "tomas")
    assert weaker.returncode == 0 and "RECEIPT kept" in weaker.stdout, weaker.stdout
    assert receipt(repo)["area"] == "full" and receipt(repo)["by"] == "maren"
    assert run_tool(repo, CHECK, "verify", "--need-full").returncode == 0
    # the other order: the area receipt is replaced by the full one
    receipt_file(repo).unlink()
    assert run_tool(repo, CHECK, "run", "--as", "tomas").returncode == 0
    assert receipt(repo)["area"] == "backend+frontend"
    assert run_tool(repo, CHECK, "run", "--full", "--as", "maren").returncode == 0
    assert receipt(repo)["area"] == "full" and receipt(repo)["by"] == "maren"


def test_a_run_without_postgres_does_not_overwrite_a_pg_receipt_and_the_reverse_replaces(repo: Path) -> None:
    both_areas(repo)
    assert run_tool(repo, CHECK, "run", "--pg-url", "postgresql://u:p@localhost:1/db", "--as", "tomas").returncode == 0
    assert receipt(repo)["pg"] is True
    assert "RECEIPT kept" in run_tool(repo, CHECK, "run", "--as", "nils").stdout
    assert receipt(repo)["pg"] is True and receipt(repo)["by"] == "tomas"
    assert run_tool(repo, CHECK, "verify", "--need-pg").returncode == 0
    receipt_file(repo).unlink()
    assert run_tool(repo, CHECK, "run", "--as", "nils").returncode == 0 and receipt(repo)["pg"] is False
    assert run_tool(repo, CHECK, "run", "--pg-url", "postgresql://u:p@localhost:1/db", "--as", "tomas").returncode == 0
    assert receipt(repo)["pg"] is True and receipt(repo)["by"] == "tomas"


def test_neither_stronger_run_replaces_the_other_when_they_prove_different_things(repo: Path) -> None:
    both_areas(repo)
    assert run_tool(repo, CHECK, "run", "--full", "--as", "maren").returncode == 0     # full, no pg
    out = run_tool(repo, CHECK, "run", "--pg-url", "postgresql://u:p@localhost:1/db", "--as", "tomas")
    assert "RECEIPT kept" in out.stdout and receipt(repo)["by"] == "maren"
    assert run_tool(repo, CHECK, "verify", "--need-pg").returncode == 1   # the pg run cannot be claimed


def test_a_failing_run_never_replaces_a_passing_receipt(repo: Path, tmp_path: Path) -> None:
    both_areas(repo)
    assert run_tool(repo, CHECK, "run", "--as", "tomas").returncode == 0
    before = receipt_file(repo).read_text()
    (tmp_path / "bin" / "npx").write_text("#!/bin/sh\necho ' Tests  1 failed (1)'\nexit 1\n")
    failed = run_tool(repo, CHECK, "run", "--full", "--as", "maren")
    assert failed.returncode == 1 and "RESULT FAIL" in failed.stdout and "RECEIPT" not in failed.stdout
    assert receipt_file(repo).read_text() == before


@pytest.mark.parametrize("forged", [
    # an area run claiming "full" and Postgres: no base is recorded for a real --full, and no log
    # shows a database URL on the pytest command
    {"area": "full", "pg": True, "base": "main", "commands": ["pytest", "vitest run", "npm run build"]},
    # claims everything but ran only the frontend
    {"area": "full", "pg": True, "base": None, "commands": ["vitest run", "npm run build"]},
])
def test_a_hand_edited_receipt_is_not_kept_as_the_stronger_one(repo: Path, forged: dict) -> None:
    both_areas(repo)
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    receipt_file(repo).parent.mkdir(parents=True, exist_ok=True)
    receipt_file(repo).write_text(json.dumps({
        "tree": tree, "head": "x", "summary": "forged", "counts": {}, "by": "mallory", "cwd": "/",
        "ts": "2026-01-01T00:00:00+00:00", **forged}))
    out = run_tool(repo, CHECK, "run", "--as", "tomas")
    assert out.returncode == 0 and "RECEIPT kept" not in out.stdout, out.stdout
    rec = receipt(repo)
    assert rec["by"] == "tomas" and rec["area"] == "backend+frontend" and rec["pg"] is False


def test_a_receipt_for_another_tree_or_unreadable_is_replaced(repo: Path) -> None:
    both_areas(repo)
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    receipt_file(repo).parent.mkdir(parents=True, exist_ok=True)
    forged = {"tree": "0" * 40, "area": "full", "pg": False, "base": None, "by": "mallory",
              "commands": ["pytest", "vitest run", "npm run build"], "summary": "x", "ts": "x"}
    receipt_file(repo).write_text(json.dumps(forged))      # a full receipt copied from another tree
    assert run_tool(repo, CHECK, "run", "--as", "tomas").returncode == 0
    assert receipt(repo)["by"] == "tomas" and receipt(repo)["tree"] == tree
    receipt_file(repo).write_text("{not json")
    assert run_tool(repo, CHECK, "run", "--as", "nils").returncode == 0 and receipt(repo)["by"] == "nils"


def test_a_pg_claim_the_pytest_log_does_not_show_is_not_kept_as_stronger(repo: Path) -> None:
    both_areas(repo)
    assert run_tool(repo, CHECK, "run", "--as", "tomas").returncode == 0     # really ran without Postgres
    rec = receipt(repo)
    receipt_file(repo).write_text(json.dumps({**rec, "pg": True}))            # hand-edited to pg=yes
    out = run_tool(repo, CHECK, "run", "--as", "nils")
    assert out.returncode == 0 and "RECEIPT kept" not in out.stdout, out.stdout
    assert receipt(repo)["by"] == "nils" and receipt(repo)["pg"] is False
