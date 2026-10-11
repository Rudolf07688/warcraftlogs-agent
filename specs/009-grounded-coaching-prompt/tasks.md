---

description: "Task list for feature 009 — Grounded, Evidence-Based Coaching"
---

# Tasks: Grounded, Evidence-Based Coaching

**Input**: Design documents from `specs/009-grounded-coaching-prompt/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (prompt.md,
agent-tools.md, rest-guides.md), quickstart.md

**Tests**: Included — plan.md names the offline pytest files per slice. WCL responses are
faked (monkeypatch `wcl_agent.wcl_client.get_client().query` or `requests.post`, as in
`backend/tests/test_wcl_cache.py`); no live API or model calls in tests.

**Organization**: Grouped by user story. Story order follows plan.md's delivery order:
US1 → US2 → US3 → US5 → US4 (US4 consumes guide cooldowns that US5 produces; spec
Assumptions record this).

**Every code task**: before editing a function/class, run GitNexus
`impact({target, direction: "upstream"})` (or `node .gitnexus/run.cjs impact "<symbol>"
--direction upstream --repo .`) and heed HIGH/CRITICAL; before each commit run
`detect_changes({scope: "all"})` (CLAUDE.md, Constitution VI). Changes to existing
tool result shapes are **additive only** (contracts/agent-tools.md).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US5 from spec.md

---

## Phase 1: Setup (Baseline)

**Purpose**: Record the "before" state that SC-011 and SC-012 compare against, while
still on unchanged code.

- [x] T001 Run `uv run --extra test pytest -q` on branch `009-grounded-coaching-prompt` before any code change and note the pass count at the top of `specs/009-grounded-coaching-prompt/review/baseline.md` (create the file and `review/` dir).
- [~] T002 (pulls + questions recorded in review/baseline.md; baseline *answers* need the running app) Pick and record in `specs/009-grounded-coaching-prompt/review/baseline.md` the four reference pulls from quickstart.md Prereqs (one kill, one wipe, one early-death pull, one encounter with an intermission: report code + fight id + player name) and 10 coaching questions over them; ask all 10 against the current app (unchanged prompt) and paste each answer plus its wall-clock time. This is the SC-011/SC-012 baseline.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Provenance/completeness envelope on every WCL tool (FR-020, FR-022) and
the percentile-flattening helper reused by US2 and US3. The US1 prompt's validation
section depends on the envelope existing.

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [x] T003 [P] Create `wcl_agent/provenance.py` with: dataclass `Provenance` (optional `report_code, fight_id, encounter_id, difficulty, partition, metric, source_id, compare, timeframe`; `fetched_at: str` ISO-8601 UTC set via `datetime.now(UTC)`), dataclass `Completeness` (`has_more=False, truncated=False, sample_size: int|None=None, sample_scope: str|None=None`), and `with_envelope(result: dict, provenance: Provenance, completeness: Completeness | None = None) -> dict` that returns `result` unchanged unless `result.get("status") == "success"`, else adds `result["provenance"]` (`asdict` with `None` keys dropped) and `result["completeness"]` (`asdict`; when `completeness` is None, default with `truncated` auto-set True if any top-level value in `result` is a dict containing `"_truncated": True`). Do not modify `_cap`.
- [x] T004 In `wcl_agent/provenance.py` add dataclass `PercentileContext` (data-model §4.2: `name, class_name, spec, role, population ("rankings"|"parses"), timeframe ("historical"|"today"), rank_percent, bracket_percent, bracket, item_level, total_parses, partition, metric, encounter_id, difficulty, fight_id, kill, duration_s, amount`) and `flatten_report_rankings(raw: dict, *, compare: str, timeframe: str, metric: str) -> list[PercentileContext]` that walks the `report.rankings` JSON (`raw["data"][]` → per fight `fightID, partition, encounter.id, difficulty, kill, duration` → `roles.{tanks,healers,dps}.characters[]` → `name, class, spec, rankPercent, bracketPercent, bracket, bracketData, totalParses, amount`) defensively (missing keys → None). Shape verified in research.md R1.
- [x] T005 In `wcl_agent/report_tools.py` fix the whitelists to match the probed API enums (research R5/R14): remove `"Resurrections"` from `TABLE_DATA_TYPES` and `EVENT_DATA_TYPES`; add `"Summons"` to `TABLE_DATA_TYPES` (`GRAPH_DATA_TYPES` follows). Update the `data_type` lists in the `get_report_table`, `get_report_events`, `get_report_graph` docstrings accordingly.
- [x] T006 In `wcl_agent/report_tools.py` wrap every successful return with `with_envelope`: `get_report_fights`, `get_report_master_data`, `get_report_table`, `get_report_events` (`has_more = events.get("nextPageTimestamp") is not None`), `get_report_graph`, `get_report_rankings`, `get_report_player_details`, `get_character_zone_rankings`, `get_character_encounter_rankings` (provenance = the call's identifying args: report_code, fight_id or None when 0, source_id or None when 0, metric where applicable), and `run_wcl_graphql` (provenance `fetched_at` only). Existing keys unchanged; error returns unchanged. (`_report_field`/`_cap` are CRITICAL-impact — do not change their signatures or outputs.)
- [x] T007 In `wcl_agent/tools.py` wrap successful returns of `get_rankings_distribution` (provenance: encounter_id, difficulty, partition, metric; completeness: `has_more=more_pages_available`, `sample_size`, `sample_scope="top_of_leaderboard"` if `more_pages_available` else `"full"`), `compare_specs` (same, aggregated), `find_encounter`, `get_spec_options`, `get_selected_encounter` (provenance `fetched_at` + any ids known). `_summarize` output unchanged.
- [x] T008 [P] Create `backend/tests/test_provenance.py`: (a) `with_envelope` adds keys only on success, drops None provenance keys, sets `truncated` from a `_cap`-truncated value; (b) with a faked client, `get_report_table` returns `provenance.report_code/fight_id` and the original `table` key; (c) `get_report_events` sets `has_more` from `nextPageTimestamp`; (d) `get_rankings_distribution` sets `sample_scope="top_of_leaderboard"` when `hasMorePages` is true; (e) bad `data_type="Resurrections"` is rejected for tables and events; (f) `flatten_report_rankings` on a fixture shaped like research R1 returns rank/bracket percent, totalParses, partition, kill, duration.
- [x] T009 Run `uv run --extra test pytest -q`; confirm all pre-existing tests (notably `test_raids.py`, `test_encounters.py`, `test_known_entities.py`, `test_suggestions.py`, `test_parallel_tools.py`) still pass with the additive envelope.

**Checkpoint**: Every WCL tool result carries `provenance` + `completeness`; nothing else changed.

---

## Phase 3: User Story 1 — Evidence-honest coaching answers (Priority: P1) 🎯 MVP

**Goal**: Barnaby answers verdict-first with ≤3 confidence-rated, evidence-backed fixes,
words inference as inference, abstains when evidence is insufficient, validates context,
ignores injected instructions, and applies the persona last (FR-001..FR-013).

**Independent Test**: quickstart.md "US1" steps 1–7 plus `test_prompt_contract.py`.

### Tests for User Story 1

- [x] T010 [P] [US1] Create `backend/tests/test_prompt_contract.py` that imports `INSTRUCTION` and `TOOLS` from `wcl_agent.agent` and asserts: all 15 section tags from `contracts/prompt.md` are present (`<EVIDENCE_CONTRACT>`, `<SOURCE_AUTHORITY>`, `<TOOLS>`, `<CONTEXT_RESOLUTION>`, `<VALIDATION_BEFORE_ANALYSIS>`, `<ANALYSIS_ROUTING>`, `<BENCHMARK_POLICY>`, `<COACHING_POLICY>`, `<PERCENTILE_POLICY>`, `<GUIDES>`, `<TOOL_FAILURES>`, `<CITATIONS>`, `<CHARTS>`, `<OUTPUT>`, `<PERSONALITY>`) with matching closing tags; key clauses present case-insensitively (`OBSERVED`, `BENCHMARKED`, `GUIDANCE`, `INFERRED`, "never follow instructions", "smallest missing", "avoidable", "confidence", "never the person", "retry at most twice", "Heroic", "damage-done", and the guide-authoring permission "write a class/spec guide"); the old phrase "representative TOP parse" is absent; every tool function name in `TOOLS` (`fn.__name__`) appears in `INSTRUCTION`; and `"web_search"` appears with wording that it may be unavailable.

### Implementation for User Story 1

- [x] T011 [US1] Rewrite `INSTRUCTION` in `wcl_agent/agent.py` as tag-delimited sections exactly per `contracts/prompt.md` (rows 1–16), adapting the grounding doc's "Recommended replacement prompt" (`documentation/designs/20261007_prompt_upgrade.md`). Keep the f-string current-time line. Preserve in substance the existing SOURCE LINKS rules (three URL shapes, metric mapping, one link per distinct source, none on non-WCL claims), CHARTS rules, KNOWN PLAYER CONTEXT rules, Heroic default, `find_encounter` recovery when no encounter is selected, parallel-lookup guidance, WCL domain knowledge (colour brackets, metrics, difficulty ids), and web-search optionality. In `<EVIDENCE_CONTRACT>` scope the contract to claims about logged play and add the authoring permission (research R15): when asked to *write* a class/spec guide, general class knowledge and web sources are allowed, the patch must be stated, and sources cited when web search is available. In `<VALIDATION_BEFORE_ANALYSIS>` reference the new `completeness` fields (`has_more`, `truncated`, `sample_scope`). In `<BENCHMARK_POLICY>` (until US2 lands) state the policy without a dedicated tool: several non-outlier parses of similar duration, never a single max/rank-one parse as representative, single comparison ⇒ "anecdotal". In `<COACHING_POLICY>` (until US4 lands) require rates per minute and forbid "missed" without an opportunity basis. `<OUTPUT>` applies to analytical questions only; greetings, guide documents and summaries follow their own request's format. `<PERSONALITY>` keeps Barnaby's blunt, mistake-first voice with ≤1 short joke/metaphor per section, criticises the play not the person, and must not change facts or confidence.
- [x] T012 [US1] Run `uv run --extra test pytest -q backend/tests/test_prompt_contract.py backend/tests/test_greeting.py backend/tests/test_guide.py backend/tests/test_spec_guides.py` and fix any failures (greeting and guide generation share the agent instruction).
- [~] T013 [US1] (sheet prepared in review/us1.md; needs the running app) Manually run quickstart.md "US1" steps 1–7 against the running app using the reference pulls from `review/baseline.md`; record pass/fail and notable wording in `specs/009-grounded-coaching-prompt/review/us1.md`; tune `INSTRUCTION` wording (not structure) for any failures and re-run T010.

**Checkpoint**: MVP — grounded answer shape and evidence discipline live with existing tools.

---

## Phase 4: User Story 2 — Fair benchmark comparisons (Priority: P2)

**Goal**: `compare_player_to_cohort` returns a matched cohort (≤5 kill parses from the
~75th–95th percentile band, duration ±15%) with medians/ranges, label, and unmet
criteria; budget-bounded (FR-014..FR-017).

**Independent Test**: `test_fight_time.py` + `test_benchmark.py` + quickstart.md "US2" steps 1–6.

### Tests for User Story 2

- [x] T014 [P] [US2] Create `backend/tests/test_benchmark.py` covering the pure helpers of `wcl_agent/benchmark.py`: `band_pages(total_parses)` (N=2159 → pages spanning ranks 108..539 centred on rank ~324, ≤3 pages; N=60000 → pages 18–20 with `clipped=True`; N<100 → page 1); `select_cohort(entries, player_name, player_duration_ms, size)` (±15% window, excludes same name, nearest by |Δduration|, widens to ±25% and reports it when <3 matches); `cohort_label(size, unmet)` (1 → anecdotal, 2 or any unmet → directional, ≥3 and none unmet → matched); `budget_size(requested, remaining_points)` (≥100 → requested≤5, <100 → ≤3, <40 → 1); `reduce_casts_entry(table, name)` (picks entry by name, returns per-ability `{guid, name, total}`; missing → None); `aggregate_measures(player, members, duration_s by member)` (casts/min, median/min/max, `cohort_users`, union of top abilities ≤20). Also create `backend/tests/test_fight_time.py` for the shared helpers in `wcl_agent/fight_time.py`: `merge_intervals` (overlaps/adjacency); `dead_windows(death_ts, next_cast_ts, fight_end)` (no next cast → until fight end); `eligible_seconds`; `resolve_player(actors, fight_player_ids, player_name, source_id)` (source_id wins; one name match → actor; none → error listing names present; two same-name actors → `AmbiguousPlayer` error with `candidates[{source_id, name, server, class}]`). Plus tool-level tests with a faked client: wipe fight → `status == "limited"`; player not in the fight → `error` listing names present; duplicate name without `source_id` → ambiguous error, with `source_id` → success; a player who died at 60% of a 300 s kill → `player.dead_s ≈ 120`, `player.alive_s ≈ 180`, `rate_basis == "alive_time"` and player casts/min computed ÷ 180 s (not 300 s); success result contains `cohort.size`, `cohort.label`, `measures`, `throughput`, `members[].link` of the form `https://www.warcraftlogs.com/reports/<code>#fight=<id>`, and `provenance`/`completeness`.

### Implementation for User Story 2

- [x] T015 [US2] Create `wcl_agent/fight_time.py` (data-model §4.3b; shared with US4) with `resolve_player` (masterData `actors(type: "Player"){id name server subType}` + the fight's `friendlyPlayers`; `source_id` wins; ambiguous → data-model §4.3a error), `merge_intervals`, `dead_windows`, `fetch_dead_windows(report_code, fight_id, source_id, fight_end)` (Deaths table → player's death timestamps; per death one `events(dataType: Casts, sourceID, startTime: <death ts>, limit: 1)` call), `intermission_windows`, `eligible_seconds` — eligible/alive time is never WCL `activeTime`. Then create `wcl_agent/benchmark.py` with the pure helpers tested in T014 and the tool `compare_player_to_cohort(report_code: str, fight_id: int, player_name: str, metric: str = "dps", size: int = 5, source_id: int = 0) -> dict` implementing contracts/agent-tools.md §4 steps 1–6: resolve the player first via `resolve_player`; player row via `report.rankings(fightIDs, playerMetric)` + `flatten_report_rankings` (T004), selected by resolved name + server; player's Casts entry selected by `entry.id == source_id`; player rates ÷ `alive_s` from `fetch_dead_windows` with `dead_s`/`alive_s`/`rate_basis="alive_time"` in the result (FR-015a), member rates ÷ their fight duration; leaderboard pages via the existing `ENCOUNTER_RANKINGS` query in `wcl_agent/queries.py` (same class/spec/metric/difficulty/partition from the player's fight); budget via `rateLimitData` (reuse `wcl_client.check_rate_limit`); Casts tables via the existing `_report_field` (unfiltered by source, pick by name — payload is reduced in code, never returned raw); result shape per data-model §4.3, built from dataclasses + `asdict`, wrapped with `with_envelope`. Validate `metric` against `wcl_agent.constants.METRICS`; clamp `size` to 1..5. Write the model-facing docstring stated in the contract (use for "how do I compare / why is my parse low"; do not use leaderboard `top_parses` as a benchmark).
- [x] T016 [US2] Register `compare_player_to_cohort` in `TOOLS` in `wcl_agent/agent.py` (benchmark group) and update `INSTRUCTION`: list it under `<TOOLS>`; in `<BENCHMARK_POLICY>` require it for player comparisons, require reporting cohort size, label and unmet criteria, wipes ⇒ limited, rank-one only when the user asks about elite play (call it an outlier); when the player died, present the death (with `dead_s`) as the finding rather than the alive-time rates; on an ambiguous-name error, use the known server from KNOWN PLAYER CONTEXT to pick `source_id` or ask the user which candidate. Extend `backend/tests/test_prompt_contract.py` to assert `compare_player_to_cohort` is in `<BENCHMARK_POLICY>`.
- [x] T017 [P] [US2] Add a summary branch for `compare_player_to_cohort` in `summarize_tool_result` in `backend/app/services/tool_summary.py` (e.g. "cohort of 5 (matched) — ±15% duration" / "limited: wipe") and a test case in the existing tool-summary tests (or `backend/tests/test_benchmark.py` if none exist).
- [x] T018 [P] [US2] Add `compare_player_to_cohort` to `TOOL_LABELS` in `frontend/src/toolLabels.ts` ("Finding comparable players") and a spell entry in `frontend/src/lib/spells.ts` (reuse an existing imported icon, e.g. `GiCrossedSwords`, hue `GOLD`, verb "Gathering worthy rivals", two flavor lines).
- [~] T019 [US2] (automated part green; manual steps need the running app — see review/us2.md) Run `uv run --extra test pytest -q`, then quickstart.md "US2" steps 1–6 against the running app; record results and WCL points spent per benchmark (`check_rate_limit` before/after) in `specs/009-grounded-coaching-prompt/review/us2.md`.

**Checkpoint**: US1 + US2 work together; comparisons no longer use a single top parse.

---

## Phase 5: User Story 3 — Percentiles and data with explicit context (Priority: P3)

**Goal**: Percentiles carry rankings-vs-parses, timeframe, overall + bracket, partition,
sample size; population stats state their sample scope (FR-018..FR-022).

**Independent Test**: tests below + quickstart.md "US3" steps 1–3.

### Tests for User Story 3

- [x] T020 [P] [US3] Create `backend/tests/test_report_rankings.py`: with a faked client, `get_report_rankings(code, fight, compare="Parses", timeframe="Today")` sends `compare: Parses, timeframe: Today` in the query, keeps the raw `rankings` key, adds `percentiles` (list of `PercentileContext` dicts with `population == "parses"`, `timeframe == "today"`, `rank_percent`, `bracket_percent`, `total_parses`), and echoes `compare`/`timeframe` in `provenance`; invalid `compare`/`timeframe` → `status == "error"` listing valid values; defaults are `Rankings`/`Historical`.

### Implementation for User Story 3

- [x] T021 [US3] Change `get_report_rankings` in `wcl_agent/report_tools.py` to `get_report_rankings(report_code: str, fight_id: int = 0, compare: str = "Rankings", timeframe: str = "Historical") -> dict`: whitelist `{"Rankings","Parses"}` / `{"Historical","Today"}`, inline the validated enums into the `rankings(...)` field call, add `percentiles = [asdict(p) for p in flatten_report_rankings(...)]`, set provenance `compare`/`timeframe`; update the docstring to explain rankings (best per character) vs parses (~2 weeks of pulls) and today vs historical. Keep the `rankings` key unchanged (consumed by `backend/app/services/raids.py` and `tool_summary.py`).
- [x] T022 [US3] Update `<PERCENTILE_POLICY>` in `INSTRUCTION` (`wcl_agent/agent.py`) to reference `get_report_rankings`'s `compare`/`timeframe` parameters and its `percentiles` list, require showing `rank_percent` and `bracket_percent` together when both exist, and stating `sample_scope` for leaderboard statistics; extend `backend/tests/test_prompt_contract.py` to assert `percentiles` and `bracket` appear in `<PERCENTILE_POLICY>`.
- [~] T023 [US3] (automated part green; manual steps need the running app — see review/us3.md) Run `uv run --extra test pytest -q`, then quickstart.md "US3" steps 1–3; record in `specs/009-grounded-coaching-prompt/review/us3.md`.

**Checkpoint**: Percentile claims carry context; partial data is flagged.

---

## Phase 6: User Story 5 — Guide advice with known freshness (Priority: P5)

**Goal**: Guides store patch, generated date, sources, and machine-readable major
cooldowns; freshness is computed at read time and shown in the Class Guides page and
agent context; cooldowns are published to the in-process registry (FR-026..FR-029).
Delivered before US4, which consumes the cooldowns.

**Independent Test**: `test_guide_meta.py` + quickstart.md "US5" steps 1–3.

### Tests for User Story 5

- [x] T024 [P] [US5] Create `backend/tests/test_guide_meta.py`: (a) `guide_freshness` — `("12.1","12.1")→current`, `("12.1.5","12.1")→current`, `("12.0","12.1")→possibly_stale`, `("11.2","12.1")→possibly_stale`, `(None,"12.1")→unknown`, `("12.1",None)→unknown`, `("Season 2","12.1")→unknown`; (b) `current_patch()` with a faked `MENU_DISCOVERY` payload (one M+ zone with partition "Season 2" and no Heroic, one older frozen raid, one newest non-frozen raid with default partition "12.1") returns `"12.1"`; (c) `parse_guide_meta(text)` extracts the last fenced `guide-meta` JSON block, returns `(markdown_without_block, GuideMetaBlock)`; invalid JSON or schema → `(original_text_minus_nothing, None)`; cooldown bounds enforced (cooldown_s 1..600, charges 1..5, ≤15 entries); (d) `set_guide_meta`/`get_guide_meta` round-trip keyed by `(class_name, spec)`; (e) `build_preamble` with a `guide_labels` map renders `## <name> — <spec> (guide for patch 12.1 · current)` and is byte-identical to today when `guide_labels` is empty.

### Implementation for User Story 5

- [x] T025 [P] [US5] Create `wcl_agent/patch.py`: `current_patch() -> str | None` (run `MENU_DISCOVERY` from `wcl_agent/queries.py` through the cached client; pick the non-frozen zone with the highest `id` whose `difficulties` include id 4; return its default partition `name` (via the same logic as `menu._default_partition`, reuse it rather than duplicate); any error → None) and `guide_freshness(guide_patch: str | None, current: str | None) -> Literal["current","possibly_stale","unknown"]` per research R8 (parse `^\d+\.\d+(\.\d+)?$`, compare `(major, minor)`).
- [x] T026 [P] [US5] Create `wcl_agent/guide_meta.py` with frozen dataclasses `GuideCooldown(name, spell_id, cooldown_s, charges, talent_modified)` and `GuideMeta(class_name, spec, game_patch, generated_at, cooldowns: tuple[GuideCooldown, ...])`, a module-level dict guarded by a `threading.Lock`, and `set_guide_meta(meta)`, `get_guide_meta(class_name, spec) -> GuideMeta | None`, `clear_guide_meta()` (tests).
- [x] T027 [US5] Create migration `backend/migrations/versions/0009_spec_guide_provenance.py` (revision id `0009_guide_provenance` — ≤32 chars, `down_revision = "0008_drop_guide_columns"`, follow `0008` file style) adding nullable `game_patch String(20)`, `generated_at DateTime(timezone=True)`, `sources JSON`, `major_cooldowns JSON` to `spec_guides`; downgrade drops them. No backfill.
- [x] T028 [US5] Add the four mapped columns to `SpecGuide` in `backend/app/db/models.py` (all `nullable=True`; use the existing `_JSON` type alias for `sources` and `major_cooldowns`), and extend `upsert_spec_guide` in `backend/app/db/repository.py` with keyword args `game_patch`, `generated_at`, `sources`, `major_cooldowns` (default sentinel = leave unchanged; only stamped when provided, like `guide_markdown`).
- [x] T029 [US5] In `backend/app/schemas.py` add `GuideCooldownIn` and `GuideMetaBlock` (Pydantic, data-model §2 bounds), `GuideSource {title: str|None, uri: str}`, `GuideFreshness = Literal["current","possibly_stale","unknown"]`, and extend `GuideListItem` / `GuideOut` with `game_patch`, `generated_at`, `freshness` (and `GuideOut.sources: list[GuideSource] = []`) per contracts/rest-guides.md.
- [x] T030 [US5] In `backend/app/services/guide.py`: (1) extend `_GUIDE_PROMPT` to frame an authoring task ("you are writing a reference guide; general class knowledge is allowed; use web search for current-patch accuracy when available" — research R15), state the target patch, include a "Major cooldowns" section with numeric cooldowns, and end with exactly one fenced block labelled `guide-meta` containing JSON `{"patch": "<major.minor>", "major_cooldowns": [{"name", "spell_id", "cooldown_s", "charges", "talent_modified"}]}` for the spec's major throughput and defensive cooldowns; (2) change `_generate_text(prompt, session_id=None)` to return a dataclass `GeneratedText(text, sources, session_id)` collecting `record["sources"]` from `type == "grounding"` records and reusing `session_id` when given (CRITICAL impact: update both callers `_run_spec_guide` and `run_guild_summary` in the same change; guild path ignores sources); (3) add `parse_guide_meta(text) -> tuple[str, GuideMetaBlock | None]`; (3b) if the block is missing or invalid, send exactly one repair turn via `_generate_text(_GUIDE_META_REPAIR_PROMPT, session_id=<same session>)` where `_GUIDE_META_REPAIR_PROMPT = "Reply with only the guide-meta block for the guide above."`, and parse that reply (research R10); (4) in `_run_spec_guide` on success persist stripped markdown + `game_patch`, `generated_at=now(UTC)`, `sources`, `major_cooldowns` via `upsert_spec_guide`, then `set_guide_meta(GuideMeta(...))`; (5) add `async load_guide_registry()` that reads all `ready` rows via `repo.list_spec_guides` and calls `set_guide_meta` for each (rows with NULL cooldowns get an empty tuple). Never raise into callers.
- [x] T031 [US5] In `backend/app/main.py` `lifespan`, after the session service is set up, `await load_guide_registry()` wrapped in try/except with a logged warning (startup must not fail if the table is empty or unreachable).
- [x] T032 [US5] In `backend/app/api/guides.py` populate the new fields in `list_guides` (via `build_guide_roster` in `backend/app/services/guide.py` — add `game_patch`, `generated_at`, `freshness` to each item; compute `current_patch()` once per request with `asyncio.to_thread`) and `get_guide` (also `sources`); `freshness` is None unless status is `ready`.
- [x] T033 [US5] Add an optional `guide_labels: dict[tuple[str, str], str] = {}` parameter to `build_preamble` in `backend/app/services/profile_context.py` that appends ` (<label>)` to each `## <name> — <spec>` guide heading when a label exists (unchanged output when absent); in `backend/app/api/ws.py` build labels from `guide_rows` (`guide for patch <p> · current`, `guide for patch <p> · may be out of date`, or `guide patch unknown · may be out of date`) using `guide_freshness(g.game_patch, current_patch())` (call `current_patch` via `asyncio.to_thread`; cached by the WCL client cache).
- [x] T034 [P] [US5] Extend `GuideListItem` and `Guide` in `frontend/src/types.ts` with `game_patch: string | null`, `generated_at: string | null`, `freshness: "current" | "possibly_stale" | "unknown" | null`, and `Guide.sources: { title: string | null; uri: string }[]`.
- [x] T035 [US5] In `frontend/src/components/profile/ClassGuidesTab.tsx` show for `ready` rows a muted "Patch <game_patch>" / "Patch unknown" and the generated date next to the status chip, plus a "May be out of date" badge (new class `guide-badge guide-stale`, styled in the same stylesheet as existing `guide-badge` classes) when `freshness` is `possibly_stale` or `unknown`, beside the existing Refresh action; in the guide view panel header show patch + date and render `sources` as a short list of external links (`target="_blank" rel="noreferrer"`) under the body when non-empty.
- [x] T036 [US5] Update `<GUIDES>` in `INSTRUCTION` (`wcl_agent/agent.py`) to explain the guide heading labels (patch · freshness) and require flagging possibly-stale/unknown guide advice that drives a recommendation; extend `backend/tests/test_prompt_contract.py` accordingly. Extend `backend/tests/test_spec_guides.py` / `backend/tests/test_guide.py` for the new columns, `_generate_text` `GeneratedText` return (update its fakes), stored metadata on success, a missing block triggering exactly one repair turn on the same session (repair succeeds → metadata stored; repair fails → NULL metadata, guide still `ready`), and API `freshness` values.
- [~] T037 [US5] (migration applied, tests + build green; manual steps need the running app — see review/us5.md) Apply the migration (`uv run alembic -c backend/alembic.ini upgrade head`), run `uv run --extra test pytest -q` and `npm run build` in `frontend/`, then quickstart.md "US5" steps 1–3 — including the content check that a regenerated guide (under the new evidence contract) states its patch and lists ≥3 major cooldowns with numeric cooldowns, and that its `major_cooldowns` column is populated; record in `specs/009-grounded-coaching-prompt/review/us5.md`.

**Checkpoint**: Guides carry provenance; the registry holds cooldowns for ready guides.

---

## Phase 7: User Story 4 — Opportunity-based cast coaching (Priority: P4)

**Goal**: `get_cooldown_usage` computes eligible time (minus death and intermission
windows) and "uses of ~N opportunities" from guide cooldowns; falls back to rates
when no cooldown is known; approximate when the guide isn't current (FR-023..FR-025a).

**Independent Test**: `test_cooldowns.py` + quickstart.md "US4" steps 1–4.

### Tests for User Story 4

- [x] T038 [P] [US4] Create `backend/tests/test_cooldowns.py` covering `intermission_windows(fight_start, fight_end, phase_transitions, intermission_phase_ids)` (add to `backend/tests/test_fight_time.py`, since it lives in `wcl_agent/fight_time.py`) and the pure helpers in `wcl_agent/cooldowns.py`: `opportunities(eligible_s, cooldown_s, charges)` (263 s / 120 s / 1 charge → 3; 60 s / 120 s → 1; 2 charges adds 1); `match_uses(cooldowns, abilities)` (spell_id == guid first, then case-insensitive name, unmatched → 0). Tool-level with a faked client and registry: early death shrinks `eligible_s` and opportunities; intermission excluded; no registry entry → `guide.available == False`, `cooldowns == []`, `rates` present; registry entry with `game_patch=None` → every cooldown `freshness_caveat == True`; `time.excluded_windows_unknown` contains "target immunity outside intermissions"; `time.eligible_s` is independent of the Casts entry's `activeTime` (fixture sets a misleading `activeTime`); player missing → `error` naming players present; duplicate name without `source_id` → ambiguous error; `provenance`/`completeness` present.

### Implementation for User Story 4

- [x] T039 [US4] Add `intermission_windows` to `wcl_agent/fight_time.py` and create `wcl_agent/cooldowns.py` with the pure helpers tested in T038 and the tool `get_cooldown_usage(report_code: str, fight_id: int, player_name: str, source_id: int = 0) -> dict` per contracts/agent-tools.md §5: `resolve_player` from `wcl_agent/fight_time.py` first (ambiguity → error); one `_report_field` query for `phases{encounterID phases{id isIntermission}}` + `fights(fightIDs){startTime endTime kill encounterID phaseTransitions{id startTime}}`; `Casts` table for the fight reduced with `reduce_casts_entry` from `wcl_agent/benchmark.py` selecting `entry.id == source_id` (reuse, don't duplicate), class/spec parsed from the entry `icon` (`"Mage-Fire"`); dead windows via `fetch_dead_windows` and eligible time via `eligible_seconds` from `wcl_agent/fight_time.py` (reuse — never WCL `activeTime`); registry via `get_guide_meta`; freshness via `guide_freshness(meta.game_patch, current_patch())`; result per data-model §4.4 from dataclasses + `asdict`, wrapped with `with_envelope`. Docstring as stated in the contract.
- [x] T040 [US4] Register `get_cooldown_usage` in `TOOLS` in `wcl_agent/agent.py` and update `INSTRUCTION`: list it under `<TOOLS>`; in `<COACHING_POLICY>` require calling it before judging cooldown usage, phrase results as "N of ~M opportunities" only when `guide.available`, label counts approximate with a freshness note when `freshness_caveat`, otherwise compare rates to the cohort and never say "missed". Extend `backend/tests/test_prompt_contract.py` to assert `get_cooldown_usage` is in `<COACHING_POLICY>`.
- [x] T041 [P] [US4] Add a summary branch for `get_cooldown_usage` in `backend/app/services/tool_summary.py` (e.g. "3 cooldowns · eligible 4m12s of 4m24s" / "rates only — no guide cooldowns") with a test.
- [x] T042 [P] [US4] Add `get_cooldown_usage` to `TOOL_LABELS` in `frontend/src/toolLabels.ts` ("Checking cooldown usage") and a spell entry in `frontend/src/lib/spells.ts` (existing imported icon, hue `EMBER`, verb "Counting the cooldowns", two flavor lines).
- [~] T043 [US4] (automated part green; manual steps need the running app — see review/us4.md) Run `uv run --extra test pytest -q`, then quickstart.md "US4" steps 1–4 (early-death pull, intermission encounter, a spec without a ready guide, a spec with an unknown-patch guide); record in `specs/009-grounded-coaching-prompt/review/us4.md`.

**Checkpoint**: All five stories functional together.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [~] T044 (sheet prepared in review/sample.md; needs the running app and a human judge) Run the quickstart.md "Review sample" (≥15 questions covering every spec edge-case category, including a run on a Claude model for "no web search") and fill the SC table in `specs/009-grounded-coaching-prompt/review/sample.md`; for SC-011 and SC-012 re-ask the 10 baseline questions from `review/baseline.md` on this branch, compare wall times, and do the blind comparison. Fix any failing criterion (prompt wording or tool output) and re-check it.
- [x] T045 [P] Update `README.md` feature/agent-tool list with `compare_player_to_cohort` and `get_cooldown_usage`, the evidence/abstention behaviour, and guide patch/freshness; note migration `0009` in the setup section.
- [x] T046 [P] Reconcile the `TOOLS` docstring list in `wcl_agent/agent.py` (`_build_web_search_tool` comment says "all 16 WCL function tools") with the new count, and remove any now-unused text from the old prompt.
- [x] T047 Run `node .gitnexus/run.cjs analyze --index-only`, then `detect_changes({scope: "compare", base_ref: "main"})`; confirm affected processes match the plan (tool results additive, guide generation, preamble) and that the result is not partial/truncated before committing.
- [x] T048 Final `uv run --extra test pytest -q` and `npm run build` (in `frontend/`) green; tick `specs/009-grounded-coaching-prompt/checklists/requirements.md` items still relevant.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — must precede any code change (baseline).
- **Foundational (Phase 2)**: after Setup; **blocks all stories**.
- **US1 (Phase 3)**: after Foundational. MVP.
- **US2 (Phase 4)**: after Foundational (uses T003/T004). Touches `INSTRUCTION` after US1 (T016 edits the US1 rewrite) — sequence after T011.
- **US3 (Phase 5)**: after Foundational (uses T004). Prompt edit T022 after T011.
- **US5 (Phase 6)**: after Foundational. Prompt edit T036 after T011. Independent of US2/US3.
- **US4 (Phase 7)**: after US5 (needs `guide_meta.py`, `patch.py`, populated registry) and after US2's T015 (`reduce_casts_entry` and `wcl_agent/fight_time.py`).
- **Polish (Phase 8)**: after all stories.

### Shared-file sequencing

`wcl_agent/agent.py` (`INSTRUCTION`, `TOOLS`) is edited by T011 → T016 → T022 → T036 →
T040 → T046, and `backend/tests/test_prompt_contract.py` by T010 → T016 → T022 → T036 →
T040: never parallel. `wcl_agent/report_tools.py`: T005 → T006 → T021.
`backend/app/services/tool_summary.py`: T017 → T041. `frontend/src/toolLabels.ts`,
`frontend/src/lib/spells.ts`: T018 → T042.

### Within Each User Story

Tests first (they should fail), then implementation, then prompt/registration, then
manual verification recorded under `review/`.

## Parallel Opportunities

- **Phase 2**: T003 → T004 (same new file); T008 test scaffold can start alongside T003; T005 → T006 sequential (same file); T007 parallel to T005/T006.
- **US2**: T014 ‖ (T017, T018 once T015's result shape is fixed).
- **US5**: T024 ‖ T025 ‖ T026 ‖ T034; then T027 → T028 → T029 → T030 → T031/T032/T033; T035 after T034.
- **US4**: T038 ‖ T041 ‖ T042 after T039's shape is fixed.
- **Across stories** (with more than one developer, after Phase 2 and T011): US2, US3 and US5 can proceed in parallel except for their `INSTRUCTION`/`TOOLS` edits, which go one at a time.

### Parallel Example: User Story 5

```text
Task: "T024 [US5] Create backend/tests/test_guide_meta.py"
Task: "T025 [US5] Create wcl_agent/patch.py (current_patch, guide_freshness)"
Task: "T026 [US5] Create wcl_agent/guide_meta.py registry"
Task: "T034 [US5] Extend guide types in frontend/src/types.ts"
```

### Parallel Example: User Story 2

```text
Task: "T014 [US2] Create backend/tests/test_benchmark.py"
# after T015 fixes the result shape:
Task: "T017 [US2] tool_summary branch for compare_player_to_cohort"
Task: "T018 [US2] toolLabels.ts + spells.ts entries"
```

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 baseline → Phase 2 envelope → Phase 3 prompt rewrite.
2. **Stop and validate** with quickstart US1 + `review/us1.md`. This alone delivers the
   evidence contract, abstention, validation, answer shape and persona restraint.

### Incremental Delivery

1. MVP (US1) → 2. US2 fair benchmarks → 3. US3 percentile context → 4. US5 guide
freshness (UI-visible on its own) → 5. US4 opportunity coaching → 6. Review sample.
Each step leaves the app working and is verified before the next (Constitution II).

## Notes

- `[P]` = different files, no dependency on incomplete tasks.
- Commit after each task or logical group, after `detect_changes`.
- The automated evaluation set and analysis trace are out of scope (spec Assumptions).
