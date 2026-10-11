# Research: Grounded, Evidence-Based Coaching

**Feature**: 009-grounded-coaching-prompt · **Date**: 2026-10-07
**Grounding**: `documentation/designs/20261007_prompt_upgrade.md`

All facts marked **(probed)** were verified against the live Warcraft Logs v2 API on
2026-10-07 (zone 53 "The Venomous Abyss", encounter 3470, Heroic Fire Mage).

---

## R1. How to locate the 75th–95th percentile band for a benchmark cohort

**Decision**: Read the player's own fight with `report.rankings` to get the population
size `totalParses` (N), the player's `rankPercent`/`bracketPercent`, fight `duration`,
`kill`, `partition`, and `bracketData`. Map the band to leaderboard ranks
`ceil(0.05·N)…floor(0.25·N)` → `characterRankings` pages `ceil(rank/100)`. Fetch at most
**3** pages centred on the ~85th-percentile rank, **filter locally** (duration ±15%,
excluding the player's own character), and keep the `size` (default 5) closest by
duration.

**Facts (probed)**:
- `characterRankings` JSON: `{page, hasMorePages, count, rankings[]}` — `count` is the
  page length (100), **not** the population.
- Each ranking entry has `name, class, spec, amount, duration (ms), startTime,
  report{code, fightID, startTime}, bracketData (item level), server, guild, size`.
  No percentile per entry.
- **Hard cap: `page` ≤ 20** ("The maximum page value supported by the API is 20") →
  only the top 2,000 are reachable.
- `report.rankings(fightIDs, compare, timeframe, playerMetric)` per character returns
  `rank, best, totalParses, rankPercent, bracketPercent, bracket, bracketData, amount`,
  and per fight `partition, zone, encounter, difficulty, kill, duration, deaths`.
  `totalParses` differs by `compare` (Rankings 2159 vs Parses 1864 in the probe).
- `characterRankings(filter: "duration.<minS>.<maxS>")` works server-side (seconds).

**Rationale**: `totalParses` is the only way to know where a percentile sits on the
leaderboard. Local filtering keeps rank positions meaningful (a server-side
duration filter would re-rank against a different population). Three pages × 100
entries comfortably yields ≥3 duration matches in practice.

**Band clipping**: when `ceil(0.05·N)/100 > 20` (N > ~40,000) the band is unreachable;
use pages 18–20 and report `band_clipped: true` with the approximate percentile range
actually sampled (`100 − 100·rank/N`). Disclosed as an unmet criterion.

**Alternatives considered**:
- *Server-side duration filter* — rejected: ranks then refer to a filtered population,
  so the band can't be located.
- *Verify each candidate's percentile via its own `report.rankings`* — rejected: +1 call
  per candidate for marginal accuracy.
- *Single top parse (status quo)* — rejected by spec FR-016.

## R2. Wipe pulls

**Decision**: `characterRankings` contains kills only. For a wipe, the benchmark tool
returns `status: "limited"` with `reason: "wipe — no ranked population"`; the
assistant may still describe the pull but must label any comparison as limited
(spec US2 scenario 5). No phase-matched wipe cohort in this feature (YAGNI).

## R3. Which measures to compare

**Decision**: Per cohort member, one `report.table(dataType: Casts, fightIDs:[f])` call
(no source filter; select the entry by character name). It yields per-ability cast
totals, `activeTime`, and `itemLevel` for the member, and the player's own row comes
from the same call shape. Compare **casts per minute per ability** plus throughput
(`amount`). Report median and min–max for each.

**Rate basis (analysis I1)**: cohort members' rates use their fight duration (ranked
kills; deaths are rare and not fetched to save budget). The **player's** rates use
**time alive** — fight duration minus dead windows from R5 (Deaths table + one
next-cast event per death) — and the result carries `dead_s` and `rate_basis`. Without
this, a player who died at 60% shows ~40% lower rates and the benchmark reproduces
the false criticism the feature exists to remove. Cost: +1 call (Deaths) + 1 per death.
Throughput (`amount`) is shown as recorded, with the death stated beside it.

**Facts (probed)**: `Casts` table entries include `name, id, type, icon ("Mage-Fire"),
itemLevel, total, activeTime, abilities[{guid, name, total}]`. An unfiltered Casts
table is ~160 KB (exceeds the existing 60 KB `_cap`), filtered by source ~12 KB.

**Rationale**: one bounded call per member; the heavy payload is reduced in code and
never sent to the model (doc: "deterministic calculations should happen in code").
Buff uptime and damage breakdown comparisons are deferred (the existing table tool
still answers them per player).

**Alternatives**: DamageDone + Buffs per member (3× calls) — rejected for budget.

## R4. Request budget

**Facts (probed)**: `rateLimitData.limitPerHour = 720` points; the whole research probe
used ~85 points.

**Decision**: A benchmark costs ≤ 1 (player rankings) + ≤ 3 (leaderboard pages) + 1
(player Casts) + `size` (member Casts) ≈ **10 calls at size 5**, all through the
existing cached client (report TTL 24h, leaderboard TTL 1h). Before fetching members,
read `rateLimitData`; if remaining points < 100, shrink `size` to 3; if < 40, to 1 and
label anecdotal (FR-017). Hard cap `size ≤ 5`.

## R5. Active (eligible) time and intermissions

**Decision**: `eligible_time = fight duration − dead intervals − intermission
intervals` (overlaps merged), computed in code. The interval maths and the
dead-window fetch live in one shared module, `wcl_agent/fight_time.py`, created with
US2 (which needs time alive, R3) and reused by US4 (Constitution I). "Eligible time"
is deliberately not WCL's `activeTime` (time spent casting — a performance measure).

**Facts (probed)**:
- `ReportFight` has `startTime, endTime, kill, phaseTransitions{id, startTime},
  lastPhaseIsIntermission`.
- `Report.phases[]{encounterID, separatesWipes, phases[{id, name, isIntermission}]}`
  labels intermission phases per encounter (e.g. "Intermission: The Shattering").
- `Deaths` table entries: `{name, id, type, icon, timestamp (report-relative ms), …}`.
- `Resurrections` is **not** a valid `TableDataType` **nor** `EventDataType` (probed enum
  values: Tables — Summary, Buffs, Casts, DamageDone, DamageTaken, Deaths, Debuffs,
  Dispels, Healing, Interrupts, Resources, Summons, Survivability, Threat; Events — the
  same minus Summary/Survivability plus All, CombatantInfo). The existing whitelists
  wrongly accept it → always errors.

**Dead interval**: from each death timestamp to the player's **first cast after that
death** (`events(dataType: Casts, sourceID, startTime: death_ts, limit: 1)`, one call
per death), else fight end. A battle-resurrected player acts again, so their next cast
bounds the dead window; no resurrection event type is needed.
**Intermission interval**: from a `phaseTransitions` entry whose phase id is marked
`isIntermission` to the next transition (or fight end).
**Target immunity outside intermissions**: not detectable from these fields → stated as
an unknown in the result (`excluded_windows_unknown: ["target immunity outside
intermissions"]`), satisfying spec US4 scenario 2's "or states it could not be excluded".

## R6. Opportunity formula

**Decision**: `opportunities ≈ 1 + floor(eligible_s / cooldown_s) + (charges − 1)`,
always reported as approximate (`~N`). The leading `1` counts the use available at
pull; the doc's bare `floor(eligible/cd)` under-counts (263 s fight, 120 s CD → uses at
0/120/240 = 3, not 2).

## R7. Source of ability cooldowns (clarified: the spec guide)

**Decision**: Guide generation emits, in addition to the markdown, a machine-readable
metadata block parsed into a typed model: `{patch, major_cooldowns[{name, spell_id?,
cooldown_s, charges, talent_modified}]}`. Stored on the `spec_guides` row. Matching to
log casts: `spell_id` == ability `guid` first, else case-insensitive name equality.

**Delivery of guide data to the WCL tool layer**: a tiny in-process registry in
`wcl_agent` (`guide_meta.py`: `set_guide_meta`, `get_guide_meta`) that the backend
fills at startup (load all ready guides, ~40 rows) and after each successful guide
generation. Tools read it synchronously from their worker thread.

**Rationale**: `wcl_agent` must not import the backend (dependency direction is
backend → wcl_agent). The app is single-process (no Redis per project guidance), so an
in-process registry is the simplest correct transport. The CLI (no backend) simply has
an empty registry → tools fall back to rate-only comparison (FR-025).

**Alternatives considered**:
- *Model passes cooldowns as tool args* — rejected: un-sourced numbers would enter the
  "deterministic" calculation.
- *Tool queries the DB* — rejected: async DB from sync worker threads + reverse
  dependency.
- *Backend-registered extra tool* — rejected: second tool-construction path (DRY).

## R8. Determining the current patch

**Decision**: `current_patch()` = `name` of the default partition of the newest
non-frozen zone offering Heroic (difficulty 4) — i.e. the current raid. Probed value:
`"12.1"` (zone 53). Mythic+ zones are excluded naturally (no Heroic difficulty; their
partition is named "Season 2"). Reuses the cached `MENU_DISCOVERY` query.

**Freshness rule** (`guide_freshness(guide_patch, current_patch)`):
- either missing or not parseable as `major.minor[.patch]` → `unknown`
- guide `major.minor` < current `major.minor` → `possibly_stale`
- otherwise → `current`

**Alternatives**: age threshold (e.g. 30 days) — rejected as primary rule (patches,
not days, invalidate advice); web lookup — rejected (not available for Claude models).

## R9. Capturing guide sources

**Decision**: `_generate_text` already consumes `stream_response`, which emits a
`{"type": "grounding", "sources": [{title, uri}]}` record when web search is used.
Collect those as the guide's `sources` (deterministic, not model-claimed). Models
without web search → `sources = []` and the guide's patch is still model-stated, so
freshness relies on the stated patch.

## R10. Metadata block format from the guide model

**Decision**: The guide prompt asks the model to end its answer with one fenced block
labelled `guide-meta` containing JSON. The backend extracts the last such block,
validates it with a Pydantic model, strips it from the stored markdown, and stores the
fields.

**Repair turn (analysis C1)**: if the block is missing or fails validation, send **one**
follow-up turn on the *same* disposable session ("Reply with only the `guide-meta`
block for the guide above") and parse that reply. It reuses the context already in the
session, so it costs one short turn rather than a full regeneration. If the repair also
fails → guide is still `ready`; `game_patch = null` (→ `unknown` freshness) and
`major_cooldowns = null` (→ rate-only coaching). This keeps SC-010 meaningful without
making guide availability depend on metadata.

**Alternatives**: second structured-output model call to extract metadata —
rejected (extra cost/latency, a second generation path).

## R11. Provenance & completeness envelope on tool results

**Decision**: Add two **additive** keys to WCL tool results: `provenance`
(report_code, fight_id, encounter_id, difficulty, partition, metric, source_id,
compare, timeframe, fetched_at — only the keys that apply) and `completeness`
(`has_more`, `truncated`, `sample_size`, `sample_scope`). Built by one shared helper
used by every tool. Existing keys are unchanged.

**Why additive**: backend services consume tool results by tool name and key
(`services/encounters.py`, `tool_summary.py`, `raids.py`, known-entity capture);
GitNexus impact on `_cap` is CRITICAL (10 direct callers, 8 processes), so its output
shape must not change — the envelope is added beside it.

## R12. Percentile context

**Decision**: `get_report_rankings` gains `compare` (`Rankings` | `Parses`, default
`Rankings`) and `timeframe` (`Historical` | `Today`, default `Historical`) parameters,
echoed in `provenance`. `get_rankings_distribution` adds `completeness.sample_scope =
"top_of_leaderboard"` when `more_pages_available`. The prompt requires showing overall
and bracket percentiles together and stating the scope.

## R13. Prompt structure and model compatibility

**Decision**: Rewrite `INSTRUCTION` into tagged sections adapted from the doc
(`EVIDENCE_CONTRACT`, `SOURCE_AUTHORITY`, `TOOLS`, `CONTEXT_RESOLUTION`,
`VALIDATION_BEFORE_ANALYSIS`, `ANALYSIS_ROUTING`, `BENCHMARK_POLICY`,
`COACHING_POLICY`, `PERCENTILE_POLICY`, `TOOL_FAILURES`, `CITATIONS`, `CHARTS`,
`KNOWN_PLAYER_CONTEXT`, `OUTPUT`, `PERSONALITY`). Tag-delimited sections work for both
Gemini and Claude. Keep: source-link rules, known-player context, Heroic default,
parallel calls, charts, web-search optionality. `OUTPUT` structure applies only to
analytical questions (not greetings, guide documents, or summaries — the same agent
generates those).

**Persona ordering**: a single model pass cannot literally "render afterwards", so the
prompt instructs: decide facts, confidence and fixes first; then voice them; banter
may not add, remove or soften any of them; ≤1 joke per section.

## R15. Guide generation under the new evidence contract (analysis C2)

**Risk**: guides are generated by the same agent and instruction as chat. The new
`<EVIDENCE_CONTRACT>` ("never invent guide advice", abstain when evidence is
insufficient) could make the generator hedge, refuse to list cooldowns, or produce a
thin guide.

**Decision**: the guide request is an explicit *authoring* task, and the instruction
is written so the contract governs claims about logged fights, not requested
documents:
- `<OUTPUT>` (contracts/prompt.md row 15) already exempts guide documents from the
  verdict format; `<EVIDENCE_CONTRACT>` adds: "When the user asks you to *write* a
  class/spec guide, you may use general class knowledge and web sources; state the
  patch it targets and cite sources when web search is available."
- `_GUIDE_PROMPT` states the same permission and requires the patch, the major
  cooldowns with numbers, and the `guide-meta` block.
- Verified by a content check (≥3 major cooldowns with numeric cooldowns, a patch
  stated) on a regenerated guide during US5 verification, and by the existing
  guide/greeting tests.

**Alternative**: a separate guide-writer agent without the coaching instruction —
rejected: a second agent/runner path (Constitution I) for a wording problem.

## R14. Incidental defects found (fixed in scope, they block grounding)

- `TABLE_DATA_TYPES` and `EVENT_DATA_TYPES` include `Resurrections` (invalid for both)
  → remove; add the valid `Summons` to tables. Whitelists then match the probed enums.
- Unfiltered tables exceed `_cap` and return a truncated preview the model cannot
  flag → now surfaced as `completeness.truncated: true` (R11).
