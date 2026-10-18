# Contract: Guide generation pipeline (feature 015)

Package `backend/app/services/guide_pipeline/` (plain async functions — no ADK agent, no
coaching tools; research R3). Entry point replaces `services/guide._run_spec_guide`:

```python
async def run_guide_generation(class_name: str, spec: str, content_type: ContentType) -> RunOutcome
```

Runs under the existing generation semaphore (`wcl_guide_max_concurrency`) and
`background_lane()` for every WCL call. Every stage is a pure-ish function with a typed
input/output so it is unit-testable with fakes.

## Stages

| # | Stage | Function | Input → Output | Model / tools |
|---|---|---|---|---|
| 1 | Briefing | `build_briefing` | roster, `current_patch()`, `current_mplus_season()`, version source, hotfix source → `GenerationBriefing` | none. **Live patch unknown ⇒ stop: `failed`, `failure_reason="patch_unknown"`** (FR-006) |
| 2 | Data sheet | `build_data_sheet` | briefing → `DataSheet` (cached, `spec_datasheet`) | WCL only (research R5/R6) |
| 3 | Research | `build_fact_sheet` | briefing, data sheet ability names, open inaccuracy reports → `FactSheet` | two calls (research R3): (a) `wcl_guide_model` with `google_search` + `url_context` (allowlisted domains only, research R14) → cited text; (b) tool-less extraction, `response_schema = list[EvidenceItem]`; then **code** hard filters + tiering + ranking (FR-040/041) |
| 4 | Author | `author_claims` | briefing, data sheet, fact sheet → `list[GuideClaim]` | `wcl_guide_model`, **no tools**, `response_schema` = claims list; prompt forbids facts not in the sheets |
| 5 | Checks | `run_checks` | claims, brief, data sheet, fact sheet, briefing → `list[CheckFailure]` | none (deterministic, FR-036) |
| 6 | Review | `review_claims` | briefing, sheets, claims → verdicts + `list[ReviewIssue]` | `wcl_guide_review_model` (stronger, different), no tools, structured output |
| 7 | Revise | `revise_claims` | claims + verdicts/issues/check failures → claims | `wcl_guide_model`, no tools; contradicted → corrected from cited evidence, unconfirmed → removed |
| 8 | Render | `build_brief`, `render_brief_text`, `render_guide_markdown` | confirmed claims → `CoachingBrief`, text, markdown | none (code templates) |
| 9 | Persist | `publish` / `hold_for_review` / `fail` | → DB row + loader cache invalidation | none |

Loop: stages 5–7 repeat; a **round** = checks + review (+ revise when anything failed).
`MAX_REVIEW_ROUNDS = 3` (FR-047). Outcome:
- no check failures and every remaining claim `confirmed` → **publish** (`ready`);
- after round 3 still failing → **needs_review** (`draft` + `review_issues`);
- model/WCL errors → **failed** (retryable), published version untouched.
After a successful review, removed claims' topics are added to `brief.unconfirmed`.

Brief over budget after rendering → the revise step is told to cut lowest-confidence items
(counts as a check failure in that round); never truncated.

## Prompts (all in `guide_pipeline/prompts.py`; no `{}`-sensitive templating issues — these are
plain `str.format` with escaped braces, not ADK instructions)

- **Research**: role "evidence collector, not author"; given the briefing (date, live
  patch/build, hotfix time, content type, season, class spec list), the data-sheet ability
  names, and the trusted-site list; must return evidence items with the URL, page date,
  product/environment/patch it applies to, a ≤300-char paraphrase; never quote > 25 words;
  must mark PTR/beta/Classic/older-patch material instead of dropping it silently (code drops
  it, so leakage is auditable). Open inaccuracy reports are listed as "claims to verify".
- **Author**: "write claims only from the evidence ids below; every claim cites ≥1 id; ability
  ids only from the data sheet; observed facts are worded as observed with scope; omit what
  you cannot support and list it as unconfirmed; content type X only". Output schema enforces
  `log_check` on mistakes/uptimes/cooldowns/benchmarks.
- **Reviewer**: "you are verifying, not writing; judge each claim only against the cited
  evidence text and data-sheet values shown; your own game knowledge is not evidence";
  structured verdicts with the evidence ids used; also judges open inaccuracy reports
  (`fixed`/`rejected` + reason).

## Deterministic checks (`run_checks`, FR-036)

| Check | Rule |
|---|---|
| `ability_unknown` | brief cooldown/uptime/benchmark names must match a data-sheet ability (name casefold or id); skipped (not failed) when the data sheet is insufficient, but then the item is `confidence=low` |
| `cooldown_mismatch` | `cooldown_s` vs data-sheet `min_gap_s`: fail when `min_gap_s < 0.8 × cooldown_s` (cast faster than the stated CD) or, for abilities used ≥ 3×/fight, `min_gap_s > 2.5 × cooldown_s`; charges > 1 relax the lower bound |
| `patch_mismatch` / `season_mismatch` | brief patch == `briefing.live_patch`; mplus season == `briefing.mplus_season` |
| `source_env` | every cited `src:*` item has product retail, environment live, compatible patch, matching content type |
| `source_prehotfix` | cited item date < `latest_hotfix_at` for this class/spec and not flagged → fail |
| `claim_unreferenced` | every claim has ≥1 resolvable evidence ref |
| `log_check_missing` | required `log_check` present with a known signal |
| `brief_too_long` | `len(render_brief_text) ≤ BRIEF_MAX_CHARS` |
| `guide_extra_claim` | markdown is rendered from claims only (structural guarantee); check asserts every rendered bullet maps to a claim id |

## Staleness & regeneration (FR-050/051)

`maybe_scan_stale_guides()` — throttled in-process to once per 10 min, called from
`GET /api/guides`, the chat preamble builder and startup (all non-blocking via `spawn`):
1. Read live patch, Mythic+ season, latest hotfix (cached sources).
2. For each published row: set `stale_reason` = `patch_changed` (patch < live),
   `season_changed` (mplus, season ≠ live), `hotfix` (hotfix_at > generated_at and the hotfix
   touches the class, or touches "all classes"), keep `legacy`.
3. For stale rows with `last_wanted_at` within 14 days → `ensure_guide(..., force=True)`.
   Others regenerate on next open/request.
Cross-instance safety comes from the existing `pending` dedup in `ensure_guide` (atomic
upsert + unique constraint); no extra lock.

`last_wanted_at` is stamped (≤ once/hour/row) when: the viewer opens the guide; a
character's spec resolves to it (`run_character_guide`); the preamble injects its brief or the
tool returns it.

## Character save (FR-030)

`run_character_guide` resolves spec as today, then: `ensure_guide(cls, spec, "raid")`; and
`ensure_guide(cls, spec, "mplus")` when `get_character_zone_rankings(zone_id=<M+ zone>)`
returns ≥1 ranked run this season (cached call, background lane).

## Config (`backend/app/config.py`, env-overridable)

| Setting | Default | Purpose |
|---|---|---|
| `wcl_guide_model` | `gemini-3.7-flash` (existing) | research, author, revise |
| `wcl_guide_review_model` | `gemini-3.1-pro-preview` | reviewer (must differ from author; startup warns if equal) |
| `wcl_guide_max_review_rounds` | 3 | FR-047 |
| `wcl_guide_brief_max_chars` | 6000 | FR-010 |
| `wcl_guide_preamble_briefs_max_chars` | 12000 | FR-013 |
| `wcl_guide_datasheet_min_sample` | 20 | FR-033 (research R6) |
| `wcl_guide_inuse_days` | 14 | FR-051 |
| `wcl_guide_report_per_minute` | 5 | report rate limit |
| `wcl_guide_research_fetch_enabled` | `false` | allow `url_context` on third-party allowlisted domains (Icy Veins/Archon/Murlok) — enable after the maintainer terms review (research R14); Blizzard pages always allowed |
| `wcl_guide_talent_names_url` | `""` | optional talent-entry → name JSON (Raidbots `talents.json`), off until terms checked (research R5) |
| `wow_version_url` | `https://us.version.battle.net/v2/products/wow/versions` | live build source (research R1) |
| `wow_news_url` | `https://worldofwarcraft.blizzard.com/en-us/news` | hotfix article discovery (research R2) |

## Briefing sources (stage 1)

| Field | Source | Failure behaviour |
|---|---|---|
| `live_build`, `live_patch` | version endpoint, product `wow`, row `us` (`live_version` cache) | last cached value → WCL partition `major.minor` → **postpone** if both unknown |
| `raid_tier` | newest non-frozen Heroic zone name (`patch.py`) | `None` (raid guide still generated; header omits tier) |
| `mplus_season` | newest non-frozen zone with difficulty 10 → name (`current_mplus_season`) | mplus generation **postponed** (`failure_reason="season_unknown"`) |
| `latest_hotfix_at`, `hotfix_touches_spec` | `hotfix_feed` (Blizzard news → newest "Hotfixes:" article, JSON-LD + Classes block parse) | `None` / `False`; `source_prehotfix` check skipped |
| roster, class specs | `roster_snapshot()` | fallback roster |

## Data-sheet queries (stage 2, research R5/R6)

1. `characterRankings(className, specName, metric, difficulty, partition, leaderboard: LogsOnly, includeCombatantInfo: true, page: 1)` for ≤4 encounters (raid: Mythic → Heroic fallback; mplus: `metric: playerscore`) — talents, gear, report refs.
2. Casts table by source (`REPORT_PLAYER` cache) for 20 players → cpm + ability ids (`reduce_casts_entry`).
3. `events(dataType: Casts, sourceID)` for 5 players → min gaps of major-cooldown candidates.
4. Buffs/Debuffs tables by source for the same 20 → uptimes.
5. `playerDetails(includeCombatantInfo: true)` for 10 players → stats.
All in `background_lane()`; cohort halved when `budget_size()` is low; result cached 12 h.
