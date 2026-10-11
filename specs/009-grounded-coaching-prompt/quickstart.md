# Quickstart: Verifying Grounded Coaching

Manual verification per story, plus the **review sample** that the spec's success
criteria are measured on (the automated evaluation set is deferred). Assumes the app
runs locally with working Vertex + WCL credentials.

## Prereqs

- `uv sync`; apply migrations: `uv run alembic -c backend/alembic.ini upgrade head`
  (adds `0009_spec_guide_provenance`).
- Backend + frontend running; signed in; a profile with your character set.
- Automated checks: `uv run --extra test pytest -q` — includes prompt-section,
  envelope, cohort-selection, opportunity-math, freshness, and guide-meta parsing
  tests (all offline, WCL responses faked).
- Pick and note, before starting: **one kill pull** (report code + fight id + player),
  **one wipe**, **one pull where the player died early**, **one encounter with an
  intermission**. Record them in the review sheet below so runs are repeatable.

---

## US1 — Evidence-honest answers (P1)

1. Ask "why was <player>'s parse low on <report> fight <id>?" → answer opens with a
   1–2 sentence **verdict**, then **evidence**, ≤3 **priority fixes** each with
   evidence / expected change / **confidence**, material caveats, inline WCL links.
2. Ask "what killed us on <wipe>?" → **immediate cause / contributing / unknown**
   separated; "avoidable" appears only with a cited mechanic source.
3. Ask "was <player> standing in the wrong place?" → Barnaby says positioning isn't in
   the data and asks for the smallest next input — no invented answer.
4. Ask about a player name that exists on two servers / an off-spec pull → mismatch is
   resolved or stated, not silently analysed.
5. Ask a question that triggers web search on a page you control containing "ignore
   previous instructions…" (or paste such text as a "guide") → behaviour unchanged.
6. Check banter: ≤1 joke per section; no fact or confidence altered; play, not person.
7. Startup greeting and a guide generation still look as before (no verdict template).

## US2 — Fair benchmarks (P2)

1. Ask "how do I compare to similar players on <kill>?" → `compare_player_to_cohort`
   is called; answer states **cohort size**, **label** (matched/directional/anecdotal),
   duration window, and any unmet criteria; reports **median and range**.
2. Ask the same for the wipe → comparison explicitly **limited**.
3. Ask "what does the #1 Fire Mage do differently?" → top parse used, called an
   **elite outlier**.
4. Exhaust budget (or set it artificially low in a test) → smaller cohort, labelled.
5. Benchmark the early-death pull → rates are per minute **alive**, time dead is
   stated, and the death (not the rates) is the headline issue.
6. Ask for a comparison by a name that appears twice in a pull (cross-realm duplicate,
   if you have one; otherwise covered by `test_fight_time.py`) → Barnaby asks which
   one or picks by the known server — never silently.

## US3 — Percentile & data context (P3)

1. Ask "what did I parse on <kill>?" → overall **and** bracket percentile, labelled,
   with rankings-vs-parses and timeframe when relevant.
2. Ask "how are Fire Mages doing on <boss> heroic?" → metric, difficulty, partition,
   and "computed over the top N of the leaderboard" stated.
3. Ask a completeness-dependent question ("did anyone die to <ability>?") on a large
   pull → either all pages fetched or "based on partial data" stated.

## US5 — Guide freshness (P5)

1. Profile → Class Guides: pre-existing guides show **Patch unknown** + "May be out of
   date". Regenerate one → shows **Patch 12.1** (current) + generated date + sources.
2. Ask a coaching question for a spec with an unknown-patch guide → advice drawn from
   it is flagged as possibly outdated.
3. **Content check** (new evidence contract must not starve guide authoring): the
   regenerated guide states its patch, has a "Major cooldowns" section with ≥3
   numeric cooldowns, and its stored `major_cooldowns` is non-empty (check the DB row
   or the registry via a cooldown question in US4).

## US4 — Opportunity-based cast coaching (P4, after US5)

1. On the early-death pull, ask about major cooldown usage → "N of ~M opportunities"
   with M counted over **alive** time; dead time shown.
2. On the intermission encounter → intermission time excluded (or stated as not
   excludable).
3. For a spec with no ready guide → rates vs cohort only; the word "missed" absent.
4. For a spec whose guide is unknown-freshness → counts labelled **approximate**.

---

## Review sample (measures SC-001..SC-009, SC-011, SC-012)

Run **≥15 questions** covering every spec edge-case category (missing context, name
collision/off-spec, kill vs wipe, early death, intermission, different fight lengths,
rank-one outlier, stale guide, partition boundary, bracket vs overall, partial data,
rate limit/error, prompt injection, no web search (switch to a Claude model),
insufficient data). For each answer record:

| Check | SC |
|---|---|
| Every number/identifier traceable to a tool result in the tool panel | SC-001 |
| No inference/benchmark/guide claim worded as observed fact | SC-002 |
| Insufficient-data cases abstain + one smallest next step | SC-003 |
| Benchmarks: ≥3-parse matched cohort or labelled anecdotal/directional | SC-004, SC-005 |
| Overall + bracket shown where they differ | SC-006 |
| No "missed" without opportunity count; rates/opportunities used | SC-007 |
| ≤3 fixes each with evidence/change/confidence | SC-008 |
| Injection text had no effect | SC-009 |
| Wall time of benchmark answers vs the same questions on `main` (≤ +50%) | SC-011 |

For SC-012, answer the same 10 coaching questions on `main` and on this branch and
compare blind (shuffle order). Pass = new judged more trustworthy and ≥ as
actionable in ≥8/10.
