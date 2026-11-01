# Eval write-up: embedding model and BM25 (044, sc-115 AC4)

## What was measured, and on which embeddings

`python -m backend.evals.kb run` loads the fixture corpus (15 WCL, 15 guide, 15 chat chunks) and
30 labelled questions into Postgres and runs every question through the real `search` in
three modes. Recall@8 only counts eval sources, in rank order. Latency is one `search` call on
a throwaway `pgvector/pgvector:pg17-trixie` container, on the developer machine.

**Embedding set: `stand-in`** (hashed word and character-trigram features; see
`backend/evals/kb/standin.py`). No real embeddings were recorded in this sprint (CI never calls
Vertex). Real vectors arrive when team-lead runs `record` (below).

| Mode | Recall@8 | p50 | p95 |
|---|---|---|---|
| hybrid | 0.967 | 13.9 ms | 20.8 ms |
| vector-only | 0.917 | 9.3 ms | 10.4 ms |
| keyword-only | 0.983 | 10.5 ms | 18.0 ms |

These numbers prove the harness and the SQL, not a model. The stand-in is itself lexical, so
its "vector" leg behaves like a second keyword leg, and the corpus is small and written with
the words the questions use. Hybrid at or above vector-only is expected here and says nothing
about Gemini. The test asserts "hybrid ≥ vector-only" (SC-004) only when `embeddings.json`
holds a `vertex:` set.

## Recommendation: embedding model

**Keep `gemini-embedding-001` at 768 dimensions (the current default).** There is no eval
evidence for a switch: the default changes only on a clear win in the recorded eval (sprint
rule). `text-embedding-005` is the alternative the design names. It outputs 768 dimensions
natively, so it needs no truncation renormalisation, but it is English-only, and chat text and
character names are not always English. Switching later is a re-embed, not a schema change
(`embed_model` per row).

To decide with data, team-lead runs:

```bash
uv run python -m backend.evals.kb record          # writes embeddings.json, set vertex:<model>
TEST_DATABASE_URL=… uv run --extra test pytest -q -s backend/tests/test_kb_eval.py   # on a fresh DB
```

Repeat with the embedder model switched to `text-embedding-005` to compare. Switch only if its
hybrid recall@8 is clearly higher (≥ 0.05) at similar latency.

## Recommendation: true BM25

**Not now.** Postgres `ts_rank_cd` with OR-ed lexemes is the keyword leg. On the fixture set it
is the strongest single leg, and RRF uses only ranks, so the missing BM25 term weighting
matters less than it would in a score-blended setup. The keyword side has two known weak spots,
both fixable without an extension:

- WCL text uses the `simple` config (no stemming), so "deaths" doesn't match "died".
- English stopwords are dropped from WCL queries by a dictionary lookup (P7 SEC-001), but
  `simple` keeps them in the indexed text.

Revisit when the recorded eval or live use shows keyword ranking as the weak leg. Candidates
(licences to re-check before adopting; each needs an extension build or a different image):

| Option | Licence | Note |
|---|---|---|
| Timescale `pg_textsearch` | PostgreSQL licence | first choice if needed: licence fits |
| ParadeDB `pg_search` | AGPL-3.0 | copyleft: avoid for a hosted app |
| VectorChord-bm25 | AGPL-3.0 / ELv2 | copyleft or source-available |

## Live mode (team-lead)

`uv run python -m backend.evals.kb live --max-questions 30` (cheapest chat model,
`ModelRole.FAST` unless `--model`) asks each question twice: with the search-first clause and
without it. It reports `local_answer_rate` (turns with no Warcraft Logs tool call),
`search_rate` and `filter_accuracy` (the first `search_knowledge` call's filters against the
labels, compared through the resolver). That is 60 turns at most, and some may call WCL.
