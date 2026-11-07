"""Team facts (.claude/team/facts.py): anchored facts that surface by footprint.

facts.py is a stand-alone CLI that reads .claude/team/facts/ in the current checkout, so each
test runs it in a fresh temporary git repository. GitNexus is replaced by a stub command
(FACTS_GITNEXUS), or switched off with an empty FACTS_GITNEXUS.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

TEAM = Path(__file__).resolve().parents[2] / ".claude" / "team"
FACTS = TEAM / "facts.py"
MEMBER = TEAM / "member.py"
HOOK = Path(__file__).resolve().parents[2] / ".githooks" / "pre-commit"

SVC = '''\
def alpha(x):
    y = x + 1
    return y


def beta(x):
    return x * 2


class Repo:
    def get(self, key):
        return key

    def put(self, key, value):
        return value
'''

STUB = '''\
import json, os, sys
q = sys.argv[2]
mode = os.environ.get("STUB_MODE", "healthy")
if mode == "fail":
    print("Error: boom", file=sys.stderr)
    sys.exit(1)
if "n:Function" in q:
    rows = [["f", "a.py"]] * 3 if mode == "healthy" else [["", ""]] * 3
    hdr = "| n.name | n.filePath |"
else:
    rows = json.loads(os.environ.get("STUB_EDGES", "[]")) if mode == "healthy" else []
    hdr = "| a.name | a.filePath | b.name | b.filePath |"
md = "\\n".join([hdr, "| --- | --- |"] + ["| " + " | ".join(r) + " |" for r in rows])
print(json.dumps({"markdown": md, "row_count": len(rows)}))
'''


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "T")
    git(r, "config", "core.hooksPath", "/dev/null")
    write(r, "backend/app/db/svc.py", SVC)
    write(r, "backend/app/caller.py", "from backend.app.db.svc import alpha\n\n\ndef use_alpha():\n    return alpha(1)\n")
    write(r, "observability/mimir/mimir.yaml", "limits: {}\n")
    write(r, "frontend/src/thing.tsx", "export function Thing() {\n  return <p>Don't {x}</p>;\n}\n\n"
                                       "export const other = 3;\n")
    commit(r, "init")
    return r


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def commit(repo: Path, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "--short", "HEAD")


def fact(repo: Path, fid: str, anchors: list[str], body: str, *, by: str = "dev-1 Ansel",
         verified: str | None = None) -> Path:
    sha = verified or git(repo, "rev-parse", "--short", "HEAD")
    p = repo / ".claude" / "team" / "facts" / f"{fid}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nid: {fid}\nanchors: [{', '.join(anchors)}]\nby: {by}\n"
                 f"verified: {sha} 2026-11-05\n---\n{body}\n")
    return p


def run(repo: Path, *args: str, graph: str | None = "", stdin: str | None = None,
        env: dict | None = None, tool: Path = FACTS) -> subprocess.CompletedProcess:
    e = {k: v for k, v in os.environ.items() if not k.startswith(("FACTS_", "STUB_"))}
    if graph is not None:
        e["FACTS_GITNEXUS"] = graph
    e.update(env or {})
    return subprocess.run([sys.executable, str(tool), *args], cwd=repo, env=e, input=stdin,
                          capture_output=True, text=True, timeout=60)


@pytest.fixture
def stub(tmp_path: Path) -> str:
    s = tmp_path / "gitnexus_stub.py"
    s.write_text(STUB)
    return f"{sys.executable} {s}"


def ids(out: str) -> list[str]:
    return re.findall(r"^- (\S+)  \[", out, re.M)


# ---------------------------------------------------------------- parsing and lint

def test_lint_accepts_good_facts_including_block_anchor_lists(repo: Path) -> None:
    fact(repo, "mimir-names", ["comp:mimir", "file:observability/mimir/"],
         "Mimir keeps OTLP metric names with dots turned into underscores and no unit suffix.")
    p = repo / ".claude/team/facts/svc-alpha.md"
    p.write_text("---\nid: svc-alpha\nanchors:\n  - sym:backend/app/db/svc.py::alpha\n"
                 "  - sym:backend/app/db/svc.py::Repo.get\nby: po Maren\nsource: board #3\n"
                 f"verified: {git(repo, 'rev-parse', '--short', 'HEAD')} 2026-11-05\n---\n"
                 "alpha adds one before returning; callers rely on the increment happening here.\n")
    fact(repo, "thing-tsx", ["sym:frontend/src/thing.tsx::Thing", "sym:frontend/src/thing.tsx::other"],
         "Thing renders a paragraph; other is a constant exported beside it.")
    r = run(repo, "lint")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "3 fact(s), 0 problem(s)" in r.stdout


def test_lint_reports_each_kind_of_problem(repo: Path) -> None:
    fact(repo, "bad-anchors", ["comp:nosuch", "file:missing/file.py", "sym:backend/app/db/svc.py::gamma",
                               "sym:observability/mimir/mimir.yaml::x", "url:http://x"],
         "Anchors that do not resolve at all in this repository checkout.")
    fact(repo, "too-long", ["file:backend/app/db/svc.py"], " ".join(f"word{i}" for i in range(81)))
    fact(repo, "bad-by", ["file:backend/app/db/svc.py"], "Who wrote this is not a seat name.", by="Ansel")
    fact(repo, "bad-sha", ["file:backend/app/db/svc.py"], "The verified commit is not known.",
         verified="deadbee")
    p = fact(repo, "wrong-id", ["file:backend/app/db/svc.py"], "The id is not the file name.")
    p.write_text(p.read_text().replace("id: wrong-id", "id: other-id"))
    (repo / ".claude/team/facts/no-front.md").write_text("just text\n")
    r = run(repo, "lint")
    assert r.returncode == 1
    out = r.stdout
    for needle in ("unknown component 'nosuch'", "no file missing/file.py", "no symbol gamma",
                   "sym: works in", "anchor kind must be", "81 words, over the 80-word cap",
                   "by must be", "verified commit deadbee is not known", "differs from the file name",
                   "no front matter"):
        assert needle in out, needle


def test_lint_flags_near_duplicate_pairs(repo: Path) -> None:
    body = "Mimir answers 200 to duplicate timestamp samples and drops them silently without any error."
    fact(repo, "dup-a", ["comp:mimir"], body)
    fact(repo, "dup-b", ["comp:mimir"], body.replace("without any error", "with no error at all"))
    r = run(repo, "lint")
    assert r.returncode == 1
    assert "near-duplicates: dup-a and dup-b" in r.stdout


# ---------------------------------------------------------------- add

def test_add_writes_a_stamped_fact(repo: Path) -> None:
    r = run(repo, "add", "--id", "pg-shared-db", "--anchor", "comp:postgres", "--anchor",
            "file:backend/app/db/", "--by", "dev-2 Nils", "--source", "board #9", "-",
            stdin="The Postgres tests share one long-lived database,\nso clean up the rows you add.\n")
    assert r.returncode == 0, r.stderr
    text = (repo / ".claude/team/facts/pg-shared-db.md").read_text()
    head = git(repo, "rev-parse", "--short", "HEAD")
    assert f"verified: {head} " in text
    assert "anchors: [comp:postgres, file:backend/app/db/]" in text and "source: board #9" in text
    assert run(repo, "lint").returncode == 0


def test_add_refuses_a_near_duplicate_and_shows_it(repo: Path) -> None:
    fact(repo, "mimir-dupes", ["comp:mimir"],
         "Mimir answers 200 to duplicate timestamp samples and drops them silently.")
    r = run(repo, "add", "--id", "mimir-dupes-2", "--anchor", "comp:mimir", "--by", "dev-1 Ansel",
            "Mimir", "answers", "200", "to", "duplicate", "timestamp", "samples", "and", "silently", "drops", "them.")
    assert r.returncode == 1
    assert "repeats mimir-dupes" in r.stdout and "id: mimir-dupes" in r.stdout
    assert "Edit .claude/team/facts/mimir-dupes.md instead" in r.stdout
    assert not (repo / ".claude/team/facts/mimir-dupes-2.md").exists()


def test_add_rejects_invalid_input(repo: Path) -> None:
    r = run(repo, "add", "--id", "Bad_Id", "--anchor", "sym:backend/app/db/svc.py::nope", "--by", "x",
            " ".join(["w"] * 81))
    assert r.returncode == 2
    for needle in ("kebab-case", "no symbol nope", "--by must be", "over the 80-word cap"):
        assert needle in r.stderr


# ---------------------------------------------------------------- for: ranking

def ranking_facts(repo: Path) -> None:
    fact(repo, "a-direct-file", ["file:backend/app/db/svc.py"], "Direct anchor on the file itself here.")
    fact(repo, "b-sym-in-file", ["sym:backend/app/db/svc.py::beta"], "Beta doubles its input value always.")
    fact(repo, "c-parent-dir", ["file:backend/app/"], "Everything in the backend app package is async.")
    fact(repo, "d-component", ["comp:postgres"], "Postgres tests share one long lived database instance.")
    fact(repo, "e-neighbour", ["sym:backend/app/caller.py::use_alpha"], "use_alpha pins the argument to one.")
    fact(repo, "f-unrelated", ["comp:mimir"], "Mimir histograms are native with no bucket series.")


EDGES = json.dumps([["use_alpha", "backend/app/caller.py", "alpha", "backend/app/db/svc.py"],
                    ["alpha", "backend/app/db/svc.py", "beta", "backend/app/db/svc.py"]])


def test_for_ranks_direct_file_component_then_neighbour(repo: Path, stub: str) -> None:
    ranking_facts(repo)
    r = run(repo, "for", "backend/app/db/svc.py", graph=stub, env={"STUB_EDGES": EDGES})
    assert r.returncode == 0, r.stderr
    assert ids(r.stdout) == ["a-direct-file", "b-sym-in-file", "c-parent-dir", "d-component", "e-neighbour"]
    assert "[neighbour: sym:backend/app/caller.py::use_alpha calls backend/app/db/svc.py::alpha]" in r.stdout
    assert "warning" not in r.stdout
    r0 = run(repo, "for", "backend/app/db/svc.py", "--depth", "0", graph=stub, env={"STUB_EDGES": EDGES})
    assert "e-neighbour" not in ids(r0.stdout)


def test_for_on_a_symbol_and_a_component(repo: Path, stub: str) -> None:
    ranking_facts(repo)
    r = run(repo, "for", "backend/app/db/svc.py::alpha", graph=stub, env={"STUB_EDGES": EDGES})
    # beta is another symbol in the same file: it shows only as alpha's callee (a neighbour)
    assert ids(r.stdout) == ["a-direct-file", "c-parent-dir", "d-component", "b-sym-in-file", "e-neighbour"]
    assert "[file: file:backend/app/db/svc.py holds" in r.stdout  # a file anchor is rank 2 for a symbol
    assert "[neighbour: sym:backend/app/db/svc.py::beta called by backend/app/db/svc.py::alpha]" in r.stdout
    assert "b-sym-in-file" not in ids(run(repo, "for", "backend/app/db/svc.py::alpha", "--depth", "0").stdout)
    c = run(repo, "for", "comp:mimir")
    assert ids(c.stdout) == ["f-unrelated"]
    assert run(repo, "for", "comp:nosuch").returncode == 2


def test_for_caps_the_output(repo: Path) -> None:
    for i in range(14):
        fact(repo, f"cap-{i:02d}", ["file:backend/app/db/svc.py"], f"distinct{i} lesson{i} about{i} item{i}")
    r = run(repo, "for", "backend/app/db/svc.py")
    assert len(ids(r.stdout)) == 12 and "2 more fact(s) left out; --all shows them." in r.stdout
    assert len(ids(run(repo, "for", "backend/app/db/svc.py", "--all").stdout)) == 14


def test_brief_prints_a_markdown_section(repo: Path) -> None:
    ranking_facts(repo)
    r = run(repo, "brief", "backend/app/db/svc.py")
    assert r.stdout.startswith("## Known facts for this footprint")
    assert "- **a-direct-file** (direct: file:backend/app/db/svc.py; verified" in r.stdout



def test_brief_runs_adds_facts_for_paths_the_developer_runs(repo: Path) -> None:
    write(repo, "observability/test/lib.sh", "PORT=12347\n")
    commit(repo, "lib")
    fact(repo, "lib-ports", ["file:observability/test/lib.sh"], "lib.sh keeps the Faro port at 12347.")
    commit(repo, "fact")
    written_only = run(repo, "brief", "backend/app/db/svc.py")
    assert "lib-ports" not in written_only.stdout
    r = run(repo, "brief", "backend/app/db/svc.py", "--runs", "observability/test/lib.sh")
    assert r.returncode == 0
    assert "the paths you run: `observability/test/lib.sh`" in r.stdout
    assert "- **lib-ports** (direct: file:observability/test/lib.sh (you run it);" in r.stdout
    only_runs = run(repo, "brief", "--runs", "observability/test/lib.sh")
    assert only_runs.returncode == 0 and "lib-ports" in only_runs.stdout
    assert run(repo, "brief").returncode == 2


def test_brief_runs_before_the_written_paths_does_not_swallow_them(repo: Path) -> None:
    """BUG-014: `--runs` used to take every path after it, so `--runs LIB WRITTEN` lost WRITTEN."""
    write(repo, "observability/test/lib.sh", "PORT=12347\n")
    commit(repo, "lib")
    ranking_facts(repo)
    fact(repo, "lib-ports", ["file:observability/test/lib.sh"], "lib.sh keeps the Faro port at 12347.")
    commit(repo, "fact")
    r = run(repo, "brief", "--runs", "observability/test/lib.sh", "backend/app/db/svc.py")
    assert r.returncode == 0, r.stderr
    assert "a-direct-file" in r.stdout and "lib-ports" in r.stdout        # written and run both used
    assert "the paths you run: `observability/test/lib.sh`" in r.stdout
    assert "(direct: file:backend/app/db/svc.py; verified" in r.stdout       # not labelled "you run it"
    two = run(repo, "brief", "--runs", "observability/test/lib.sh", "--runs", "backend/app/db/svc.py")
    assert "`observability/test/lib.sh`, `backend/app/db/svc.py`" in two.stdout

# ---------------------------------------------------------------- graph health fallback

def test_unhealthy_index_warns_once_and_falls_back(repo: Path, stub: str) -> None:
    ranking_facts(repo)
    r = run(repo, "for", "backend/app/db/svc.py", graph=stub,
            env={"STUB_MODE": "broken", "STUB_EDGES": EDGES})
    assert r.returncode == 0
    assert r.stdout.count("GitNexus index unhealthy: run `node .gitnexus/run.cjs analyze --index-only --force`") == 1
    assert ids(r.stdout) == ["a-direct-file", "b-sym-in-file", "c-parent-dir", "d-component"]


def test_failing_or_absent_graph_still_matches_files(repo: Path, stub: str) -> None:
    ranking_facts(repo)
    r = run(repo, "for", "backend/app/db/svc.py", graph=stub, env={"STUB_MODE": "fail"})
    assert "GitNexus unavailable (Error: boom)" in r.stdout and "a-direct-file" in r.stdout
    none = run(repo, "for", "backend/app/db/svc.py", graph="")
    assert "warning" not in none.stdout and "d-component" in ids(none.stdout)
    no_flag = run(repo, "for", "backend/app/db/svc.py", "--no-graph", graph=stub,
                  env={"STUB_MODE": "fail"})
    assert "warning" not in no_flag.stdout


# ---------------------------------------------------------------- diff

def test_diff_staged_maps_hunks_to_symbols(repo: Path) -> None:
    fact(repo, "alpha-fact", ["sym:backend/app/db/svc.py::alpha"], "alpha increments before returning.")
    fact(repo, "beta-fact", ["sym:backend/app/db/svc.py::beta"], "beta doubles and never rounds.")
    fact(repo, "get-fact", ["sym:backend/app/db/svc.py::Repo.get"], "Repo get returns the key as is.")
    staged = SVC.replace("y = x + 1", "y = x + 2").replace("return key", "return str(key)")
    write(repo, "backend/app/db/svc.py", staged)
    git(repo, "add", "backend/app/db/svc.py")
    write(repo, "backend/app/db/svc.py", staged.replace("return x * 2", "return x * 3"))  # unstaged only
    r = run(repo, "diff", "--staged")
    assert r.returncode == 0
    assert ids(r.stdout) == ["alpha-fact", "get-fact"]
    assert "(1 file(s), 2 symbol(s))" in r.stdout
    assert set(ids(run(repo, "diff").stdout)) == {"alpha-fact", "beta-fact", "get-fact"}  # vs HEAD


def test_diff_base_and_the_hook_format(repo: Path) -> None:
    fact(repo, "mimir-names", ["comp:mimir"], "Mimir keeps OTLP names with underscores and no suffix.")
    commit(repo, "facts")
    write(repo, "observability/mimir/mimir.yaml", "limits: {max: 1}\n")
    commit(repo, "tune mimir")
    assert ids(run(repo, "diff", "--base", "HEAD~1").stdout) == ["mimir-names"]
    write(repo, "observability/mimir/mimir.yaml", "limits: {max: 2}\n")
    git(repo, "add", "-A")
    h = run(repo, "diff", "--staged", "--hook")
    assert h.returncode == 0
    lines = h.stdout.splitlines()
    assert lines[0].startswith("team facts for this commit (1;")
    assert lines[1].startswith("  mimir-names [component]: Mimir keeps")
    git(repo, "reset", "-q", "--hard")
    write(repo, "frontend/src/thing.tsx", "export function Thing() {\n  return null;\n}\n")
    git(repo, "add", "-A")
    quiet = run(repo, "diff", "--staged", "--hook")
    assert quiet.returncode == 0 and quiet.stdout == ""


def test_hook_output_is_bounded(repo: Path) -> None:
    for i in range(15):
        fact(repo, f"many-{i:02d}", ["comp:mimir"], f"unique{i} words{i} here{i} only{i} " + "x" * 200)
    commit(repo, "facts")
    write(repo, "observability/mimir/mimir.yaml", "limits: {max: 3}\n")
    git(repo, "add", "-A")
    lines = run(repo, "diff", "--staged", "--hook").stdout.splitlines()
    assert len(lines) <= 12 and lines[-1] == "  +5 more"
    assert all(len(line) <= 150 for line in lines[1:])


def test_pre_commit_hook_shows_facts_and_never_blocks(repo: Path) -> None:
    hooks = repo / ".githooks"
    hooks.mkdir()
    shutil.copy(HOOK, hooks / "pre-commit")
    (repo / ".claude/team").mkdir(parents=True, exist_ok=True)
    shutil.copy(FACTS, repo / ".claude/team/facts.py")
    git(repo, "config", "core.hooksPath", ".githooks")
    fact(repo, "mimir-names", ["comp:mimir"], "Mimir keeps OTLP names with underscores and no suffix.")
    env = {k: v for k, v in os.environ.items() if not k.startswith("FACTS_")} | {"FACTS_GITNEXUS": ""}
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "facts"], cwd=repo, check=True, env=env)
    write(repo, "observability/mimir/mimir.yaml", "limits: {max: 4}\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    c = subprocess.run(["git", "commit", "-q", "-m", "tune"], cwd=repo, env=env, capture_output=True, text=True)
    assert c.returncode == 0 and "mimir-names [component]" in c.stderr
    (repo / ".claude/team/facts.py").write_text("import sys\nprint('boom' * 50)\nsys.exit(3)\n")
    write(repo, "observability/mimir/mimir.yaml", "limits: {max: 5}\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    c = subprocess.run(["git", "commit", "-q", "-m", "broken tool"], cwd=repo, env=env,
                       capture_output=True, text=True)
    assert c.returncode == 0


# ---------------------------------------------------------------- stale and verify

def test_stale_file_symbol_and_gone_anchors(repo: Path) -> None:
    fact(repo, "file-fact", ["file:observability/mimir/"], "Mimir config lives in one yaml file only.")
    fact(repo, "alpha-fact", ["sym:backend/app/db/svc.py::alpha"], "alpha increments before returning.")
    fact(repo, "put-fact", ["sym:backend/app/db/svc.py::Repo.put"], "Repo put returns the stored value.")
    fact(repo, "gone-fact", ["sym:backend/app/caller.py::use_alpha"], "use_alpha pins its argument.")
    fact(repo, "comp-fact", ["comp:redis"], "Redis is optional; the cache degrades to memory.")
    commit(repo, "facts")
    assert run(repo, "stale").returncode == 0
    # change inside alpha and in mimir; add a line above Repo (shifts put but does not touch it)
    write(repo, "backend/app/db/svc.py", SVC.replace("y = x + 1", "y = x + 5").replace(
        "class Repo:", "# a note\nclass Repo:"))
    write(repo, "observability/mimir/mimir.yaml", "limits: {max: 9}\n")
    (repo / "backend/app/caller.py").unlink()
    commit(repo, "changes")
    r = run(repo, "stale")
    assert r.returncode == 1
    stale_part, _, gone_part = r.stdout.partition("Anchor gone")
    assert "file-fact" in stale_part and "observability/mimir/mimir.yaml" in stale_part
    assert "alpha-fact" in stale_part and "lines 1-3 of backend/app/db/svc.py changed" in stale_part
    assert "put-fact" not in r.stdout and "comp-fact" not in r.stdout
    assert "gone-fact" in gone_part and "no file backend/app/caller.py at HEAD" in gone_part
    # verify re-stamps; a fact whose anchor is gone is refused
    v = run(repo, "verify", "file-fact", "alpha-fact")
    assert v.returncode == 0
    head = git(repo, "rev-parse", "--short", "HEAD")
    assert f"verified: {head} " in (repo / ".claude/team/facts/alpha-fact.md").read_text()
    g = run(repo, "verify", "gone-fact")
    assert g.returncode == 1 and "anchor gone" in g.stdout
    assert run(repo, "verify", "nope").returncode == 2
    commit(repo, "verified")
    r2 = run(repo, "stale")
    assert "file-fact" not in r2.stdout and "alpha-fact" not in r2.stdout and "gone-fact" in r2.stdout
    t = run(repo, "retire", "gone-fact", "--why", "caller.py was removed")
    assert t.returncode == 0 and "caller.py was removed" in t.stdout
    assert run(repo, "stale").returncode == 0


def test_stale_symbol_change_outside_the_range_is_not_stale(repo: Path) -> None:
    fact(repo, "beta-fact", ["sym:backend/app/db/svc.py::beta"], "beta doubles and never rounds.")
    commit(repo, "facts")
    write(repo, "backend/app/db/svc.py", SVC.replace("y = x + 1", "y = x + 7") + "\n\ndef gamma():\n    pass\n")
    commit(repo, "edit alpha, add gamma")
    assert run(repo, "stale").returncode == 0
    write(repo, "backend/app/db/svc.py", (repo / "backend/app/db/svc.py").read_text().replace(
        "return x * 2", "return x * 4"))
    commit(repo, "edit beta")
    assert "beta-fact" in run(repo, "stale").stdout


def test_for_marks_stale_facts(repo: Path) -> None:
    fact(repo, "file-fact", ["file:observability/mimir/mimir.yaml"], "Mimir config lives in one file.")
    commit(repo, "facts")
    write(repo, "observability/mimir/mimir.yaml", "limits: {max: 9}\n")
    commit(repo, "change")
    assert "STALE: re-check it, then facts.py verify file-fact" in run(repo, "for", "comp:mimir").stdout



def test_a_fact_edit_does_not_stale_a_directory_anchor_above_the_facts(repo: Path) -> None:
    write(repo, ".claude/team/tool.py", "X = 1\n")
    commit(repo, "tool")
    fact(repo, "team-dir", ["file:.claude/team/"], "Team tools are stdlib-only scripts.")
    fact(repo, "facts-dir", ["file:.claude/team/facts/"], "Facts are markdown files with front matter.")
    commit(repo, "facts")
    fact(repo, "other", ["comp:redis"], "Redis is optional; the cache degrades to memory.")
    commit(repo, "a fact edit only")
    def stale_ids() -> list[str]:
        return re.findall(r"^  (\S+)  \(verified", run(repo, "stale").stdout, re.M)

    assert stale_ids() == ["facts-dir"]
    write(repo, ".claude/team/tool.py", "X = 2\n")
    commit(repo, "a tool edit")
    assert stale_ids() == ["facts-dir", "team-dir"]

# ---------------------------------------------------------------- stats and member lint

def test_stats_counts_by_author_added_and_stale(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    fact(repo, "one", ["comp:mimir"], "First lesson about mimir names.")
    fact(repo, "two", ["comp:redis"], "Second lesson about the redis cache.", by="po Maren")
    commit(repo, "facts")
    r = run(repo, "stats", "--since", base, "--json")
    data = json.loads(r.stdout)
    assert data["facts"] == 2 and data["by_author"] == {"dev-1 Ansel": 1, "po Maren": 1}
    assert data["added"] == ["one", "two"] and data["stale"] == 0
    assert "added since" in run(repo, "stats", "--since", base).stdout


def test_member_lint_flags_a_memory_line_that_repeats_a_fact(repo: Path) -> None:
    fact(repo, "mimir-dupes", ["comp:mimir"],
         "Mimir answers 200 to duplicate timestamp samples and drops them silently without an error.")
    subprocess.run([sys.executable, str(MEMBER), "claim", "--seat", "dev-1", "--name", "Ansel",
                    "--role", "developer", "--about", "x"], cwd=repo, check=True, capture_output=True)
    memory = textwrap.dedent("""\
        - Mimir answers 200 for duplicate timestamp samples and silently drops them.
        - Something else entirely unrelated about frontend routing tables and layouts.
    """)
    subprocess.run([sys.executable, str(MEMBER), "remember", "--seat", "dev-1", "-"], cwd=repo,
                   input=memory, check=True, capture_output=True, text=True)
    out = subprocess.run([sys.executable, str(MEMBER), "lint", "--seat", "dev-1"], cwd=repo,
                         capture_output=True, text=True, check=True).stdout
    assert "1 line(s) worth a look" in out
    assert "repeats team fact mimir-dupes" in out


def test_module_and_class_constants_are_anchorable(repo: Path) -> None:
    write(repo, "backend/app/consts.py", "LIMITS = {'a': 1}\n_clock: object = None\n\n\n"
                                         "class Box:\n    SIZE = 3\n")
    commit(repo, "consts")
    fact(repo, "consts", ["sym:backend/app/consts.py::LIMITS", "sym:backend/app/consts.py::_clock",
                          "sym:backend/app/consts.py::Box.SIZE"], "Module constants are valid anchors.")
    r = run(repo, "lint")
    assert r.returncode == 0, r.stdout + r.stderr


def test_several_authors_lint_and_count_separately(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    fact(repo, "shared", ["comp:mimir"], "Both learned the mimir naming lesson.", by="dev-1 Ansel, dev-3 Nils")
    commit(repo, "facts")
    assert run(repo, "lint").returncode == 0
    data = json.loads(run(repo, "stats", "--since", base, "--json").stdout)
    assert data["by_author"] == {"dev-1 Ansel": 1, "dev-3 Nils": 1}
