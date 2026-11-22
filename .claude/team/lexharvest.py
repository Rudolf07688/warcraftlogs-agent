#!/usr/bin/env python3
"""Lexicon harvest: find what the team keeps saying, so we can name it once.

Team-lead helper (meta, P18). Reads what team agents wrote to each other, splits it into
short units, and reports three kinds of candidates for the team lexicon:

  coined   terms the team already invented (D18, tier M, security-core, `fix round` ...)
  phrases  word sequences repeated verbatim across many messages
  clusters the same idea in different words (embeddings + cosine grouping)

  lexharvest.py run OUTDIR [--dsn URL] [--sim 0.93] [--limit N]

Sources: meta/sprints/*/board.jsonl, sprints/*/briefs/*.md, meta/team/*.md, and the agent
transcripts still on disk (assistant text, Agent prompts, SendMessage bodies, Shortcut
comments). Owner-facing chat is left out. Embeddings: Vertex gemini-embedding-001 at 768
dims with task CLUSTERING (the app's GCP config from .env), cached by text hash under
~/.cache/wcl-team/ so a rerun costs nothing. With --dsn the units and vectors also land in
a pgvector table `lex_unit` (start one with `pg.py up lexicon --no-init`), for ad-hoc
nearest-neighbour queries later. Token counts are estimates (chars / CHARS_PER_TOKEN).
"""
import argparse
import asyncio
import collections
import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRANSCRIPTS = os.path.expanduser("~/.claude/projects/-home-rudolf-dev-warcraftlogs-agent")
CACHE = os.path.expanduser("~/.cache/wcl-team/lex-embed.sqlite")
MODEL, DIMS = "gemini-embedding-001", 768
CHARS_PER_TOKEN = 3.3  # prose, measured with count_tokens 2026-11-22; paths are about 1.7
MIN_WORDS, MAX_WORDS = 5, 70

# ---------------------------------------------------------------- corpus

SPRINTS = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "meta/sprints/*")))


def sprint_of(ts):
    """The latest sprint label whose date is on or before an ISO timestamp."""
    day = (ts or "")[:10]
    best = None
    for s in SPRINTS:
        if s[:10] <= day:
            best = s
    return best or "pre"


def items():
    """Yield dicts: source, role, author, sprint, text (one message / brief / memory)."""
    for path in sorted(glob.glob(os.path.join(ROOT, "meta/sprints/*/board.jsonl"))):
        sprint = path.split(os.sep)[-2]
        for line in open(path):
            d = json.loads(line)
            author = d.get("author", "?")
            role = "team-lead" if author == "team-lead" else "seat"
            yield dict(source="board", role=role, author=author, sprint=sprint, text=d.get("text", ""))
    for path in sorted(glob.glob(os.path.join(ROOT, "sprints/*/briefs/*.md"))):
        sprint = path.split(os.sep)[-3]
        yield dict(source="brief", role="product-owner", author="po", sprint=sprint, text=open(path).read())
    for path in sorted(glob.glob(os.path.join(ROOT, "meta/team/*.md"))):
        seat = os.path.basename(path)[:-3]
        yield dict(source="memory", role=seat, author=seat, sprint="now", text=open(path).read())
    yield from transcript_items()


def transcript_items():
    for meta in sorted(glob.glob(os.path.join(TRANSCRIPTS, "*/subagents/*.meta.json"))):
        m = json.load(open(meta))
        role = m.get("agentType", "?")
        if re.match(r"dev-[ab]-", role):
            role = "developer"
        author = m.get("description", role)
        f = meta[: -len(".meta.json")] + ".jsonl"
        if os.path.exists(f):
            yield from _assistant_blocks(f, role, author, text_too=True)
    for f in sorted(glob.glob(os.path.join(TRANSCRIPTS, "*.jsonl"))):
        # main sessions: only what team-lead sent to agents (chat text is for the owner)
        yield from _assistant_blocks(f, "team-lead", "team-lead", text_too=False)


def _assistant_blocks(path, role, author, text_too):
    for line in open(path):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") != "assistant":
            continue
        sprint = sprint_of(d.get("timestamp"))
        for b in d.get("message", {}).get("content", []) or []:
            t, text, source = b.get("type"), None, None
            if t == "text" and text_too:
                text, source = b.get("text"), "say"
            elif t == "tool_use":
                inp, name = b.get("input") or {}, b.get("name", "")
                if name == "Agent":
                    text, source = inp.get("prompt"), "brief"
                elif name == "SendMessage":
                    msg = inp.get("message")
                    text, source = (msg if isinstance(msg, str) else json.dumps(msg)), "message"
                elif "comment" in name or name.endswith("stories-create") or name.endswith("create_story"):
                    text, source = inp.get("text") or inp.get("description"), "shortcut"
            if text:
                yield dict(source=source, role=role, author=author, sprint=sprint, text=text)


FENCE = re.compile(r"```.*?```", re.S)
SENT = re.compile(r"(?<=[.!?;])\s+(?=[A-Z`(*\"'])")
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'’-]*")


def units(text):
    """Short prose units from a message: no code fences, tables, headings or path soup."""
    text = FENCE.sub(" ", text)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("|", "#", "<", "{", "$ ")):
            continue
        line = re.sub(r"^([-*>]|\d+[.)])\s+", "", line)
        line = re.sub(r"\*\*|__", "", line)
        for s in SENT.split(line):
            s = s.strip()
            words = WORD.findall(s)
            if not (MIN_WORDS <= len(words) <= MAX_WORDS):
                continue
            alpha = sum(c.isalpha() or c == " " for c in s) / max(len(s), 1)
            if alpha < 0.72:
                continue
            yield s


# ---------------------------------------------------------------- coined terms

COINED = [
    ("decision/proposal id", re.compile(r"\b([DP]\d{1,2})\b")),
    ("tier", re.compile(r"\b[Tt]ier ([SML])\b")),
    ("backticked", re.compile(r"`([A-Za-z][A-Za-z0-9 _:-]{2,28})`")),
    ("compound", re.compile(r"\b([a-z]{3,}(?:-[a-z]{2,}){1,2})\b")),
]
STOP_COMPOUNDS = set("""follow-up end-to-end read-only long-term short-term real-time well-known
one-off built-in up-to-date day-to-day so-called self-contained re-run re-runs""".split())


def looks_code(term):
    return bool(re.search(r"[/.()=]|_[a-z]|\.py|^[a-z_]+\(|^--", term)) or term.isupper() and len(term) > 4


def coined_terms(rows):
    hits = collections.defaultdict(lambda: dict(n=0, roles=set(), sprints=set(), kind=""))
    for r in rows:
        seen = set()
        for kind, rx in COINED:
            for m in rx.finditer(r["text"]):
                term = m.group(0) if kind == "tier" else m.group(1)
                if kind == "tier":
                    term = "tier " + m.group(1)
                if kind == "backticked" and looks_code(term):
                    continue
                if kind == "compound" and term in STOP_COMPOUNDS:
                    continue
                key = term.lower() if kind != "decision/proposal id" else term
                if key in seen:
                    continue
                seen.add(key)
                h = hits[key]
                h["n"] += 1
                h["roles"].add(r["role"])
                h["sprints"].add(r["sprint"])
                h["kind"] = h["kind"] or kind
    out = []
    for term, h in hits.items():
        if h["n"] >= 8 and len(h["roles"]) >= 2:
            out.append(dict(term=term, kind=h["kind"], uses=h["n"], roles=sorted(h["roles"]),
                            sprints=len(h["sprints"])))
    out.sort(key=lambda x: (-len(x["roles"]), -x["uses"]))
    return out


# ---------------------------------------------------------------- repeated phrases

def phrases(rows, nmin=4, nmax=9, min_docs=6):
    df = collections.Counter()
    roles = collections.defaultdict(set)
    for r in rows:
        words = [w.lower() for w in WORD.findall(FENCE.sub(" ", r["text"]))]
        grams = set()
        for n in range(nmin, nmax + 1):
            for i in range(len(words) - n + 1):
                grams.add(" ".join(words[i:i + n]))
        for g in grams:
            df[g] += 1
            roles[g].add(r["role"])
    cands = [(g, c) for g, c in df.items() if c >= min_docs and len(roles[g]) >= 2]
    # drop a gram when a longer gram containing it has at least 80% of its count
    cands.sort(key=lambda x: -len(x[0]))
    kept = []
    for g, c in cands:
        if any(g in k and kc >= 0.8 * c for k, kc in kept):
            continue
        kept.append((g, c))
    out = []
    for g, c in kept:
        words = g.split()
        if sum(w in FUNCTION for w in words) >= len(words) - 1:
            continue
        tok = len(g) / CHARS_PER_TOKEN
        out.append(dict(phrase=g, docs=c, roles=sorted(roles[g]), est_tokens=round(tok, 1),
                        est_saving=round(c * max(tok - 2, 0))))
    out.sort(key=lambda x: -x["est_saving"])
    return out


FUNCTION = set("""a an the and or but if of to in on at for with by from as is are was were be been it
its this that these those there here not no do does did have has had will would can could should
may might must i we you he she they them our your their my me us so than then when which who what
how all any each more most other some such only own same too very just one two also into over""".split())


# ---------------------------------------------------------------- embeddings

def cache_db():
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    db = sqlite3.connect(CACHE)
    db.execute("create table if not exists e (h text primary key, v blob)")
    return db


def h(text, task="CLUSTERING"):
    return hashlib.sha256(f"{MODEL}:{DIMS}:{task}:{text}".encode()).hexdigest()


async def embed_all(texts, task="CLUSTERING"):
    from google import genai
    from google.genai import types

    db = cache_db()
    have = {}
    for i in range(0, len(texts), 900):
        chunk = [h(t, task) for t in texts[i:i + 900]]
        q = "select h, v from e where h in (%s)" % ",".join("?" * len(chunk))
        have.update({k: v for k, v in db.execute(q, chunk)})
    todo = [t for t in texts if h(t, task) not in have]
    print(f"embed: {len(texts)} units, {len(texts) - len(todo)} cached, {len(todo)} to embed", file=sys.stderr)
    if todo:
        client = genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"], location="europe-west1")
        cfg = types.EmbedContentConfig(task_type=task, output_dimensionality=DIMS, auto_truncate=True)
        sem = asyncio.Semaphore(6)
        batches = [todo[i:i + 40] for i in range(0, len(todo), 40)]
        done = [0]

        async def one(batch):
            async with sem:
                for attempt in range(6):
                    try:
                        r = await client.aio.models.embed_content(model=MODEL, contents=batch, config=cfg)
                        break
                    except Exception as exc:  # rate limits: back off and retry
                        if attempt == 5:
                            raise
                        await asyncio.sleep(2 ** attempt + 1)
                        print(f"embed: retry {attempt + 1} ({str(exc)[:80]})", file=sys.stderr)
                rows = [(h(t, task), np.asarray(e.values, dtype=np.float32).tobytes()) for t, e in zip(batch, r.embeddings)]
                db.executemany("insert or replace into e values (?, ?)", rows)
                db.commit()
                have.update(dict(rows))
                done[0] += 1
                if done[0] % 25 == 0:
                    print(f"embed: {done[0]}/{len(batches)} batches", file=sys.stderr)

        await asyncio.gather(*(one(b) for b in batches))
    v = np.stack([np.frombuffer(have[h(t, task)], dtype=np.float32) for t in texts])
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def cluster(v, sim, block=2048):
    """Leader clustering: repeatedly take the unit with the most unassigned neighbours."""
    n = len(v)
    nbrs = []
    for i in range(0, n, block):
        s = v[i:i + block] @ v.T
        for row in s:
            nbrs.append(np.nonzero(row >= sim)[0])
    assigned = np.zeros(n, bool)
    degree = np.array([len(x) for x in nbrs])
    order = np.argsort(-degree)
    groups = []
    for i in order:
        if assigned[i] or degree[i] < 2:
            continue
        members = [j for j in nbrs[i] if not assigned[j]]
        if len(members) < 3:
            continue
        assigned[members] = True
        groups.append((int(i), [int(j) for j in members]))
    return groups


async def to_pg(dsn, uniq, meta, v):
    import asyncpg

    con = await asyncpg.connect(dsn)
    await con.execute("create extension if not exists vector")
    await con.execute("""create table if not exists lex_unit (
        id int primary key, text text not null, uses int not null, roles text[] not null,
        sources text[] not null, sprints text[] not null, embedding vector(768) not null)""")
    await con.execute("truncate lex_unit")
    rows = [(i, t, meta[t]["uses"], sorted(meta[t]["roles"]), sorted(meta[t]["sources"]),
             sorted(meta[t]["sprints"]), "[" + ",".join(f"{x:.6f}" for x in v[i]) + "]")
            for i, t in enumerate(uniq)]
    await con.executemany("insert into lex_unit values ($1,$2,$3,$4,$5,$6,$7::vector)", rows)
    await con.execute("create index if not exists lex_unit_hnsw on lex_unit using hnsw (embedding vector_cosine_ops)")
    await con.close()


# ---------------------------------------------------------------- run

def run(a):
    t0 = time.time()
    rows = list(items())
    print(f"corpus: {len(rows)} items, {sum(len(r['text']) for r in rows) / 1e6:.2f} M chars", file=sys.stderr)
    by_source = collections.Counter(r["source"] for r in rows)
    meta = collections.defaultdict(lambda: dict(uses=0, roles=set(), sources=set(), sprints=set()))
    for r in rows:
        for u in units(r["text"]):
            m = meta[u]
            m["uses"] += 1
            m["roles"].add(r["role"])
            m["sources"].add(r["source"])
            m["sprints"].add(r["sprint"])
    uniq = sorted(meta, key=lambda t: -meta[t]["uses"])
    if a.limit:
        uniq = uniq[: a.limit]
    print(f"units: {sum(m['uses'] for m in meta.values())} total, {len(uniq)} distinct", file=sys.stderr)

    coined = coined_terms(rows)
    phr = phrases(rows)
    v = asyncio.run(embed_all(uniq))
    groups = cluster(v, a.sim)
    clusters = []
    for leader, members in groups:
        uses = sum(meta[uniq[j]]["uses"] for j in members)
        roles = set().union(*(meta[uniq[j]]["roles"] for j in members))
        sprints = set().union(*(meta[uniq[j]]["sprints"] for j in members))
        toks = float(np.median([len(uniq[j]) for j in members])) / CHARS_PER_TOKEN
        # leader first, then the most-used variants, then the most different ones
        sims = v[members] @ v[leader]
        variants = sorted(members, key=lambda j: -meta[uniq[j]]["uses"])[:4]
        far = [members[k] for k in np.argsort(sims)[:3]]
        examples = list(dict.fromkeys([leader] + variants + far))[:7]
        clusters.append(dict(size=len(members), uses=uses, roles=sorted(roles), sprints=len(sprints),
                             median_tokens=round(toks, 1), est_saving=round(uses * max(toks - 3, 0)),
                             examples=[dict(text=uniq[j], uses=meta[uniq[j]]["uses"],
                                            sim=round(float(v[j] @ v[leader]), 3)) for j in examples]))
    clusters.sort(key=lambda c: -(c["est_saving"] * min(len(c["roles"]), 4)))
    if a.dsn:
        asyncio.run(to_pg(a.dsn, uniq, meta, v))
        print("pg: lex_unit written", file=sys.stderr)

    os.makedirs(a.outdir, exist_ok=True)
    summary = dict(generated=time.strftime("%Y-%m-%d %H:%M"), model=MODEL, sim=a.sim,
                   items=len(rows), items_by_source=dict(by_source), distinct_units=len(uniq),
                   total_units=sum(meta[t]["uses"] for t in uniq), chars_per_token=CHARS_PER_TOKEN,
                   sprints=SPRINTS, seconds=round(time.time() - t0))
    json.dump(dict(summary=summary, coined=coined, phrases=phr[:300], clusters=clusters[:300]),
              open(os.path.join(a.outdir, "candidates.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))
    print(f"coined {len(coined)}, phrases {len(phr)}, clusters {len(clusters)}")


def main():
    p = argparse.ArgumentParser(prog="lexharvest.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("outdir")
    r.add_argument("--dsn")
    r.add_argument("--sim", type=float, default=0.93)
    r.add_argument("--limit", type=int, default=0)
    a = p.parse_args()
    if a.cmd == "run":
        run(a)


if __name__ == "__main__":
    main()
