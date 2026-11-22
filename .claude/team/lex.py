#!/usr/bin/env python3
"""The team lexicon (P18): short names the team agrees on, kept alive by use.

Agent-facing. The lexicon is `.claude/team/lexicon.jsonl` in git (one entry per line), in
three families: places (@sprint ...), status lines (TESTS, SEV ...) and concept terms
(hand-off, D18 ...). `member.py me` prints the core, so every seat starts with it.

  lex.py core                         the always-loaded core (what member.py me prints)
  lex.py show [TERM ...] [--all]      full entries; no TERM: list every term by tier
  lex.py propose TERM --family place|status|concept --means "..." --as NAME
          [--form "..."] [--example "..."] [--expands PATH] [--match REGEX] [--missed REGEX]
          [--saves N] [--distinct "why it differs from the near term"]
                                      add a proposed term (not in core until team-lead promotes it)
  lex.py usage [--since SPRINT] [--json]
                                      uses per term, long-form misses, adoption, value
  lex.py budget                       core size against its cap, weakest core terms first
  lex.py expand TEXT [--wt dev-a] [--sprint DATE]
                                      @places -> absolute paths (for a tool call)
  lex.py plain FILE ...               owner-facing check: lexicon-only terms left in the text
  lex.py promote TERM [--to core|extended]     (team-lead, at wrap-up)
  lex.py retire TERM --reason "..."            (team-lead, at wrap-up)
  lex.py lint                         validate the file

Rules: use the lexicon with team agents that ran member.py (seats). Write plain words for the
owner and for agents that never see it (QA, Explore, general-purpose sub-agents). Name
concepts, never abbreviate letters: "QA sec rvw @ HO" is 11 tokens, "D18 review" is 4.
Missing a term? Propose it; the dedupe check tells you if one already covers it.
"""
import argparse
import datetime
import difflib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(HERE, "lexicon.jsonl")
FAMILIES = ("place", "status", "concept")
TIERS = ("core", "extended", "proposed", "retired")
CORE_CAP = 1000         # tokens of the printed core (every seat re-reads it on every call); a new core term must fit or beat the weakest
NEAR = 0.89             # SEMANTIC_SIMILARITY at which a proposal is "near" a term (calibrated 2026-11-22: dups >= 0.90, distinct <= 0.88)
LEX_CPT = 2.35          # the core itself (forms full of < | @), measured 2026-11-22
COUNT_MODEL = "claude-opus-5-5"


def load():
    if not os.path.exists(FILE):
        return []
    return [json.loads(l) for l in open(FILE) if l.strip()]


def save(entries):
    with open(FILE, "w") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def find(entries, term):
    for e in entries:
        if e["term"].lower() == term.lower():
            return e
    sys.exit(f"lex: no term {term!r} (lex.py show lists them)")


def core_tokens(text):
    """(tokens, how): exact via the free count_tokens endpoint when a key is at hand, else estimated."""
    try:
        import anthropic
        _load_env(("ANTHROPIC_API_KEY",))
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("no key")
        c = anthropic.Anthropic()
        n = lambda t: c.messages.count_tokens(model=COUNT_MODEL, messages=[{"role": "user", "content": t}]).input_tokens
        return n("x" + text) - n("x"), "exact"
    except Exception:
        return round(len(text) / LEX_CPT), "estimated"


# ---------------------------------------------------------------- core

def render_core(entries):
    core = [e for e in entries if e.get("tier") == "core"]
    out = ["Team lexicon (core; full entries: lex.py show TERM). Use it with seats; write plain words "
           "for the owner and for QA/Explore/general-purpose sub-agents. Missing a term: lex.py propose."]
    places = [e for e in core if e["family"] == "place"]
    if places:
        out.append("Places (expand to absolute paths in tool calls, or lex.py expand):")
        for e in places:
            path = e["expands"]
            for other in places:  # show nested places relative to an earlier one: @sprint/qa-reports/...
                if other is not e and path.startswith(other["expands"] + "/"):
                    path = other["term"] + path[len(other["expands"]):]
            out.append(f"  {e['term']} = {path}: {e['means']}")
    status = [e for e in core if e["family"] == "status"]
    if status:
        out.append("Status lines (one per line, this exact shape):")
        for e in status:
            out.append(f"  {e['form']}  {e['means']}")
    concepts = [e for e in core if e["family"] == "concept"]
    if concepts:
        out.append("Terms:")
        for e in concepts:
            out.append(f"  {e['term']}: {e['means']}")
    return "\n".join(out)


def cmd_core(a):
    print(render_core(load()))


def cmd_show(a):
    entries = load()
    if a.terms:
        for t in a.terms:
            print(json.dumps(find(entries, t), indent=1, ensure_ascii=False))
        return
    for tier in TIERS:
        rows = [e for e in entries if e.get("tier") == tier]
        if not rows or (tier == "retired" and not a.all):
            continue
        print(f"{tier} ({len(rows)}):")
        for e in rows:
            head = e.get("form") or e["term"]
            print(f"  [{e['family']}] {head}: {e['means']}" + (f"  (retired: {e.get('retired_reason')})" if tier == "retired" else ""))


# ---------------------------------------------------------------- propose (with the dedupe check)

def entry_text(e):
    return f"{e['term']}: {e.get('form', '')} {e['means']}".strip()


def nearest(text, entries):
    """[(similarity, term)] best first, by embeddings when available, else by string ratio."""
    live = [e for e in entries if e.get("tier") != "retired"]
    if not live:
        return [], "none"
    try:
        sys.path.insert(0, HERE)
        import asyncio
        import numpy as np
        import lexharvest
        _load_gcp_env()
        texts = [text] + [entry_text(e) for e in live]
        v = asyncio.run(lexharvest.embed_all(texts, task="SEMANTIC_SIMILARITY"))
        sims = v[1:] @ v[0]
        order = np.argsort(-sims)
        return [(float(sims[i]), live[i]["term"]) for i in order[:3]], "embeddings"
    except Exception as exc:  # no credentials or network: fall back, say so
        print(f"lex: embeddings unavailable ({type(exc).__name__}); using string similarity", file=sys.stderr)
        rows = sorted(((difflib.SequenceMatcher(None, text.lower(), entry_text(e).lower()).ratio(), e["term"])
                       for e in live), reverse=True)
        return rows[:3], "string"


def _load_gcp_env():
    _load_env(("GOOGLE_",))


def _load_env(prefixes):
    """Only the named settings from the main checkout's .env, never printed."""
    if all(any(k.startswith(p) for k in os.environ) for p in prefixes):
        return
    top = subprocess.run(["git", "-C", HERE, "worktree", "list", "--porcelain"], capture_output=True, text=True).stdout
    main = top.split("\n", 1)[0].removeprefix("worktree ").strip()
    env = os.path.join(main, ".env")
    if os.path.exists(env):
        for line in open(env):
            m = re.match(r"\s*([A-Z_]+)=(.*)", line)
            if m and m.group(1).startswith(prefixes):
                os.environ.setdefault(m.group(1), m.group(2).strip().strip('"'))


def cmd_propose(a):
    entries = load()
    if any(e["term"].lower() == a.term.lower() for e in entries):
        sys.exit(f"lex: {a.term!r} exists (lex.py show {a.term})")
    if a.family == "place" and not a.expands:
        sys.exit("lex: a place needs --expands PATH")
    if a.family == "status" and not a.form:
        sys.exit("lex: a status line needs --form \"WORD <slot> ...\"")
    if a.family == "concept" and re.fullmatch(r"[A-Za-z]{2,4}", a.term):
        print("lex: note: invented letter abbreviations tokenize badly and get misread; prefer a word or an ID", file=sys.stderr)
    new = dict(term=a.term, family=a.family, means=a.means, tier="proposed", coined_by=a.as_,
               coined=datetime.date.today().isoformat(), match=a.match or re.escape(a.term),
               saves=a.saves, plain_ok=False)
    for k in ("form", "example", "expands", "missed"):
        if getattr(a, k):
            new[k] = getattr(a, k)
    try:
        re.compile(new["match"])
        if new.get("missed"):
            re.compile(new["missed"])
    except re.error as exc:
        sys.exit(f"lex: bad regex: {exc}")
    if new.get("example") and not re.search(new["match"], new["example"]):
        sys.exit("lex: --example doesn't match --match; fix one of them so usage counting works")
    near, how = nearest(entry_text(new), entries)
    limit = NEAR if how == "embeddings" else 0.6
    close = [(s, t) for s, t in near if s >= limit]
    if close and not a.distinct:
        sys.exit("lex: close to existing term(s): " + ", ".join(f"{t} ({s:.2f})" for s, t in close)
                 + f"\n  Use or extend that term, or re-run with --distinct \"why it means something else\" ({how}).")
    if close:
        new["distinct"] = a.distinct
    entries.append(new)
    save(entries)
    print(f"lex: proposed {a.term!r} ({a.family}); nearest: "
          + ", ".join(f"{t} {s:.2f}" for s, t in near) + f" [{how}]. team-lead reviews it at wrap-up.")


# ---------------------------------------------------------------- usage and budget

def usage_rows(entries, since):
    sys.path.insert(0, HERE)
    import lexharvest
    counts = {e["term"]: dict(uses=0, missed=0, sprints={}) for e in entries}
    rx = [(e["term"], re.compile(e["match"]), re.compile(e["missed"]) if e.get("missed") else None) for e in entries]
    for item in lexharvest.items():
        if since and item["sprint"] < since:
            continue
        text = item["text"]
        for term, m, miss in rx:
            n = len(m.findall(text))
            c = counts[term]
            c["uses"] += n
            if n:
                c["sprints"][item["sprint"]] = c["sprints"].get(item["sprint"], 0) + n
            if miss:
                c["missed"] += len(miss.findall(text))
    rows = []
    for e in entries:
        c = counts[e["term"]]
        total = c["uses"] + c["missed"]
        rows.append(dict(term=e["term"], tier=e.get("tier"), family=e["family"], uses=c["uses"], missed=c["missed"],
                         adoption=round(c["uses"] / total, 2) if total else None,
                         value=c["uses"] * e.get("saves", 0), potential=c["missed"] * e.get("saves", 0),
                         sprints=c["sprints"]))
    return rows


def cmd_usage(a):
    rows = usage_rows(load(), a.since)
    if a.json:
        print(json.dumps(rows, indent=1))
        return
    print(f"{'term':<14}{'tier':<10}{'uses':>6}{'missed':>8}{'adopt':>7}{'value':>8}{'potential':>10}")
    for r in sorted(rows, key=lambda r: (TIERS.index(r["tier"]), -r["value"] - r["potential"])):
        ad = "-" if r["adoption"] is None else f"{r['adoption']:.2f}"
        print(f"{r['term']:<14}{r['tier']:<10}{r['uses']:>6}{r['missed']:>8}{ad:>7}{r['value']:>8}{r['potential']:>10}")
    print("value = uses x saves (est. tokens); potential = long-form misses x saves; adoption = uses / (uses + misses)")


def cmd_budget(a):
    entries = load()
    size, how = core_tokens(render_core(entries))
    print(f"core: {sum(e.get('tier') == 'core' for e in entries)} terms, {size} tokens ({how}) of {CORE_CAP} cap"
          + ("  OVER CAP: demote or retire the weakest" if size > CORE_CAP else ""))
    print(f"  every seat re-reads it on every call: ~{size} x calls per sprint in cache reads")
    if a.no_usage:
        return
    rows = [r for r in usage_rows(entries, a.since) if r["tier"] == "core"]
    print("weakest core terms (value + potential, since " + (a.since or "the start") + "):")
    for r in sorted(rows, key=lambda r: r["value"] + r["potential"])[:6]:
        print(f"  {r['term']:<14} value {r['value']:>6}  potential {r['potential']:>6}  uses {r['uses']}")


# ---------------------------------------------------------------- expand and plain

def cmd_expand(a):
    entries = [e for e in load() if e["family"] == "place" and e.get("tier") != "retired"]
    sprint = a.sprint or _latest_sprint()
    text = a.text
    for e in sorted(entries, key=lambda e: -len(e["term"])):
        path = e["expands"].replace("<sprint>", sprint or "<sprint>")
        if e["term"] == "@wt":
            if not a.wt and "@wt" in text:
                sys.exit("lex: @wt needs --wt dev-a|dev-b|...")
            path = path.replace("<dev-a|dev-b|...>", a.wt or "")
        text = re.sub(re.escape(e["term"]) + r"\b", path, text)
    print(text)


def _latest_sprint():
    for e in load():
        if e["term"] == "@sprint":
            d = os.path.join(e["expands"], "sprints")
            if os.path.isdir(d):
                names = sorted(n for n in os.listdir(d) if re.match(r"\d{4}-\d{2}-\d{2}", n))
                return names[-1] if names else None
    return None


def cmd_plain(a):
    entries = [e for e in load() if not e.get("plain_ok") and e.get("tier") in ("core", "extended")]
    bad = 0
    for path in a.files:
        text = re.sub(r"<[^>]+>", " ", open(path).read()) if path.endswith(".html") else open(path).read()
        for e in entries:
            for m in re.finditer(e["match"], text):
                if text[max(0, m.start() - 1):m.start()] == "(":  # "the security review (D18)": an id in brackets is fine (pref 23)
                    continue
                line = text.count("\n", 0, m.start()) + 1
                print(f"{path}:{line}: lexicon term {e['term']!r} in owner-facing text: say it in plain words")
                bad += 1
    if bad:
        sys.exit(1)
    print("lex: plain: no lexicon-only terms")


# ---------------------------------------------------------------- curation

def cmd_promote(a):
    entries = load()
    e = find(entries, a.term)
    e["tier"] = a.to
    e["promoted"] = datetime.date.today().isoformat()
    save(entries)
    print(f"lex: {e['term']} -> {a.to}")
    if a.to == "core":
        size, _ = core_tokens(render_core(entries))
        if size > CORE_CAP:
            print(f"lex: core is now {size} tokens, over the {CORE_CAP} cap: demote the weakest (lex.py budget)")


def cmd_retire(a):
    entries = load()
    e = find(entries, a.term)
    e["tier"] = "retired"
    e["retired"] = datetime.date.today().isoformat()
    e["retired_reason"] = a.reason
    save(entries)
    print(f"lex: retired {e['term']}")


def cmd_lint(a):
    entries, errs, seen = load(), [], set()
    for i, e in enumerate(entries, 1):
        for k in ("term", "family", "means", "tier", "match"):
            if not e.get(k):
                errs.append(f"line {i}: missing {k}")
        if e.get("family") not in FAMILIES:
            errs.append(f"line {i}: family {e.get('family')!r}")
        if e.get("tier") not in TIERS:
            errs.append(f"line {i}: tier {e.get('tier')!r}")
        if e.get("family") == "place" and not e.get("expands"):
            errs.append(f"line {i}: place without expands")
        if e.get("family") == "status" and not e.get("form"):
            errs.append(f"line {i}: status line without form")
        key = (e.get("term") or "").lower()
        if key in seen:
            errs.append(f"line {i}: duplicate term {e.get('term')!r}")
        seen.add(key)
        for k in ("match", "missed"):
            if e.get(k):
                try:
                    re.compile(e[k])
                except re.error as exc:
                    errs.append(f"line {i}: {k} regex: {exc}")
        if e.get("example") and e.get("match") and not re.search(e["match"], e["example"]):
            errs.append(f"line {i}: example doesn't match its own match regex")
    size, how = core_tokens(render_core(entries))
    if size > CORE_CAP:
        errs.append(f"core {size} tokens ({how}), over the {CORE_CAP} cap")
    for x in errs:
        print("lex: " + x)
    if errs:
        sys.exit(1)
    print(f"lex: ok ({len(entries)} entries, core {size}/{CORE_CAP} tokens, {how})")


def main():
    p = argparse.ArgumentParser(prog="lex.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("core")
    q = s.add_parser("show")
    q.add_argument("terms", nargs="*")
    q.add_argument("--all", action="store_true")
    q = s.add_parser("propose")
    q.add_argument("term")
    q.add_argument("--family", choices=FAMILIES, required=True)
    q.add_argument("--means", required=True)
    q.add_argument("--as", dest="as_", required=True)
    for k in ("form", "example", "expands", "match", "missed", "distinct"):
        q.add_argument("--" + k)
    q.add_argument("--saves", type=int, default=5)
    q = s.add_parser("usage")
    q.add_argument("--since")
    q.add_argument("--json", action="store_true")
    q = s.add_parser("budget")
    q.add_argument("--since")
    q.add_argument("--no-usage", action="store_true")
    q = s.add_parser("expand")
    q.add_argument("text")
    q.add_argument("--wt")
    q.add_argument("--sprint")
    q = s.add_parser("plain")
    q.add_argument("files", nargs="+")
    q = s.add_parser("promote")
    q.add_argument("term")
    q.add_argument("--to", choices=("core", "extended"), default="core")
    q = s.add_parser("retire")
    q.add_argument("term")
    q.add_argument("--reason", required=True)
    s.add_parser("lint")
    a = p.parse_args()
    globals()["cmd_" + a.cmd](a)


if __name__ == "__main__":
    main()
