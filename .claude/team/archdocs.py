#!/usr/bin/env python3
"""Keep documentation/architecture/ in step with the code (sprint close-out step).

Agent-facing, and fine for humans. Every architecture page carries
<meta name="verified-at" content="commit <sha> · <date>">: the commit its facts were last
checked against. This tool says which pages the code has moved under since then, stamps pages
after they have been re-checked, and checks the site's links and structure.

  archdocs.py changed [--to REF]     code paths changed since each page's stamp, grouped by page
  archdocs.py stamp [PAGE...] [--ref REF]
                                     write REF's commit + today into the pages (default: all pages)
  archdocs.py check                  nav, links, anchors, stamps, no <style>/external resources
  archdocs.py gate [--branches main]  git hook (.githooks/pre-merge-commit): on a merge into main,
                                     refuse while any page's code moved past its stamp or check fails

The page map (PAGE_PATHS) decides which page owns a code path. A changed path no page owns is
listed under "unmapped": decide where it belongs, document it, and add it to PAGE_PATHS.
The procedure is in documentation/architecture/pages/maintaining.html.
Exit codes: changed = 0 nothing to re-check / 1 pages to re-check; check and gate = 0 clean / 1 problems.
The hook is enabled per clone with: git config core.hooksPath .githooks
"""
import argparse
import contextlib
import datetime
import io
import html.parser
import os
import re
import subprocess
import sys

ROOT = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                      check=True).stdout.strip()
DOCS = os.path.join(ROOT, "documentation", "architecture")

# Page -> path prefixes it owns. First match wins, so list specific paths before broad ones.
# "*" pages re-check on any change of these shared manifests (versions are quoted on them).
PAGE_PATHS = [
    ("pages/pdf-reports.html", [
        "backend/app/api/reports.py", "backend/app/services/pdf_report.py",
        "backend/app/services/charts.py", "backend/app/services/graphs.py",
        "backend/app/services/artifacts.py", "backend/app/assets/",
    ]),
    ("pages/streaming.html", ["backend/app/api/ws.py"]),
    ("pages/knowledge-base.html", [
        "backend/app/kb/", "backend/app/agent_tools/kb_tools.py", "backend/evals/",
        "backend/cli/kb", "backend/app/services/name_resolver.py",
    ]),
    ("pages/wcl-data.html", [
        "wcl_agent/client/", "wcl_agent/cache/", "backend/app/services/fetch_persistence.py",
        "backend/app/services/raw_fetch_reads.py", "backend/app/repositories/raw_fetches.py",
        "backend/app/services/kickoff_prefetch.py", "backend/app/agent_tools/stored_data_tools.py",
        "backend/app/api/cache_stats.py", "backend/app/services/guide_pipeline/sources",
    ]),
    ("pages/models.html", [
        "backend/app/model_state.py", "backend/app/api/models.py", "wcl_agent/llm",
        "wcl_agent/models", "backend/app/services/conversation_titles.py",
    ]),
    ("pages/auth-tenancy.html", [
        "backend/app/auth/", "backend/app/tenancy/", "backend/app/api/auth.py",
        "backend/app/api/admin_users.py", "backend/app/repositories/users.py",
        "backend/app/repositories/sessions.py", "backend/app/repositories/invitations.py",
        "backend/app/repositories/reset_tokens.py", "backend/app/repositories/tenants.py",
        "backend/app/repositories/audit.py", "backend/app/services/auth_service.py",
        "backend/app/services/invitation_service.py",
        "backend/app/services/password_reset_service.py",
    ]),
    ("pages/database.html", ["backend/migrations/", "backend/app/db/", "backend/alembic.ini"]),
    ("pages/deployment.html", [
        "docker-compose", "backend/Dockerfile", "frontend/Dockerfile", "frontend/nginx",
        "bin/", ".env.example", "backend/app/config.py", "backend/app/startup.py",
        "backend/cli/", "documentation/deployment.md",
    ]),
    ("pages/agent.html", [
        "backend/app/agent_runner.py", "backend/app/agent_tools/", "backend/app/services/guide",
        "backend/app/services/profile", "backend/app/repositories/profile_proposals.py",
        "backend/app/api/proposals.py", "backend/app/api/guides.py",
        "backend/app/api/admin_guides.py", "wcl_agent/",
    ]),
    ("pages/backend-api.html", ["backend/app/"]),
    ("pages/frontend.html", ["frontend/"]),
]
SHARED = {"pyproject.toml": ["pages/deployment.html", "pages/backend-api.html"],
          "frontend/package.json": ["pages/frontend.html"],
          "docker-compose.yml": ["pages/deployment.html", "pages/database.html"]}
# Paths that never affect the architecture pages.
IGNORE = re.compile(r"^(meta/|sprints/|specs/|qa-reports/|\.claude/|\.specify/|\.githooks/|documentation/(?!deployment\.md)|"
                    r"todo\.md|user_stories\.md|quotes\.md|tmp\.txt|CLAUDE\.md|AGENTS\.md|README\.md|LICENCE|\.gitignore|\.gitnexusignore|uv\.lock|package-lock\.json|"
                    r"frontend/package-lock\.json|.*\.pyc$|.*/tests?/|backend/tests/|frontend/src/.*\.test\.)")

STAMP_RE = re.compile(r'(<meta name="verified-at" content=")commit ([0-9a-f]{7,40}) · ([0-9-]{10})(">)')


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True,
                          cwd=ROOT).stdout.strip()


def pages():
    out = ["index.html"]
    pdir = os.path.join(DOCS, "pages")
    out += sorted("pages/" + f for f in os.listdir(pdir) if f.endswith(".html") and not f.startswith("_"))
    return out


def read(page):
    with open(os.path.join(DOCS, page), encoding="utf-8") as fh:
        return fh.read()


def stamp_of(page):
    m = STAMP_RE.search(read(page))
    return (m.group(2), m.group(3)) if m else (None, None)


def owner(path):
    if path in SHARED:
        return SHARED[path]
    for page, prefixes in PAGE_PATHS:
        if any(path.startswith(p) for p in prefixes):
            return [page]
    return []


def moved(diff):
    """Pages whose code changed since their stamp. `diff(sha)` lists changed paths from sha."""
    by_page, unmapped, bases = {}, set(), {}
    for page in pages():
        sha, _ = stamp_of(page)
        if not sha:
            by_page.setdefault(page, set()).add("(no verified-at stamp: re-check the whole page)")
            continue
        bases.setdefault(sha, []).append(page)
    for sha, pgs in bases.items():
        try:
            files = diff(sha)
        except subprocess.CalledProcessError:
            for p in pgs:
                by_page.setdefault(p, set()).add(f"(stamp {sha} is not a known commit: re-check the page)")
            continue
        for f in files:
            if IGNORE.match(f):
                continue
            own = owner(f)
            if not own:
                unmapped.add(f)
            for p in own:
                if p in pgs:
                    by_page.setdefault(p, set()).add(f)
    return by_page, unmapped


def report(by_page, unmapped):
    for p in sorted(by_page):
        print(f"{p}  (stamp {stamp_of(p)[0]})")
        for f in sorted(by_page[p]):
            print(f"    {f}")
    if unmapped:
        print("\nunmapped (no page owns these; decide, document, then add to PAGE_PATHS):")
        for f in sorted(unmapped):
            print(f"    {f}")
    print("\nAlso check index.html: the layer table and the system diagram summarise every page.")
    print("Re-verify those sections against the code, then: archdocs.py stamp && archdocs.py check")


def cmd_changed(a):
    to = a.to
    by_page, unmapped = moved(lambda sha: git("diff", "--name-only", f"{sha}..{to}").splitlines())
    tip = git("rev-parse", "--short", to)
    if not by_page and not unmapped:
        print(f"Nothing to re-check: every page's stamp covers {to} ({tip}).")
        return 0
    print(f"Code changed under these pages since their stamp (up to {to} = {tip}):\n")
    report(by_page, unmapped)
    return 1


def cmd_gate(a):
    """Git hook entry (pre-merge-commit): refuse a merge into a protected branch while the
    merged code is ahead of the architecture docs. Compares each stamp with the INDEX, i.e.
    exactly what the merge commit will contain, so commits on either side are covered."""
    branch = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], capture_output=True,
                            text=True, cwd=ROOT).stdout.strip()
    if branch not in a.branches:
        return 0
    if os.environ.get("ARCHDOCS_SKIP") == "1":
        print("archdocs gate: skipped (ARCHDOCS_SKIP=1). The architecture docs may now be behind main.",
              file=sys.stderr)
        return 0
    by_page, unmapped = moved(lambda sha: git("diff", "--cached", "--name-only", sha).splitlines())
    problems, out = [], []
    if by_page or unmapped:
        problems.append("code ahead of its page")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report(by_page, unmapped)
        out.append(buf.getvalue())
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_check(a)
    if rc:
        problems.append("site check failed")
        out.append(buf.getvalue())
    if not problems:
        return 0
    print(f"\narchdocs gate: merge into '{branch}' refused - documentation/architecture is behind the "
          f"code ({', '.join(problems)}).\n", file=sys.stderr)
    print("".join(out), file=sys.stderr)
    print("Fix it on the branch you are merging (documentation/architecture/pages/maintaining.html),\n"
          "then merge again. Owner override for one merge: ARCHDOCS_SKIP=1 git merge ...",
          file=sys.stderr)
    return 1


def cmd_stamp(a):
    sha = git("rev-parse", "--short", a.ref)
    today = datetime.date.today().isoformat()
    targets = a.pages or pages()
    for page in targets:
        page = page if page == "index.html" or page.startswith("pages/") else "pages/" + page
        s = read(page)
        new, n = STAMP_RE.subn(lambda m: f"{m.group(1)}commit {sha} · {today}{m.group(4)}", s)
        if n != 1:
            print(f"{page}: expected one verified-at meta, found {n}", file=sys.stderr)
            return 1
        with open(os.path.join(DOCS, page), "w", encoding="utf-8") as fh:
            fh.write(new)
        print(f"{page}: commit {sha} · {today}")
    return 0


class Scan(html.parser.HTMLParser):
    VOID = {"meta", "link", "br", "img", "input", "hr", "source", "wbr", "col", "area", "base",
            "path", "rect", "circle", "line", "polyline", "polygon", "ellipse", "stop", "use"}

    def __init__(self):
        super().__init__()
        self.ids, self.hrefs, self.srcs, self.stack, self.errors = set(), [], [], [], []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if "id" in d:
            if d["id"] in self.ids:
                self.errors.append(f"duplicate id {d['id']!r}")
            self.ids.add(d["id"])
        if tag == "a" and d.get("href"):
            self.hrefs.append(d["href"])
        if tag in ("script", "link", "img") and (d.get("src") or d.get("href")):
            self.srcs.append(d.get("src") or d.get("href"))
        if tag == "style":
            self.errors.append("<style> block (use assets/arch.css)")
        if tag not in self.VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        before = len(self.stack)
        self.handle_starttag(tag, attrs)
        if len(self.stack) > before:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            want = self.stack[-1] if self.stack else None
            self.errors.append(f"line {self.getpos()[0]}: </{tag}> but open is {want}")
            # recover: pop to the matching tag if present
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break
            return
        self.stack.pop()


def cmd_check(a):
    problems = []
    nav = open(os.path.join(DOCS, "assets", "nav.js"), encoding="utf-8").read()
    in_nav = set(re.findall(r'\["((?:pages/)?[\w-]+\.html)"', nav))
    have = set(pages())
    for p in sorted(in_nav - have):
        problems.append(f"nav.js lists {p}, which does not exist")
    for p in sorted(have - in_nav):
        problems.append(f"{p} is not in nav.js PAGES")
    scans = {}
    for page in sorted(have):
        sc = Scan()
        sc.feed(read(page))
        scans[page] = sc
        for e in sc.errors:
            problems.append(f"{page}: {e}")
        if sc.stack:
            problems.append(f"{page}: unclosed {sc.stack[-3:]}")
        if not stamp_of(page)[0]:
            problems.append(f"{page}: no verified-at meta")
        for s in sc.srcs:
            if re.match(r"(https?:)?//", s):
                problems.append(f"{page}: external resource {s}")
    for page, sc in scans.items():
        base = os.path.dirname(page)
        for h in sc.hrefs:
            if re.match(r"(https?:|mailto:)", h):
                continue
            path, _, frag = h.partition("#")
            target = os.path.normpath(os.path.join(base, path)) if path else page
            if path and (not path.endswith(".html") or target.startswith("..")):
                # a file outside the site (e.g. documentation/designs/) or not a page: must exist
                if not os.path.exists(os.path.join(DOCS, target)):
                    problems.append(f"{page}: link to missing {h}")
                continue
            if target not in scans:
                problems.append(f"{page}: link to missing page {h}")
            elif frag and frag not in scans[target].ids:
                problems.append(f"{page}: link to missing anchor {h}")
    stamps = {p: stamp_of(p)[0] for p in have}
    if len(set(stamps.values())) > 1:
        print("note: pages carry different stamps: " + ", ".join(f"{p}={s}" for p, s in sorted(stamps.items())))
    for pr in problems:
        print(pr)
    print(f"{len(have)} pages, {len(problems)} problem(s)")
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("changed")
    c.add_argument("--to", default="HEAD")
    s = sub.add_parser("stamp")
    s.add_argument("pages", nargs="*")
    s.add_argument("--ref", default="HEAD")
    sub.add_parser("check")
    g = sub.add_parser("gate")
    g.add_argument("--branches", nargs="*", default=["main"])
    a = ap.parse_args()
    return {"changed": cmd_changed, "stamp": cmd_stamp, "check": cmd_check, "gate": cmd_gate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
