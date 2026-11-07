#!/usr/bin/env python3
"""Clean test runs with receipts: "green" is something the tool read, not something an agent said.

Agent-facing. Runs the tests in a cleared environment, reads the summary lines itself, keeps the
full log on disk and prints only what matters. With no paths it runs the suite for the AREA the
branch touched (its diff against --base, default the merge base with main):
  backend    backend/, wcl_agent/, .claude/team/*.py, pyproject/uv.lock -> pytest (full)
  frontend   frontend/                                         -> vitest + npm run build
  both       pytest, then vitest + build
  config     anything else (docs, YAML, JSON, agent files)    -> the targeted tests you name
A passing area run on a clean, committed tree leaves a receipt keyed by the git tree that records
the area and the commands run, so a frontend receipt never reads as a backend pass. `npm ci` runs
first when the frontend runs and frontend/node_modules is missing.

  check.py run [--base REF] [--pg NAME | --pg-url URL] --as YOU   the suite for the touched area
  check.py run PATHS... --as YOU        targeted tests: pytest paths and/or frontend/**/*.test.tsx
                                        (a receipt only on a config-only branch)
  check.py run --full --as YOU          pytest + vitest + build, whatever the diff (the PO, at the tip)
  check.py verify [--ref REF | --index] [--need-pg] [--need-full]   a passing receipt for this tree?
  check.py show [--ref REF | --index]                               print the receipt, if any

Exit codes: run = 0 pass / 1 fail (pytest's own code when it is not 0) / 3 refused; verify =
0 reuse / 1 run needed. Paste the RESULT line into your hand-off. Logs and receipts live in the
git common dir (team-checks/), so every worktree sees them.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

SUMMARY_RE = re.compile(r"\b(passed|failed|errors?|no tests ran)\b.*\bin [\d.]+s")
COUNT_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
VITEST_TESTS_RE = re.compile(r"^\s*Tests\s+(.*)$")
VITEST_SUITES_RE = re.compile(r"Failed Suites (\d+)")
VITEST_ERRORS_RE = re.compile(r"^\s*Errors\s+(\d+) errors?")
BACKEND_PREFIXES = ("backend/", "wcl_agent/", ".githooks/", "pyproject.toml", "uv.lock")
TSBUILDINFO = "frontend/tsconfig.tsbuildinfo"


def git(*args, cwd=None):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=cwd).stdout.strip()


def checks_dir(sub=""):
    path = os.path.join(git("rev-parse", "--path-format=absolute", "--git-common-dir"), "team-checks", sub)
    os.makedirs(path, exist_ok=True)
    return path


def toplevel():
    return git("rev-parse", "--show-toplevel")


def dirty(cwd=None):
    """Modified tracked files plus untracked, non-ignored files (new tests count)."""
    return [l for l in git("status", "--porcelain", "--untracked-files=normal", cwd=cwd).splitlines() if l]


def parse_summary(output):
    line = ""
    for raw in output.splitlines():
        s = raw.strip().strip("=").strip()
        if SUMMARY_RE.search(s):
            line = s
    counts = {}
    for n, kind in COUNT_RE.findall(line):
        counts["errors" if kind.startswith("error") else kind] = int(n)
    return line, counts


def verdict(rc, counts):
    ok = rc == 0 and counts.get("passed", 0) > 0 and not counts.get("failed") and not counts.get("errors")
    return "PASS" if ok else "FAIL"


def clean_env():
    return ["env", "-i", f"HOME={os.environ['HOME']}", f"PATH={os.environ['PATH']}"]


def pytest_cmd(paths, pg_url=None, quiet=True):
    env = clean_env()
    if pg_url:
        env.append(f"TEST_DATABASE_URL={pg_url}")
    return env + ["uv", "run", "--extra", "test", "pytest", "-q" if quiet else "-v",
                  "-p", "no:cacheprovider", *paths]


def vitest_cmd(paths):
    """vitest in frontend/; repo-relative paths become frontend-relative."""
    rel = [p[len("frontend/"):] if p.startswith("frontend/") else p for p in paths]
    return clean_env() + ["NO_COLOR=1", "npx", "vitest", "run", *rel]


def is_frontend_test(path):
    return path.startswith("frontend/") or path.endswith((".test.tsx", ".test.ts"))


def parse_vitest(output):
    """(summary_line, counts) from vitest's summary. counts["errors"] = suites that failed to
    load (a compile or import error) plus unhandled errors: never a behaviour failure."""
    text = ANSI_RE.sub("", output)
    line, counts = "", {}
    for raw in text.splitlines():
        m = VITEST_TESTS_RE.match(raw)
        if m:
            line = "Tests " + m.group(1).strip()
            counts = {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|skipped|todo)", m.group(1))}
        e = VITEST_ERRORS_RE.match(raw)
        if e:
            counts["errors"] = counts.get("errors", 0) + int(e.group(1))
    suites = sum(int(n) for n in VITEST_SUITES_RE.findall(text))
    if suites:
        counts["errors"] = counts.get("errors", 0) + suites
        line = (line + "; " if line else "") + f"{suites} suite(s) failed to load"
    return line, counts


def write_log(log_name, cmd, out, cwd=None):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log = os.path.join(checks_dir("logs"), f"{stamp}-{log_name}.log")
    with open(log, "w") as f:
        f.write(" ".join(cmd) + (f"   (in {cwd})" if cwd else "") + "\n\n" + out)
    return log


def run_pytest(paths, pg_url=None, cwd=None, log_name="run"):
    """Run pytest cleanly; return (rc, summary_line, counts, log_path, output)."""
    cmd = pytest_cmd(paths, pg_url)
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    out = proc.stdout + proc.stderr
    log = write_log(log_name, cmd, out)
    line, counts = parse_summary(out)
    return proc.returncode, line, counts, log, out


def ensure_node_modules(top, log_name="run"):
    """`npm ci` in a fresh worktree. Returns (ok, note); note is "" when nothing ran."""
    front = os.path.join(top, "frontend")
    if os.path.isdir(os.path.join(front, "node_modules")):
        return True, ""
    cmd = clean_env() + ["npm", "ci", "--no-audit", "--no-fund"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=front)
    log = write_log(f"{log_name}-npm-ci", cmd, proc.stdout + proc.stderr, front)
    return proc.returncode == 0, f"npm ci (no frontend/node_modules) -> rc {proc.returncode}, log: {log}"


def run_vitest(paths, top=None, log_name="run"):
    """Run vitest cleanly in frontend/; return (rc, summary_line, counts, log_path, output)."""
    top = top or toplevel()
    ok, note = ensure_node_modules(top, log_name)
    if note:
        print(note)
    if not ok:
        return 1, "npm ci failed", {"errors": 1}, note.rsplit("log: ", 1)[-1], ""
    front = os.path.join(top, "frontend")
    cmd = vitest_cmd(paths)
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=front)
    out = proc.stdout + proc.stderr
    log = write_log(log_name + "-vitest", cmd, out, front)
    line, counts = parse_vitest(out)
    return proc.returncode, line, counts, log, out


def run_tests(paths, pg_url=None, log_name="run"):
    """pytest or vitest by the paths (all of one kind); same return shape as run_pytest."""
    front = [is_frontend_test(p) for p in paths]
    if any(front) and not all(front):
        raise ValueError("mix of frontend and backend tests: run them separately")
    if paths and all(front):
        return run_vitest(paths, log_name=log_name)
    return run_pytest(paths, pg_url, log_name=log_name)


def run_build(top, log_name="run"):
    """`npm run build`; restores frontend/tsconfig.tsbuildinfo when the build rewrote a clean copy."""
    front = os.path.join(top, "frontend")
    was_clean = not git("status", "--porcelain", "--", TSBUILDINFO, cwd=top)
    cmd = clean_env() + ["npm", "run", "build"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=front)
    out = proc.stdout + proc.stderr
    log = write_log(log_name + "-build", cmd, out, front)
    if was_clean and git("ls-files", "--", TSBUILDINFO, cwd=top):
        git("checkout", "--", TSBUILDINFO, cwd=top)
    line = "build ok" if proc.returncode == 0 else f"build FAILED (rc {proc.returncode})"
    return proc.returncode, line, log, out


# ---------------------------------------------------------------- areas

def area_of(path):
    if path.startswith("frontend/"):
        return "frontend"
    if path.startswith(BACKEND_PREFIXES) or (path.startswith(".claude/team/") and path.endswith(".py")):
        return "backend"
    return "config"


def touched(base, top):
    """Files the branch changed against base: committed, uncommitted and untracked."""
    files = set(git("diff", "--name-only", f"{base}...HEAD", cwd=top).splitlines())
    files |= set(git("diff", "--name-only", "HEAD", cwd=top).splitlines())
    files |= set(git("ls-files", "--others", "--exclude-standard", cwd=top).splitlines())
    return sorted(f for f in files if f)


def changed_files(base, ref, tree):
    """Files a tree differs in from the merge base of `base` and its commit `ref`."""
    mb = git("merge-base", base, ref)
    return [f for f in git("diff", "--name-only", mb, tree).splitlines() if f]


def area_label(files):
    kinds = {area_of(f) for f in files}
    code = [k for k in ("backend", "frontend") if k in kinds]
    if code:
        return "+".join(code)
    return "config" if kinds else "none"


def default_base(top, ref="HEAD"):
    try:
        return git("merge-base", ref, "main", cwd=top)
    except subprocess.CalledProcessError:
        return None


class Refused(Exception):
    """A run the tool will not start: printed, exit 3."""


def resolve_base(base, top):
    """The commit SHA of a user-given --base; a value git could read as an option is refused."""
    try:
        if base.startswith("-"):
            raise ValueError
        return git("rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}", cwd=top)
    except (ValueError, subprocess.CalledProcessError):
        raise Refused(f"REFUSED: --base {base!r} is not a commit (a base may not start with '-')")


def covers(receipt_area, needed_area):
    """Did a receipt of this area run everything the branch's real diff needs?"""
    if receipt_area == "full":
        return True
    return {k for k in ("backend", "frontend") if k in needed_area} <= set(receipt_area.split("+"))


def shown_cmd(a):
    return ("check.py run" + (" --full" if a.full else "") + (f" --base {a.base}" if a.base else "")
            + (f" --pg {a.pg}" if a.pg else " --pg-url URL" if a.pg_url else "")
            + "".join(f" {p}" for p in a.paths))


def plan_steps(a, top):
    """(area, steps, base); a step is ("pytest"|"vitest", paths) or ("build", None)."""
    if a.full:
        return "full", [("pytest", []), ("vitest", []), ("build", None)], None
    base = resolve_base(a.base, top) if a.base else default_base(top)
    if not base:
        raise Refused("REFUSED: no --base given and no main branch to take the merge base from")
    area = area_label(touched(base, top))
    if a.paths:
        back = [p for p in a.paths if not is_frontend_test(p)]
        front = [p for p in a.paths if is_frontend_test(p)]
        return area, ([("pytest", back)] if back else []) + ([("vitest", front)] if front else []), base
    if area in ("config", "none"):
        raise Refused(f"REFUSED: the branch touches {area} files only (against {base[:12]}): name "
                      "the targeted tests that cover them, e.g. check.py run backend/tests/test_x.py")
    steps = [("pytest", [])] if "backend" in area else []
    if "frontend" in area:
        steps += [("vitest", []), ("build", None)]
    return area, steps, base


STEP_CMD = {"pytest": "pytest", "vitest": "vitest run", "build": "npm run build"}


def run_step(kind, paths, top, pg_url, log_name):
    """(rc, verdict, summary, counts, log, failure_lines) for one step."""
    if kind == "build":
        rc, line, log, out = run_build(top, log_name)
        return rc, "PASS" if rc == 0 else "FAIL", line, {}, log, [l for l in out.splitlines() if "error" in l.lower()]
    if kind == "vitest":
        rc, line, counts, log, out = run_vitest(paths, top, log_name)
        failed = [l.strip() for l in ANSI_RE.sub("", out).splitlines() if l.strip().startswith("FAIL ")]
    else:
        rc, line, counts, log, out = run_pytest(paths, pg_url, cwd=top, log_name=log_name)
        failed = [l for l in out.splitlines() if l.startswith(("FAILED ", "ERROR "))]
    return rc, verdict(rc, counts), line, counts, log, failed


def env_file_refusal(top):
    # Since 047 (sc-336) the test conftest sets WCL_LOAD_DOTENV=0, so a .env no longer leaks into
    # the suite and a run there is clean. Refuse only trees that predate that guard.
    try:
        guarded = "WCL_LOAD_DOTENV" in open(os.path.join(top, "backend", "tests", "conftest.py")).read()
    except OSError:
        guarded = False
    if not guarded and os.path.exists(os.path.join(top, ".env")):
        return ("REFUSED: this tree has a .env, and the app settings read it even under env -i "
                "(sc-336), so the run would not be clean and may call live APIs. Run from a "
                "worktree without .env, or pass --allow-env (no receipt is written then).")
    return None


def cmd_run(a):
    top = toplevel()
    refusal = env_file_refusal(top)
    if refusal and not a.allow_env:
        print(refusal)
        sys.exit(3)
    try:
        area, steps, base = plan_steps(a, top)
    except Refused as e:
        print(e)
        sys.exit(3)
    pg_url = a.pg_url
    if a.pg and any(k == "pytest" for k, _ in steps):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import pg
        pg_url = pg.ensure(a.pg)["test_url"]
    changed = dirty(top)
    head, tree = git("rev-parse", "HEAD", cwd=top), git("rev-parse", "HEAD^{tree}", cwd=top)
    results, rc_first = [], 0
    for kind, paths in steps:
        rc, v, line, counts, log, failed = run_step(kind, paths, top, pg_url, a.as_ or "run")
        results.append({"cmd": " ".join([STEP_CMD[kind], *(paths or [])]), "verdict": v,
                        "summary": line or "NO SUMMARY LINE (collection crash? read the log)",
                        "counts": counts, "log": log})
        print(f"  {kind}: {v} -> {results[-1]['summary']}")
        for l in failed[:15]:
            print("    " + l[:200])
        if len(failed) > 15:
            print(f"    ... {len(failed) - 15} more in the log")
        print(f"    log: {log}")
        if v != "PASS" and not rc_first:
            rc_first = rc or 1
    v = "PASS" if results and all(r["verdict"] == "PASS" for r in results) else "FAIL"
    print(f"RESULT {v}: `{shown_cmd(a)}` area={area} -> "
          + "; ".join(f"{r['cmd'].split()[0]}: {r['summary']}" for r in results))
    receipt_run = not a.paths or area == "config"
    if v == "PASS" and receipt_run:
        if changed:
            print(f"no receipt: {len(changed)} uncommitted/untracked file(s); commit, then re-run "
                  "for a receipt")
        elif refusal:
            print("no receipt: run used --allow-env")
        else:
            rec = {"tree": tree, "head": head, "area": area, "base": base,
                   "commands": [r["cmd"] for r in results],
                   "summary": "; ".join(r["summary"] for r in results),
                   "counts": {r["cmd"]: r["counts"] for r in results}, "pg": bool(pg_url),
                   "by": a.as_ or "", "cwd": top,
                   "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            with open(os.path.join(checks_dir("receipts"), f"{tree}.json"), "w") as f:
                json.dump(rec, f, indent=1)
            print(f"RECEIPT tree={tree[:12]} head={head[:12]} area={area} "
                  f"pg={'yes' if pg_url else 'no'} ran: {', '.join(rec['commands'])}")
    sys.exit(rc_first if v == "FAIL" else 0)


def target_tree(a):
    if a.index:
        return git("write-tree")  # the index, e.g. during `git merge --no-commit`
    return git("rev-parse", f"{a.ref}^{{tree}}")


def load_receipt(tree):
    try:
        return json.load(open(os.path.join(checks_dir("receipts"), f"{tree}.json")))
    except FileNotFoundError:
        return None


def cmd_verify(a):
    ref = "HEAD" if a.index else a.ref
    try:
        base = resolve_base(a.base, toplevel()) if a.base else None
    except Refused as e:
        print(e)
        sys.exit(1)
    tree = target_tree(a)
    rec = load_receipt(tree)
    if a.index and git("diff", "--name-only"):
        print("RUN NEEDED: the working tree differs from the index")
        sys.exit(1)
    if not rec:
        print(f"RUN NEEDED: no passing receipt for tree {tree[:12]} (the merged code differs from "
              "every tested tree, or nobody ran its suite on it)")
        sys.exit(1)
    if a.need_pg and not rec.get("pg"):
        print(f"RUN NEEDED: receipt for {tree[:12]} ran without Postgres (PG tests were skipped)")
        sys.exit(1)
    area = rec.get("area", "backend")   # receipts before 066 were full pytest runs
    base = base or default_base(toplevel(), ref)
    if not base:
        print("RUN NEEDED: no --base given and no main branch to check the receipt's area against")
        sys.exit(1)
    needed = area_label(changed_files(base, ref, tree))
    if not covers(area, needed):
        print(f"RUN NEEDED: the receipt for {tree[:12]} covers area={area} (base "
              f"{str(rec.get('base'))[:12]}), but the branch touches {needed} against {base[:12]}")
        sys.exit(1)
    if a.need_full and area != "full":
        print(f"RUN NEEDED: the receipt for {tree[:12]} covers area={area} only, not the full run")
        sys.exit(1)
    ran = ", ".join(rec.get("commands", ["pytest"]))
    print(f"REUSE: tree {tree[:12]} passed area={area} (ran: {ran}; {rec['summary']}), receipt base "
          f"{str(rec.get('base'))[:12]}, branch touches {needed}, by {rec['by'] or '?'} at {rec['ts']}, pg={'yes' if rec['pg'] else 'no'}")


def cmd_show(a):
    rec = load_receipt(target_tree(a))
    print(json.dumps(rec, indent=1) if rec else "no receipt for this tree")


def main():
    p = argparse.ArgumentParser(prog="check.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("run")
    q.add_argument("paths", nargs="*", help="test files or node ids; frontend/**/*.test.tsx run under "
                   "vitest (default: the suite for the touched area)")
    q.add_argument("--full", action="store_true", help="pytest + vitest + build, whatever the diff")
    q.add_argument("--base", help="the branch's base ref for the area (default: merge base with main)")
    q.add_argument("--pg", metavar="NAME", help="start/reuse throwaway Postgres NAME (pg.py) and run the PG tests too")
    q.add_argument("--pg-url", help="an existing TEST_DATABASE_URL")
    q.add_argument("--as", dest="as_", help="your board name, recorded on the receipt")
    q.add_argument("--allow-env", action="store_true", help="run even though the tree has a .env (no receipt)")
    for name in ("verify", "show"):
        q = s.add_parser(name)
        g = q.add_mutually_exclusive_group()
        g.add_argument("--ref", default="HEAD")
        g.add_argument("--index", action="store_true", help="check the index (a --no-commit trial merge)")
        if name == "verify":
            q.add_argument("--need-pg", action="store_true")
            q.add_argument("--need-full", action="store_true", help="only a --full receipt counts")
            q.add_argument("--base", help="the merge target the receipt's area is checked against "
                           "(default: merge base with main)")
    a = p.parse_args()
    if a.cmd == "run" and a.full and a.paths:
        p.error("--full runs everything; give no paths")
    {"run": cmd_run, "verify": cmd_verify, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
