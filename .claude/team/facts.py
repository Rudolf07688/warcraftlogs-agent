#!/usr/bin/env python3
"""Team facts: short lessons anchored to the codebase that surface by footprint.

Agent-facing. A fact is one file, .claude/team/facts/<id>.md: front matter (id, anchors, by,
source, verified) and a body of at most 80 words. Each anchor ties it to something concrete:
  file:<path>   a file, or a directory when it ends with /
  sym:<path>::<name>   a function or class, Class.method for a method (.py/.ts/.tsx/.js/.jsx)
  comp:<name>   a runtime component; COMPONENTS below maps it to path prefixes
Facts are committed with the code, so a fact added on a branch reaches the team when it merges.

  facts.py for TARGET... [--depth 0|1] [--all]   facts for paths, path::symbol or comp:name
  facts.py diff [--staged | --base REF] [--hook]  facts for the files and symbols a diff touches
  facts.py brief TARGET...                        the same as `for`, as a markdown brief section
  facts.py add --id ID --anchor A [--anchor A...] --by "<seat> <Name>" [--source S] TEXT|-
  facts.py stale [--to REF]                       facts whose anchor moved since `verified`
  facts.py verify ID... [--ref REF]               re-stamp after re-checking a fact
  facts.py retire ID --why TEXT                   delete a fact that is no longer true
  facts.py lint                                   front matter, anchors, word cap, duplicates
  facts.py stats [--since REF] [--json]           counts for the sprint team report

Ranking (for, diff, brief): 1 direct anchor (or a symbol inside a target file), 2 a file anchor
on the target's file or a parent directory, 3 a component covering the target, 4 a graph
neighbour: a caller or callee of the target symbols (or of the symbols in a target file).
Staleness: file and comp anchors go stale on any change under them since the verified commit; a
sym anchor only when a change overlaps the symbol's lines. Symbol line ranges are parsed from
the exact revision (Python ast; a regex for top-level TS/JS function/const/class/type).
GitNexus: always the MAIN checkout's index, `--repo <main checkout path>`. From a worktree,
`--repo .` fails ("Repository "." not found") and .gitnexus/ is absent; paths are repo-relative
in both, so no mapping is needed. An unhealthy index (empty node names) prints one warning and
falls back to file and component matches; --no-graph, no node, or no index does so silently.
Exit codes: for/brief/diff/retire 0 ok, 2 bad input; add 0 written / 1 refused (near-duplicate)
/ 2 invalid; verify 0 stamped / 1 refused (anchor gone) / 2 unknown id; stale 0 nothing stale /
1 stale or anchor gone; lint 0 clean / 1 problems. `diff --hook` (.githooks/pre-commit) always
exits 0 and prints nothing when nothing matches or anything goes wrong.
"""
import argparse
import ast
import datetime
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time

WORD_CAP = 80
DUP_OVERLAP = 0.6
DEFAULT_MAX = 12
HOOK_MAX = 10          # hook output: 1 header + 10 facts + 1 "more" line
HOOK_BUDGET = 5.0      # seconds for a whole hook run; graph neighbours are skipped past it
GRAPH_TIMEOUT = 6.0    # seconds per GitNexus call outside the hook
EDGE_LIMIT = 5000      # call edges per query
FACTS_REL = ".claude/team/facts"

# Component -> path prefixes (plain prefix match: "docker-compose" covers docker-compose*.yml).
# A path may belong to several components. Keep it in step with the repo.
COMPONENTS = {
    "alloy": ["observability/alloy/"],
    "mimir": ["observability/mimir/"],
    "loki": ["observability/loki/"],
    "tempo": ["observability/tempo/"],
    "grafana": ["observability/grafana/"],
    "pyroscope": ["backend/app/telemetry/setup.py", "backend/tests/test_telemetry_profiles.py"],
    "telemetry": ["backend/app/telemetry/", "frontend/src/telemetry/", "bin/claude-otel",
                  "observability/build-runtime/", "observability/pricing/"],
    "postgres": ["backend/migrations/", "backend/alembic.ini", "backend/app/db/",
                 "backend/app/repositories/", "observability/postgres/",
                 "observability/grafana/dashboards/infra/postgres.json", ".claude/team/pg.py"],
    "redis": ["wcl_agent/cache/", "backend/app/api/cache_stats.py",
              "observability/grafana/dashboards/infra/redis.json"],
    "compose": ["docker-compose", "backend/Dockerfile", "frontend/Dockerfile", "frontend/nginx.conf",
                ".dockerignore", ".env.example"],
    "gitnexus": [".gitnexus/", ".gitnexusignore"],
    "team": [".claude/team/", ".githooks/"],
}
FIELDS = ("id", "anchors", "by", "source", "verified")
REQUIRED = ("id", "anchors", "by", "verified")
ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_AUTHOR = r"(?:lead|po|sm|owner|dev-[0-9]+)(?:\s+[A-Z][A-Za-z-]*)?"
BY_RE = re.compile(rf"{_AUTHOR}(?:\s*,\s*{_AUTHOR})*")  # one author, or several: "dev-1 Ansel, dev-3 Nils"
VERIFIED_RE = re.compile(r"([0-9a-f]{7,40})\s+(\d{4}-\d{2}-\d{2})")
PARSEABLE = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
RANKS = {1: "direct", 2: "file", 3: "component", 4: "neighbour"}
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
# same word-overlap measure as member.py lint
STOP = set("""this that with from have when then they them your their into only also must
never every after before about which while where what there here will would should could
does done than more most some such each just like make sure same other first""".split())

ROOT = MAIN = FACTS = ""
WARNINGS = []


class Bad(Exception):
    """Bad input: printed, exit 2."""


class GraphError(Exception):
    pass


def init_paths():
    global ROOT, MAIN, FACTS
    ROOT = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                          check=True).stdout.strip()
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    MAIN = os.path.dirname(common)
    FACTS = os.path.join(ROOT, FACTS_REL)


def git(*args, check=True):
    r = subprocess.run(["git", "-c", "core.quotePath=false", *args], capture_output=True,
                       text=True, cwd=ROOT)
    if check and r.returncode:
        raise Bad(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout if r.returncode == 0 else None


_memo = {}


def memo(key, fn):
    if key not in _memo:
        _memo[key] = fn()
    return _memo[key]


def short(ref):
    out = git("rev-parse", "--short", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    if not out:
        raise Bad(f"{ref} is not a commit")
    return out.strip()


def is_commit(sha):
    return memo(("commit", sha), lambda: git("cat-file", "-e", f"{sha}^{{commit}}", check=False) is not None)


def show(ref, path):
    """File content at ref ("" = the index, None = the working tree), or None."""
    def load():
        if ref is None:
            try:
                return open(os.path.join(ROOT, path), encoding="utf-8", errors="replace").read()
            except OSError:
                return None
        return git("show", f"{ref}:{path}", check=False)
    return memo(("show", ref, path), load)


def tree_files(ref):
    return memo(("tree", ref), lambda: set((git("ls-tree", "-r", "--name-only", ref) or "").splitlines()))


def changed_files(sha, to):
    return memo(("changed", sha, to),
                lambda: (git("diff", "--name-only", "--no-renames", sha, to) or "").splitlines())


# ---------------------------------------------------------------- facts and anchors

class Anchor:
    def __init__(self, raw):
        self.raw = raw.strip()
        kind, _, rest = self.raw.partition(":")
        self.kind, self.path, self.name = kind, "", ""
        if kind == "file":
            self.path = rest[2:] if rest.startswith("./") else rest
        elif kind == "sym":
            self.path, _, self.name = rest.partition("::")
            self.path = self.path[2:] if self.path.startswith("./") else self.path
        elif kind == "comp":
            self.name = rest

    def syntax_error(self):
        if self.kind == "file":
            return None if self.path and not self.path.startswith("/") else "file: needs a repo path"
        if self.kind == "sym":
            if not self.path or not self.name:
                return "sym: needs <path>::<name>"
            if not self.path.endswith(PARSEABLE):
                return f"sym: works in {'/'.join(PARSEABLE[:5])} files only; anchor the file instead"
            return None
        if self.kind == "comp":
            return None if self.name in COMPONENTS else \
                f"unknown component {self.name!r} (known: {', '.join(sorted(COMPONENTS))})"
        return "anchor kind must be file:, sym: or comp:"

    def __str__(self):
        return self.raw


class Fact:
    def __init__(self, path):
        self.path = path
        self.fid = os.path.basename(path)[:-3]
        self.fields, self.body, self.errors = {}, "", []
        try:
            text = open(path, encoding="utf-8").read()
        except OSError as e:
            self.errors.append(f"unreadable: {e}")
            return
        if not text.startswith("---\n"):
            self.errors.append("no front matter (the file must start with ---)")
            return
        head, sep, body = text[4:].partition("\n---\n")
        if not sep:
            head, sep, body = text[4:].partition("\n---")
            if not sep or body.strip():
                self.errors.append("front matter is not closed with ---")
                return
        self.body = body.strip()
        key = None
        for line in head.splitlines():
            if not line.strip():
                continue
            m = re.match(r"\s+-\s+(.*)$", line)
            if m and key == "anchors":
                self.fields.setdefault("anchors", []).append(m.group(1).strip().strip("'\""))
                continue
            m = re.match(r"([a-z_]+):\s*(.*)$", line)
            if not m:
                self.errors.append(f"front matter line not understood: {line!r}")
                continue
            key, val = m.group(1), m.group(2).strip()
            if key == "anchors":
                if val.startswith("[") and val.endswith("]"):
                    self.fields["anchors"] = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                elif val:
                    self.fields["anchors"] = [val]
                else:
                    self.fields["anchors"] = []
            else:
                self.fields[key] = val

    @property
    def id(self):
        return self.fields.get("id") or self.fid

    @property
    def anchors(self):
        return [Anchor(a) for a in self.fields.get("anchors", [])]

    @property
    def verified(self):
        m = VERIFIED_RE.fullmatch(self.fields.get("verified", ""))
        return (m.group(1), m.group(2)) if m else (None, None)


def load_facts():
    if not os.path.isdir(FACTS):
        return []
    return [Fact(os.path.join(FACTS, f)) for f in sorted(os.listdir(FACTS))
            if f.endswith(".md") and f != "README.md"]


def words(text):
    return len(re.findall(r"\S+", text))


def content_words(text):
    return {w for w in re.findall(r"[a-z0-9_./-]{4,}", text.lower()) if w not in STOP}


def overlap(a, b):
    a, b = content_words(a), content_words(b)
    shared = len(a & b)
    if shared < 3:
        return 0.0
    return shared / min(len(a), len(b))


# ---------------------------------------------------------------- symbols (parsed, per revision)

TS_DEF = re.compile(
    r"(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
    r"(?:function\s*\*?\s*(\w+)|(?:abstract\s+)?class\s+(\w+)|(?:const|let|var)\s+(\w+)"
    r"|interface\s+(\w+)|type\s+(\w+)|enum\s+(\w+))")


def py_symbols(text):
    out = {}
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return out

    def walk(body, prefix):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([d.lineno for d in n.decorator_list] + [n.lineno])
                out.setdefault(prefix + n.name, (start, n.end_lineno))
                if isinstance(n, ast.ClassDef):
                    walk(n.body, prefix + n.name + ".")
            elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                # module and class constants/state (METRIC_ATTRIBUTES, _clock, _tombstones)
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    for e in (t.elts if isinstance(t, ast.Tuple) else [t]):
                        if isinstance(e, ast.Name):
                            out.setdefault(prefix + e.id, (n.lineno, n.end_lineno))
    walk(tree.body, "")
    return out


def _ts_end(lines, i, limit):
    depth, opened, tick = 0, False, False
    for j in range(i, limit + 1):
        line, quote, k = lines[j], None, 0
        while k < len(line):
            ch = line[k]
            if tick or quote:
                if ch == "\\":
                    k += 2
                    continue
                if tick and ch == "`":
                    tick = False
                elif quote and ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch          # ' and " strings end with the line, so a JSX apostrophe stays local
            elif ch == "`":
                tick = True
            elif ch == "/" and line[k + 1:k + 2] == "/":
                break
            elif ch in "({[":
                depth, opened = depth + 1, True
            elif ch in ")}]":
                depth -= 1
            k += 1
        if depth <= 0 and not tick and (opened or line.rstrip().endswith(";")):
            return j
    return limit


def ts_symbols(text):
    lines = text.splitlines()
    starts = [(i, next(g for g in m.groups() if g)) for i, line in enumerate(lines)
              if (m := TS_DEF.match(line))]
    out = {}
    for k, (i, name) in enumerate(starts):
        limit = starts[k + 1][0] - 1 if k + 1 < len(starts) else len(lines) - 1
        out.setdefault(name, (i + 1, _ts_end(lines, i, max(i, limit)) + 1))
    return out


def symbols(ref, path):
    """{name: (start, end)} for path at ref (see show()); {} when absent or not parseable."""
    def load():
        text = show(ref, path)
        if text is None or not path.endswith(PARSEABLE):
            return {}
        return py_symbols(text) if path.endswith(".py") else ts_symbols(text)
    return memo(("syms", ref, path), load)


def related(a, b):
    """Same symbol, or one contains the other (Class vs Class.method)."""
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


# ---------------------------------------------------------------- GitNexus

def gitnexus_cmd():
    env = os.environ.get("FACTS_GITNEXUS")
    if env is not None:                      # tests and overrides: a command prefix, "" = off
        return shlex.split(env) or None
    if not os.path.isdir(os.path.join(MAIN, ".gitnexus")):
        return None
    node, runner = shutil.which("node"), os.path.join(MAIN, ".gitnexus", "run.cjs")
    if node and os.path.exists(runner):
        return [node, runner]
    gn = shutil.which("gitnexus")
    return [gn] if gn else None


def parse_table(out):
    start = out.find("{")
    if start < 0:
        raise GraphError("no JSON in the cypher output")
    data = json.loads(out[start:])
    if "markdown" not in data:
        raise GraphError(str(data.get("error") or data)[:120])
    rows = []
    for line in data["markdown"].splitlines()[2:]:
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip()[1:-1].split("|")])
    return rows


def cypher_many(cmd, queries, timeout):
    """Run the queries in parallel; rows per query. Cached within one run.
    Output goes to temp files, not pipes: the gitnexus CLI exits before a pipe drains, so piped
    output is cut at 64 KiB (seen with 1.6.12 on a 131-file diff)."""
    procs = {}
    for q in queries:
        if ("cypher", q) not in _memo and q not in procs:
            out, err = tempfile.TemporaryFile("w+"), tempfile.TemporaryFile("w+")
            procs[q] = (subprocess.Popen(cmd + ["cypher", q, "--repo", MAIN], stdout=out, stderr=err,
                                         stdin=subprocess.DEVNULL, text=True, cwd=MAIN), out, err)
    deadline = time.monotonic() + timeout
    try:
        for q, (p, out, err) in procs.items():
            try:
                p.wait(timeout=max(0.05, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise GraphError(f"no answer within {timeout:.1f}s")
            out.seek(0)
            err.seek(0)
            if p.returncode:
                lines = [ln for ln in err.read().splitlines() if ln.strip() and not ln.strip().startswith("at ")]
                raise GraphError((lines[-1] if lines else f"exit {p.returncode}").strip()[:160])
            _memo[("cypher", q)] = parse_table(out.read())
    finally:
        for p, out, err in procs.values():
            if p.poll() is None:
                p.kill()
                p.wait()
            out.close()
            err.close()
    return [_memo[("cypher", q)] for q in queries]


HEALTH_Q = "MATCH (n:Function) RETURN n.name, n.filePath LIMIT 5"


def quote(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def neighbours(targets, timeout):
    """{(path, name): why} for callers and callees of the target symbols, or of all symbols in
    an inner file target. {} (with a warning when it matters) when the graph cannot answer."""
    cmd = gitnexus_cmd()
    whole = {t["path"] for t in targets if t["kind"] == "file" and t["inner"]}
    syms = {}
    for t in targets:
        if t["kind"] == "sym":
            syms.setdefault(t["path"], set()).add(t["name"].split(".")[-1])
    files = sorted(whole | set(syms))
    if not cmd or not files:
        return {}
    if timeout < 1.0:
        WARNINGS.append("graph neighbours skipped (out of time)")
        return {}
    lst = "[" + ", ".join(quote(f) for f in files) + "]"
    edges_q = (f"MATCH (a)-[r:CodeRelation {{type:'CALLS'}}]->(b) WHERE a.filePath IN {lst} "
               f"OR b.filePath IN {lst} RETURN DISTINCT a.name, a.filePath, b.name, b.filePath LIMIT {EDGE_LIMIT}")
    try:
        health, edges = cypher_many(cmd, [HEALTH_Q, edges_q], timeout)
    except (GraphError, OSError, ValueError) as e:
        WARNINGS.append(f"GitNexus unavailable ({e}); file and component matches only")
        return {}
    if not health or all(not r[0] for r in health) or all(not r[-1] for r in health):
        WARNINGS.append("GitNexus index unhealthy: run `node .gitnexus/run.cjs analyze --index-only "
                        "--force` (in the main checkout); file and component matches only")
        return {}
    if len(edges) >= EDGE_LIMIT:
        WARNINGS.append(f"graph neighbours partial (over {EDGE_LIMIT} call edges); narrow the targets")

    def inside(path, name):
        return path in whole or name in syms.get(path, ())

    out = {}
    for row in edges:
        if len(row) != 4:
            continue
        an, ap, bn, bp = row
        if not (ap and bp and an and bn):
            continue
        if inside(ap, an) and not inside(bp, bn):
            out.setdefault((bp, bn), f"called by {ap}::{an}")
        if inside(bp, bn) and not inside(ap, an):
            out.setdefault((ap, an), f"calls {bp}::{bn}")
    return out


# ---------------------------------------------------------------- matching

def comp_covers(prefix, path):
    return path.startswith(prefix)


def match(t, a):
    """(rank, why) when anchor a applies to target t, else None."""
    if t["kind"] == "comp":
        paths = COMPONENTS[t["name"]]
        if a.kind == "comp" and a.name == t["name"]:
            return 1, f"comp:{a.name}"
        if a.kind in ("file", "sym") and any(comp_covers(p, a.path) for p in paths):
            return 2, f"{a} is part of comp:{t['name']}"
        if a.kind == "comp" and any(p.startswith(q) or q.startswith(p)
                                    for p in COMPONENTS.get(a.name, []) for q in paths):
            return 3, f"comp:{a.name} shares paths with comp:{t['name']}"
        return None
    P, kind = t["path"], t["kind"]
    if a.kind == "file":
        if a.path.rstrip("/") == P.rstrip("/"):
            return (2, f"{a} holds {P}::{t['name']}") if kind == "sym" else (1, str(a))
        if kind == "dir" and t["inner"] and a.path.startswith(P):
            return 1, f"{a} is inside {P}"
        if a.path.endswith("/") and P.startswith(a.path):
            return 2, f"{a} contains {P}"
    elif a.kind == "sym":
        if kind == "sym" and a.path == P and related(a.name, t["name"]):
            return 1, str(a)
        if kind == "file" and t["inner"] and a.path == P:
            return 1, f"{a} is in {P}"
        if kind == "dir" and t["inner"] and a.path.startswith(P):
            return 1, f"{a} is inside {P}"
    elif a.kind == "comp":
        paths = COMPONENTS.get(a.name, [])
        if kind == "dir":
            if any(p.startswith(P) or P.startswith(p) for p in paths):
                return 3, f"comp:{a.name} overlaps {P}"
        elif any(comp_covers(p, P) for p in paths):
            return 3, f"comp:{a.name} covers {P}"
    return None


def rank_facts(facts, targets, nbrs):
    best = {}
    for f in facts:
        for a in f.anchors:
            hits = [m for t in targets if (m := match(t, a))]
            if a.kind == "sym":
                key = next((k for k in ((a.path, a.name), (a.path, a.name.split(".")[-1])) if k in nbrs), None)
                if key:
                    hits.append((4, f"{a} {nbrs[key]}"))
            elif a.kind == "file" and not a.path.endswith("/"):
                why = next((f"{a} {w}" for (p, n), w in nbrs.items() if p == a.path), None)
                if why:
                    hits.append((4, why))
            for h in hits:
                if f.id not in best or h[0] < best[f.id][1]:
                    best[f.id] = (f, h[0], h[1])
    return sorted(best.values(), key=lambda x: (x[1], x[0].id))


def target_of(raw):
    if raw.startswith("comp:"):
        if raw[5:] not in COMPONENTS:
            raise Bad(f"unknown component {raw[5:]!r} (known: {', '.join(sorted(COMPONENTS))})")
        return {"kind": "comp", "name": raw[5:], "path": "", "inner": True}
    if raw.startswith("sym:"):
        raw = raw[4:]
    elif raw.startswith("file:"):
        raw = raw[5:]
    path, _, name = raw.partition("::")
    rel = None
    for base in (os.getcwd(), ROOT, MAIN):
        cand = os.path.abspath(os.path.join(base, path))
        for root in (ROOT, MAIN):
            if (cand == root or cand.startswith(root + os.sep)) and os.path.exists(cand):
                rel = os.path.relpath(cand, root)
                break
        if rel is not None:
            break
    if rel is None:
        rel = path[2:] if path.startswith("./") else path   # e.g. a deleted file
    rel = "" if rel == "." else rel.replace(os.sep, "/")
    if name:
        return {"kind": "sym", "path": rel, "name": name, "inner": True}
    if rel == "" or os.path.isdir(os.path.join(ROOT, rel)):
        return {"kind": "dir", "path": rel.rstrip("/") + "/" if rel else "", "name": "", "inner": True}
    return {"kind": "file", "path": rel, "name": "", "inner": True}


def label(t):
    if t["kind"] == "comp":
        return f"comp:{t['name']}"
    return f"{t['path']}::{t['name']}" if t["kind"] == "sym" else t["path"]


# ---------------------------------------------------------------- staleness

def overlaps(ranges, span):
    return span and any(n and s <= span[1] and s + n - 1 >= span[0] for s, n in ranges)


def file_hunks(diff_text):
    """{path: {"old": [(start, count)], "new": [...]}} from `git diff -U0` output."""
    out, cur, old_path = {}, None, None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            cur, old_path = None, None
        elif line.startswith("--- "):
            old_path = None if line[4:] == "/dev/null" else line[4:].split("\t")[0][2:]
        elif line.startswith("+++ "):
            new = None if line[4:] == "/dev/null" else line[4:].split("\t")[0][2:]
            cur = out.setdefault(new or old_path, {"old": [], "new": [], "deleted": new is None,
                                                    "added": old_path is None})
        elif cur is not None and (m := HUNK.match(line)):
            cur["old"].append((int(m.group(1)), int(m.group(2) or 1)))
            cur["new"].append((int(m.group(3)), int(m.group(4) or 1)))
        elif line.startswith("Binary files "):
            m = re.match(r"Binary files (?:a/(.*)|/dev/null) and (?:b/(.*)|/dev/null) differ", line)
            if m:
                out.setdefault(m.group(2) or m.group(1), {"old": [], "new": [], "deleted": False, "added": False})
    return out


def anchor_state(a, sha, to):
    """("ok"|"stale"|"gone", detail) for one anchor between sha and to."""
    if a.kind == "comp":
        if a.name not in COMPONENTS:
            return "gone", f"no component {a.name!r} in COMPONENTS"
        # Fact files are data, not the component's code: editing a fact must not stale every
        # comp:team fact (2026-11-05b retro, Tomas).
        moved = [p for p in changed_files(sha, to) if not p.startswith(".claude/team/facts/")
                 and any(comp_covers(q, p) for q in COMPONENTS[a.name])]
    else:
        files = tree_files(to)
        if a.kind == "file" and a.path.endswith("/"):
            if not any(p.startswith(a.path) for p in files):
                return "gone", f"no directory {a.path} at {to}"
            moved = [p for p in changed_files(sha, to) if p.startswith(a.path)]
        else:
            if a.path not in files:
                return "gone", f"no file {a.path} at {to}"
            if a.kind == "file":
                moved = [p for p in changed_files(sha, to) if p == a.path]
            else:
                new = symbols(to, a.path).get(a.name)
                if not new:
                    return "gone", f"no symbol {a.name} in {a.path} at {to}"
                if a.path not in changed_files(sha, to):
                    return "ok", ""
                h = file_hunks(git("diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
                                   sha, to, "--", a.path) or "").get(a.path, {"old": [], "new": []})
                old = symbols(sha, a.path).get(a.name)
                if overlaps(h["new"], new) or overlaps(h["old"], old) or not old:
                    return "stale", f"lines {new[0]}-{new[1]} of {a.path} changed"
                return "ok", ""
    if moved:
        more = f" (+{len(moved) - 3} more)" if len(moved) > 3 else ""
        return "stale", ", ".join(sorted(moved)[:3]) + more
    return "ok", ""


def fact_state(f, to):
    """{"stale": [(anchor, detail)], "gone": [...]}"""
    sha, _ = f.verified
    res = {"stale": [], "gone": []}
    if not sha or not is_commit(sha):
        res["stale"].append(("verified", f"commit {sha or '?'} is not known here"))
        return res
    for a in f.anchors:
        if a.syntax_error():
            res["gone"].append((a, a.syntax_error()))
            continue
        state, detail = anchor_state(a, sha, to)
        if state != "ok":
            res[state].append((a, detail))
    return res


# ---------------------------------------------------------------- output

def collect(targets, depth, deadline):
    facts = [f for f in load_facts() if not f.errors]
    nbrs = {}
    if depth >= 1 and facts:
        left = deadline - time.monotonic() - 0.4 if deadline else GRAPH_TIMEOUT
        nbrs = neighbours(targets, min(GRAPH_TIMEOUT, left))
    return rank_facts(facts, targets, nbrs)


def is_stale(f):
    try:
        s = fact_state(f, "HEAD")
        return bool(s["stale"] or s["gone"])
    except Bad:
        return False


def print_blocks(ranked, cap, title):
    shown = ranked if cap is None else ranked[:cap]
    for w in WARNINGS:
        print(f"warning: {w}")
    if not ranked:
        print(f"No team facts for {title}.")
        return
    print(f"Team facts for {title} ({len(ranked)}):")
    for f, rank, why in shown:
        sha, day = f.verified
        stale = "  STALE: re-check it, then facts.py verify " + f.id if is_stale(f) else ""
        print(f"\n- {f.id}  [{RANKS[rank]}: {why}]{stale}")
        for line in textwrap.wrap(" ".join(f.body.split()), 96):
            print("    " + line)
        print(f"    ({f.fields.get('by', '?')}, verified {sha} {day})")
    if len(ranked) > len(shown):
        print(f"\n{len(ranked) - len(shown)} more fact(s) left out; --all shows them.")


def cmd_for(a):
    targets = [target_of(t) for t in a.targets]
    ranked = collect(targets, 0 if a.no_graph else a.depth, None)
    print_blocks(ranked, None if a.all else a.max, ", ".join(label(t) for t in targets))
    return 0


def cmd_brief(a):
    targets = [target_of(t) for t in a.targets]
    ranked = collect(targets, 0 if a.no_graph else a.depth, None)
    cap = None if a.all else a.max
    print("## Known facts for this footprint\n")
    print(f"Team facts for {', '.join(f'`{label(t)}`' for t in targets)} "
          "(`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE "
          "before relying on it; record a new lesson with `facts.py add`.\n")
    for w in WARNINGS:
        print(f"> {w}\n")
    if not ranked:
        print("None recorded yet.")
        return 0
    for f, rank, why in ranked[:cap] if cap else ranked:
        sha, day = f.verified
        stale = " **STALE**" if is_stale(f) else ""
        print(f"- **{f.id}**{stale} ({RANKS[rank]}: {why}; verified {sha} {day}): {' '.join(f.body.split())}")
    if cap and len(ranked) > cap:
        print(f"\n({len(ranked) - cap} more: `facts.py brief --all ...`)")
    return 0


def diff_targets(a):
    if a.staged:
        args, old_ref, new_ref = ["--cached"], "HEAD", ""
    elif a.base:
        mb = git("merge-base", a.base, "HEAD", check=False)
        base = mb.strip() if mb else short(a.base)
        args, old_ref, new_ref = [base], base, None
    else:
        args, old_ref, new_ref = ["HEAD"], "HEAD", None
    text = git("diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames", *args) or ""
    targets, nsyms = [], 0
    for path, h in sorted(file_hunks(text).items()):
        if path.startswith(FACTS_REL + "/"):
            continue
        hit = set()
        if not h["deleted"]:
            hit |= {n for n, span in symbols(new_ref, path).items() if overlaps(h["new"], span)}
        if not h["added"]:
            hit |= {n for n, span in symbols(old_ref, path).items() if overlaps(h["old"], span)}
        # a method hit implies its class span overlaps too: keep the most specific names only
        hit = {n for n in hit if not any(m.startswith(n + ".") for m in hit)}
        for n in sorted(hit):
            targets.append({"kind": "sym", "path": path, "name": n, "inner": True})
        nsyms += len(hit)
        if not hit:
            targets.append({"kind": "file", "path": path, "name": "", "inner": False})
    return targets, len({t["path"] for t in targets}), nsyms


def cmd_diff(a):
    start = time.monotonic()
    targets, nfiles, nsyms = diff_targets(a)
    if not targets:
        if not a.hook:
            print("No changed files.")
        return 0
    deadline = start + HOOK_BUDGET if a.hook else None
    ranked = collect(targets, 0 if a.no_graph else a.depth, deadline)
    what = "--staged" if a.staged else f"--base {a.base}" if a.base else ""
    if not a.hook:
        print_blocks(ranked, None if a.all else a.max, f"the diff {what or 'against HEAD'} "
                     f"({nfiles} file(s), {nsyms} symbol(s))")
        return 0
    if not ranked:
        return 0
    print(f"team facts for this commit ({len(ranked)}; full text: python3 .claude/team/facts.py diff {what}):")
    for w in WARNINGS[:1]:
        print(f"  warning: {w}"[:160])
    room = HOOK_MAX - min(1, len(WARNINGS))
    for f, rank, why in ranked[:room]:
        line = f"  {f.id} [{RANKS[rank]}]: {' '.join(f.body.split())}"
        print(line if len(line) <= 150 else line[:147] + "...")
    if len(ranked) > room:
        print(f"  +{len(ranked) - room} more")
    return 0


def resolve_error(a, ref=None):
    """Why anchor a does not resolve in the working tree (ref None) or at ref; None if it does."""
    err = a.syntax_error()
    if err or a.kind == "comp":
        return err
    if ref is None:
        full = os.path.join(ROOT, a.path)
        if a.path.endswith("/"):
            return None if os.path.isdir(full) else f"no directory {a.path}"
        if not os.path.isfile(full):
            return f"no file {a.path}"
    else:
        files = tree_files(ref)
        if a.path.endswith("/"):
            return None if any(p.startswith(a.path) for p in files) else f"no directory {a.path} at {ref}"
        if a.path not in files:
            return f"no file {a.path} at {ref}"
    if a.kind == "sym" and a.name not in symbols(ref, a.path):
        return f"no symbol {a.name} in {a.path}" + (f" at {ref}" if ref else "")
    return None


def write_fact(path, fields, body):
    head = ["---", f"id: {fields['id']}", f"anchors: [{', '.join(fields['anchors'])}]",
            f"by: {fields['by']}"]
    if fields.get("source"):
        head.append(f"source: {fields['source']}")
    head += [f"verified: {fields['verified']}", "---"]
    wrapped = textwrap.fill(" ".join(body.split()), 96, break_long_words=False, break_on_hyphens=False)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(head) + "\n" + wrapped + "\n")


def cmd_add(a):
    text = sys.stdin.read() if a.text == ["-"] else " ".join(a.text)
    body = " ".join(text.split())
    problems = []
    if not ID_RE.fullmatch(a.id):
        problems.append(f"id {a.id!r} must be a kebab-case slug (a-z, 0-9, -)")
    path = os.path.join(FACTS, f"{a.id}.md")
    if os.path.exists(path):
        problems.append(f"{FACTS_REL}/{a.id}.md exists: edit it instead")
    for raw in a.anchor:
        err = resolve_error(Anchor(raw))
        if err:
            problems.append(f"anchor {raw}: {err}")
    if not BY_RE.fullmatch(a.by.strip()):
        problems.append("--by must be '<seat> <Name>' (several: comma-separated), seat lead/po/sm/owner/dev-<n>")
    if not body:
        problems.append("the fact text is empty")
    elif words(body) > WORD_CAP:
        problems.append(f"{words(body)} words is over the {WORD_CAP}-word cap: cut it")
    if problems:
        print("facts add: nothing written:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    for f in load_facts():
        if f.body and overlap(body, f.body) >= DUP_OVERLAP:
            print(f"facts add: refused, this repeats {f.id} ({overlap(body, f.body):.0%} word overlap):\n")
            print(open(f.path, encoding="utf-8").read())
            print(f"Edit {FACTS_REL}/{f.id}.md instead (add the new detail or anchor), then "
                  f"`facts.py verify {f.id}`.")
            return 1
    os.makedirs(FACTS, exist_ok=True)
    fields = {"id": a.id, "anchors": [Anchor(x).raw for x in a.anchor], "by": " ".join(a.by.split()),
              "source": a.source, "verified": f"{short('HEAD')} {datetime.date.today().isoformat()}"}
    write_fact(path, fields, body)
    print(f"facts: wrote {FACTS_REL}/{a.id}.md ({words(body)}/{WORD_CAP} words, verified "
          f"{fields['verified']}). Commit it with your change.")
    return 0


def cmd_stale(a):
    tip = short(a.to)
    facts = load_facts()
    stale, gone = [], []
    for f in facts:
        if f.errors:
            gone.append((f, [("file", "; ".join(f.errors) + " (facts.py lint)")]))
            continue
        s = fact_state(f, a.to)
        if s["stale"]:
            stale.append((f, s["stale"]))
        if s["gone"]:
            gone.append((f, s["gone"]))
    if not stale and not gone:
        print(f"No stale facts: {len(facts)} fact(s), every anchor unchanged since its verified "
              f"commit (up to {a.to} = {tip}).")
        return 0
    for title, rows in (("Stale (anchor changed since the verified commit, up to "
                         f"{a.to} = {tip})", stale),
                        ("Anchor gone (the file, symbol or component no longer exists)", gone)):
        if rows:
            print(f"{title}:")
            for f, items in rows:
                sha, day = f.verified
                print(f"  {f.id}  (verified {sha} {day}, {f.fields.get('by', '?')})")
                for anc, detail in items:
                    print(f"      {anc}: {detail}")
            print()
    print("Re-check each against the code. Still true: facts.py verify ID. Partly true: edit the "
          "body or anchors, then verify.\nNo longer true: facts.py retire ID --why \"...\".")
    return 1


def find(fid):
    path = os.path.join(FACTS, f"{fid}.md")
    if not os.path.exists(path):
        raise Bad(f"no fact {fid!r} in {FACTS_REL}/")
    return Fact(path)


def cmd_verify(a):
    sha, today, rc = short(a.ref), datetime.date.today().isoformat(), 0
    for fid in a.ids:
        f = find(fid)
        if f.errors:
            print(f"{fid}: not stamped, fix it first: {'; '.join(f.errors)}")
            rc = 1
            continue
        errs = [f"{x}: {e}" for x in f.anchors if (e := resolve_error(x, a.ref))]
        if errs:
            print(f"{fid}: not stamped, anchor gone at {a.ref}: {'; '.join(errs)}. Fix the anchors "
                  "first (or retire the fact).")
            rc = 1
            continue
        text = open(f.path, encoding="utf-8").read()
        head, sep, body = text[4:].partition("\n---")
        head, n = re.subn(r"^verified:.*$", f"verified: {sha} {today}", head, count=1, flags=re.M)
        if not n:
            head += f"\nverified: {sha} {today}"
        with open(f.path, "w", encoding="utf-8") as fh:
            fh.write("---\n" + head + sep + body)
        print(f"{fid}: verified {sha} {today}")
    return rc


def cmd_retire(a):
    f = find(a.id)
    os.remove(f.path)
    print(f"facts: retired {a.id}: {' '.join(a.why.split())}\n"
          f"Commit the deletion with that reason in the message; git keeps the history.")
    return 0


def cmd_lint(a):
    facts, problems = load_facts(), []
    for f in facts:
        where = f"{FACTS_REL}/{f.fid}.md"
        if f.errors:
            problems += [f"{where}: {e}" for e in f.errors]
            continue
        for k in f.fields:
            if k not in FIELDS:
                problems.append(f"{where}: unknown field {k!r} (fields: {', '.join(FIELDS)})")
        for k in REQUIRED:
            if not f.fields.get(k):
                problems.append(f"{where}: missing {k}")
        if f.fields.get("id") and f.fields["id"] != f.fid:
            problems.append(f"{where}: id {f.fields['id']!r} differs from the file name")
        if not ID_RE.fullmatch(f.fid):
            problems.append(f"{where}: file name must be a kebab-case id")
        for x in f.anchors:
            err = resolve_error(x)
            if err:
                problems.append(f"{where}: anchor {x}: {err}")
        if f.fields.get("by") and not BY_RE.fullmatch(f.fields["by"]):
            problems.append(f"{where}: by must be '<seat> <Name>'")
        sha, _ = f.verified
        if f.fields.get("verified") and not sha:
            problems.append(f"{where}: verified must be '<short sha> <YYYY-MM-DD>'")
        elif sha and not is_commit(sha):
            problems.append(f"{where}: verified commit {sha} is not known here")
        if not f.body:
            problems.append(f"{where}: empty body")
        elif words(f.body) > WORD_CAP:
            problems.append(f"{where}: {words(f.body)} words, over the {WORD_CAP}-word cap")
    good = [f for f in facts if not f.errors and f.body]
    for i, f in enumerate(good):
        for g in good[i + 1:]:
            ov = overlap(f.body, g.body)
            if ov >= DUP_OVERLAP:
                problems.append(f"near-duplicates: {f.fid} and {g.fid} ({ov:.0%} word overlap): merge them")
    for p in problems:
        print(p)
    print(f"{len(facts)} fact(s), {len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_stats(a):
    facts = load_facts()
    by = {}
    for f in facts:
        for k in (x.strip() for x in f.fields.get("by", "?").split(",")):
            by[k] = by.get(k, 0) + 1
    stale = gone = 0
    for f in facts:
        if f.errors:
            gone += 1
            continue
        s = fact_state(f, "HEAD")
        stale += bool(s["stale"])
        gone += bool(s["gone"])
    out = {"facts": len(facts), "by_author": dict(sorted(by.items(), key=lambda x: (-x[1], x[0]))),
           "stale": stale, "anchor_gone": gone}
    if a.since:
        short(a.since)
        before = {os.path.basename(p)[:-3] for p in
                  (git("ls-tree", "-r", "--name-only", a.since, "--", FACTS_REL + "/") or "").splitlines()
                  if p.endswith(".md") and not p.endswith("README.md")}
        now = {f.fid for f in facts}
        out.update(since=a.since, added=sorted(now - before), retired=sorted(before - now))
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"facts: {out['facts']}" + (" (by author: " + ", ".join(f"{k} {v}" for k, v in out["by_author"].items())
                                       + ")" if by else ""))
    if a.since:
        print(f"added since {a.since}: {len(out['added'])}" + (f" ({', '.join(out['added'])})" if out["added"] else ""))
        print(f"retired since {a.since}: {len(out['retired'])}" +
              (f" ({', '.join(out['retired'])})" if out["retired"] else ""))
    print(f"stale: {stale}, anchor gone: {gone}" + (" (facts.py stale)" if stale or gone else ""))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="facts.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)

    def matching(q):
        q.add_argument("--depth", type=int, choices=(0, 1), default=1,
                       help="1 (default): add facts on graph neighbours")
        q.add_argument("--no-graph", action="store_true", help="no GitNexus (same as --depth 0)")
        q.add_argument("--all", action="store_true", help="show every match")
        q.add_argument("--max", type=int, default=DEFAULT_MAX)
    for name in ("for", "brief"):
        q = s.add_parser(name)
        q.add_argument("targets", nargs="+", help="path, path::symbol or comp:name")
        matching(q)
    q = s.add_parser("diff")
    g = q.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true")
    g.add_argument("--base")
    q.add_argument("--hook", action="store_true", help="pre-commit mode: short, bounded, never fails")
    matching(q)
    q = s.add_parser("add")
    q.add_argument("--id", required=True)
    q.add_argument("--anchor", action="append", required=True)
    q.add_argument("--by", required=True)
    q.add_argument("--source")
    q.add_argument("text", nargs="+", help='the fact, or "-" for stdin')
    q = s.add_parser("stale")
    q.add_argument("--to", default="HEAD")
    q = s.add_parser("verify")
    q.add_argument("ids", nargs="+")
    q.add_argument("--ref", default="HEAD")
    q = s.add_parser("retire")
    q.add_argument("id")
    q.add_argument("--why", required=True)
    s.add_parser("lint")
    q = s.add_parser("stats")
    q.add_argument("--since")
    q.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    hook = a.cmd == "diff" and a.hook
    try:
        init_paths()
        return {"for": cmd_for, "brief": cmd_brief, "diff": cmd_diff, "add": cmd_add,
                "stale": cmd_stale, "verify": cmd_verify, "retire": cmd_retire, "lint": cmd_lint,
                "stats": cmd_stats}[a.cmd](a)
    except Bad as e:
        if hook:
            return 0
        print(f"facts: {e}", file=sys.stderr)
        return 2
    except Exception:
        if hook:                     # the pre-commit hook must never block or spam a commit
            return 0
        raise


if __name__ == "__main__":
    sys.exit(main())
