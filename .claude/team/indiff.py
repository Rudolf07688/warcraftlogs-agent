#!/usr/bin/env python3
"""Is a finding in this sprint's diff or in older code? (sc-537, QA triage)

Agent-facing. Give `path:line` or `path:first-last`, as arguments or as any text on stdin (a QA
report pasted whole works: every path:line in it is checked). Each one is blamed in the working
tree and told apart:

  IN DIFF  the line was added or changed in BASE...HEAD (or is uncommitted)
  OLDER    the line predates BASE; shows the commit and date that last touched it

  indiff.py backend/app/x.py:42 wcl_agent/y.py:10-20 [--base REF]
  indiff.py < qa-reports/2026-11-07/bugs.md

Default base: on a sprint-* branch, the merge base with main (the whole sprint's diff); on any
other branch, the merge base with the newest sprint-* branch (your stream's diff), else main.
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone

FINDING = re.compile(r"(?<![\w./-])(/?(?:[\w.-]+/)*[\w.-]+\.\w+):(\d+)(?:-(\d+))?")
ZERO = "0" * 40


def git(*args, check=True, cwd=None):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    if check and r.returncode:
        sys.exit(f"indiff: git {' '.join(args)}: {r.stderr.strip()}")
    return r


def default_base():
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    sprints = git("for-each-ref", "--sort=-committerdate", "--format=%(refname:short)",
                  "refs/heads/sprint-*").stdout.split()
    other = "main" if branch.startswith("sprint-") or not sprints else sprints[0]
    base = git("merge-base", "HEAD", other).stdout.strip()
    return base, f"merge base with {other}"


def blame(path, first, last, top):
    """{line: (sha, unix time, summary)} for the working-tree file, or an error string.
    Findings are repo-relative, so blame runs from the repo root, not the caller's directory."""
    r = git("blame", "--porcelain", "-L", f"{first},{last}", "--", path, check=False, cwd=top)
    if r.returncode:
        return r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "blame failed"
    info, lines, sha, line = {}, {}, None, None
    for row in r.stdout.splitlines():
        m = re.match(r"([0-9a-f]{40}) \d+ (\d+)", row)
        if m:
            sha, line = m.group(1), int(m.group(2))
            info.setdefault(sha, {})
            lines[line] = sha
        elif row.startswith("author-time "):
            info[sha]["time"] = int(row.split()[1])
        elif row.startswith("summary "):
            info[sha]["summary"] = row[8:]
    return {n: (s, info[s].get("time", 0), info[s].get("summary", "")) for n, s in lines.items()}


def describe(sha, t, summary):
    if sha == ZERO:
        return "uncommitted"
    day = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
    return f"{sha[:9]} {day} {summary[:70]}"


def main():
    p = argparse.ArgumentParser(prog="indiff.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("findings", nargs="*", help="path:line or path:first-last (default: read stdin)")
    p.add_argument("--base", help="base ref (default: see above)")
    a = p.parse_args()
    top = git("rev-parse", "--show-toplevel").stdout.strip()
    text = " ".join(a.findings) if a.findings else sys.stdin.read()
    if a.base:
        base, how = git("rev-parse", "--verify", a.base + "^{commit}").stdout.strip(), a.base
    else:
        base, how = default_base()
    print(f"base {base[:9]} ({how})")
    ancestor = {}
    counts = {"IN DIFF": 0, "OLDER": 0, "?": 0}
    seen = set()
    for m in FINDING.finditer(text):
        path, first = m.group(1), int(m.group(2))
        last = max(first, int(m.group(3) or first))
        path = path[len(top) + 1:] if path.startswith(top + "/") else path.removeprefix("./")
        label = f"{path}:{first}" + (f"-{last}" if last != first else "")
        if label in seen:
            continue
        seen.add(label)
        got = blame(path, first, last, top)
        if isinstance(got, str):
            counts["?"] += 1
            print(f"{label}  ?        {got}")
            continue
        new = []
        for sha, t, summary in got.values():
            if sha not in ancestor:
                ancestor[sha] = sha != ZERO and git(
                    "merge-base", "--is-ancestor", sha, base, check=False).returncode == 0
            if not ancestor[sha]:
                new.append((sha, t, summary))
        if new:
            verdict, (sha, t, summary) = "IN DIFF", max(new, key=lambda x: (x[0] == ZERO, x[1]))
            share = f" ({len(new)}/{len(got)} lines)" if len(got) > 1 else ""
        else:
            verdict, (sha, t, summary) = "OLDER", max(got.values(), key=lambda x: x[1])
            share = ""
        counts[verdict] += 1
        print(f"{label}  {verdict:8} {describe(sha, t, summary)}{share}")
    if not seen:
        sys.exit("indiff: no path:line found in the input")
    print(f"indiff: {counts['IN DIFF']} in diff, {counts['OLDER']} older, {counts['?']} unresolved",
          file=sys.stderr)


if __name__ == "__main__":
    main()
