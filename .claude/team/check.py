#!/usr/bin/env python3
"""Clean test runs with receipts: "green" is something the tool read, not something an agent said.

Agent-facing. Runs pytest in a cleared environment, reads the summary line itself, keeps the
full log on disk and prints only what matters. A passing FULL-suite run on a clean, committed
tree leaves a receipt keyed by the git tree, so a merger can see that exact code already passed.

  check.py run [PATHS...] [--pg NAME | --pg-url URL]   run the suite (or some files)
  check.py verify [--ref REF | --index] [--need-pg]    is there a passing receipt for this tree?
  check.py show [--ref REF | --index]                  print the receipt, if any

Exit codes: run = pytest's exit code (3 when refused); verify = 0 reuse / 1 run needed.
Paste the RESULT line (command + summary) into your hand-off. Logs and receipts live in the
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


def pytest_cmd(paths, pg_url=None, quiet=True):
    env = ["env", "-i", f"HOME={os.environ['HOME']}", f"PATH={os.environ['PATH']}"]
    if pg_url:
        env.append(f"TEST_DATABASE_URL={pg_url}")
    return env + ["uv", "run", "--extra", "test", "pytest", "-q" if quiet else "-v",
                  "-p", "no:cacheprovider", *paths]


def run_pytest(paths, pg_url=None, cwd=None, log_name="run"):
    """Run pytest cleanly; return (rc, summary_line, counts, log_path, output)."""
    cmd = pytest_cmd(paths, pg_url)
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    out = proc.stdout + proc.stderr
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log = os.path.join(checks_dir("logs"), f"{stamp}-{log_name}.log")
    with open(log, "w") as f:
        f.write(" ".join(cmd) + "\n\n" + out)
    line, counts = parse_summary(out)
    return proc.returncode, line, counts, log, out


def shown_cmd(paths, pg):
    return "check.py run" + (f" --pg {pg}" if pg else "") + "".join(f" {p}" for p in paths)


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
    pg_url = a.pg_url
    if a.pg:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import pg
        pg_url = pg.ensure(a.pg)["test_url"]
    changed = dirty()
    head, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
    rc, line, counts, log, out = run_pytest(a.paths, pg_url, log_name=(a.as_ or "run"))
    v = verdict(rc, counts)
    print(f"RESULT {v}: `{shown_cmd(a.paths, a.pg or ('url' if a.pg_url else ''))}` -> "
          f"{line or 'NO SUMMARY LINE (collection crash? read the log)'}")
    failed = [l for l in out.splitlines() if l.startswith(("FAILED ", "ERROR "))]
    for l in failed[:15]:
        print("  " + l[:200])
    if len(failed) > 15:
        print(f"  ... {len(failed) - 15} more in the log")
    print(f"log: {log}")
    if v == "PASS" and not a.paths:
        if changed:
            print(f"no receipt: {len(changed)} uncommitted/untracked file(s); commit, then re-run "
                  "for a receipt")
        elif refusal:
            print("no receipt: run used --allow-env")
        else:
            rec = {"tree": tree, "head": head, "summary": line, "counts": counts, "pg": bool(pg_url),
                   "by": a.as_ or "", "cwd": top,
                   "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            with open(os.path.join(checks_dir("receipts"), f"{tree}.json"), "w") as f:
                json.dump(rec, f, indent=1)
            print(f"RECEIPT tree={tree[:12]} head={head[:12]} pg={'yes' if pg_url else 'no'}")
    sys.exit(rc if rc else (0 if v == "PASS" else 1))


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
    tree = target_tree(a)
    rec = load_receipt(tree)
    if a.index and git("diff", "--name-only"):
        print("RUN NEEDED: the working tree differs from the index")
        sys.exit(1)
    if not rec:
        print(f"RUN NEEDED: no passing receipt for tree {tree[:12]} (the merged code differs from "
              "every tested tree, or nobody ran the full suite on it)")
        sys.exit(1)
    if a.need_pg and not rec.get("pg"):
        print(f"RUN NEEDED: receipt for {tree[:12]} ran without Postgres (PG tests were skipped)")
        sys.exit(1)
    print(f"REUSE: tree {tree[:12]} passed the full suite ({rec['summary']}), by {rec['by'] or '?'} "
          f"at {rec['ts']}, pg={'yes' if rec['pg'] else 'no'}")


def cmd_show(a):
    rec = load_receipt(target_tree(a))
    print(json.dumps(rec, indent=1) if rec else "no receipt for this tree")


def main():
    p = argparse.ArgumentParser(prog="check.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("run")
    q.add_argument("paths", nargs="*", help="test files or node ids (default: the full suite)")
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
    a = p.parse_args()
    {"run": cmd_run, "verify": cmd_verify, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
