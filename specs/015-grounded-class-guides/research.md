# Research: Grounded, Patch-Aware Class Guides (feature 015)

Phase 0 decisions. Codebase facts verified 2026-10-18 (file:line refs); external facts list
what was fetched vs inferred.

## R1. Exact live build (FR-007)

- **Decision**:
  - Poll `https://us.version.battle.net/v2/products/wow/versions` through the `live_version`
    cache family (TTL 15 min). It is unauthenticated pipe-separated text.
  - Read the `us` row's `VersionsName` (e.g. `12.1.5.70448`), `BuildId` and the `## seqn`.
  - The briefing carries `live_build = VersionsName` and `live_patch = major.minor.patch`
    (`12.1.5`). When the endpoint fails, use the last cached value, then the WCL raid
    partition name (`12.1`, major.minor only).
  - Freshness comparison stays major.minor (`guide_freshness`). Patch-level changes
    (12.1.5 → 12.1.7) are caught by the stale scan comparing `game_patch` strings exactly.
- **Verified (fetched 2026-10-18)**:
  - Live and PTR values:
    - product `wow` = Retail live `12.1.5.70448`;
    - `wowt` = PTR `12.1.7.70424`;
    - `wowxptr` = second PTR;
    - `wow_beta`, `wow_classic*` and `wow_anniversary` are other products.
  - Same content on `http://us.patch.battle.net:1119/wow/versions`.
  - Headers `cache-control: max-age=1`, with no rate-limit headers and no published terms;
    it is the launcher's undocumented endpoint.
- **Rationale**: The only source of the exact build. Only product `wow` is ever read, so
  PTR builds cannot leak into the briefing. It never blocks generation, because WCL major.minor
  remains the floor, and an unknown WCL patch stops generation (FR-006).
- **Alternatives**: WCL partitions only (major.minor, fails FR-007's "most precise available");
  scraping patch notes (fragile, slower).

## R2. Hotfix detection (FR-035/FR-050, briefing `latest_hotfix_at`)

- **Decision**:
  - The `hotfix_feed` cache family (TTL 30 min) fetches the Blizzard news listing
    `https://worldofwarcraft.blizzard.com/en-us/news` and finds the newest article titled
    `Hotfixes:`.
  - From that article it reads the JSON-LD `dateModified` (falling back to
    `datePublished`) as `latest_hotfix_at`.
  - It parses the body with stdlib `html.parser`: date headings, then a `Classes` block,
    then bold class names, then bold spec names. This yields `entries[{date, class_name,
    specs[]}]`.
  - Class and spec names are mapped to WCL filter values through the roster. A class with
    no spec sub-heading counts as all of its specs. A "General" or "Items" section is
    recorded but does not mark specs stale.
  - If the fetch or parse fails, `latest_hotfix_at = None` and only patch and season
    changes trigger regeneration (spec Assumption).
- **Verified (fetched)**:
  - Article `/en-us/news/24307310/hotfixes-october-16-2026` has JSON-LD
    `datePublished 2026-10-17T01:37:29Z` and `dateModified`, plus a 12.1.5 tag.
  - The nested Classes → class → spec lists are present (e.g. Druid → Guardian /
    Restoration, Oct 14).
  - No official RSS or JSON feed exists (the tried paths return 404).
- **Rejected**:
  - Blizzard forum blue-tracker JSON: forum robots.txt `Disallow: /en/wow/g` covers it.
  - Wowhead news RSS (`/news/rss/retail`, `<category>Live|PTR</category>`): it works, but
    it is a third-party mirror and Wowhead's robots disallow AI crawlers. It is kept only
    as a documented fallback idea, not implemented (YAGNI).
- **Rationale**: This is the official tier-1 source, gives per-spec granularity so only
  touched specs go stale, and the parse uses the stdlib only.

## R3. Pipeline runtime: plain async functions on google-genai, not ADK agents

- **Decision**: The guide pipeline calls `google.genai` `client.aio.models.generate_content`
  directly. It uses `response_schema` (Pydantic) for author, reviewer and reviser, and the
  Gemini built-in tools `google_search` + `url_context` for research only. Calls are wrapped
  in feature 011's `generate_with_retry` (via a small adapter that turns the single call
  into a one-item async generator). The pipeline keeps one process-wide client, the
  `suggestions.py` PERF-005 pattern.
- **Rationale**:
  - Today guides run through the full analyst agent (`stream_response` → `build_agent`,
    services/guide.py:157-177): Barnaby's instruction, about 20 WCL tools and the `web_search`
    sub-agent, which summarises results so the writer sees second-hand text. FR-004 forbids
    exactly that.
  - Structured output makes claims validatable (Constitution IV).
  - Plain functions are the simplest loop (III).
  - ADK 2.10 marks `LoopAgent` / `SequentialAgent` deprecated in favour of Workflow
    (loop_agent.py:72-74, sequential_agent.py:97-99).
  - `agent_runner._runners` caches by model id only (agent_runner.py:49, :67-85), so a second
    ADK agent would need runner and session plumbing, and sessions created there are never
    deleted.
- **Alternatives**:
  - A second ADK `Agent` with `output_schema`: works (llm_agent.py:451-464) but adds
    sessions and runner keys for no benefit.
  - ADK `url_context` tool: Gemini-only (url_context_tool.py:62-64); the genai built-in is
    the same capability without ADK.
  - `load_web_page`: needs bs4/lxml, which are not installed.
  - ADK `Workflow` (the 2.x replacement, with routed writer → critic edges): a graph runtime
    for a 3-iteration loop is more machinery than a `for` loop.
- **Structured output with built-in tools is preview (Gemini 3 only)** per the Gemini docs.
  Research therefore makes **two calls**:
  1. A grounded collection call (`google_search` + `url_context`, free text with sources).
  2. A tool-less extraction call with `response_schema = list[EvidenceItem]` over that text
     and the grounding metadata.
  Author, reviewer and reviser are tool-less structured calls.

## R4. Live `<CURRENT_TIME>` (FR-001)

- **Decision**: Build `Agent(instruction=build_instruction)`, where
  `build_instruction(ctx: ReadonlyContext) -> str` returns the static body with
  `<CURRENT_TIME>` set to `datetime.now(UTC)` (formatted `%Y-%m-%d %H:%M UTC`). The static
  body stays brace-free.
- **Rationale**:
  - ADK 2.10 supports `InstructionProvider = Callable[[ReadonlyContext], str | Awaitable[str]]`
    (llm_agent.py:321; `_instructions_utils.py:39-41`).
  - `canonical_instruction` calls the provider per request and bypasses state injection
    (llm_agent.py:813-831), so the time is correct on every model call however long the
    process runs.
  - Today's f-string (agent.py:64-72) is evaluated once at import.
- **Alternatives**:
  - Inject the time through the preamble: the preamble is profile-only and empty for users
    without a profile.
  - `static_instruction` + dynamic `instruction`: moves the instruction into user content,
    which changes prompt caching behaviour for no gain.
- **Test change**: `test_time_line_is_live` (test_prompt_contract.py:165-167) calls the
  provider under two frozen clocks. `test_no_template_braces` targets the static body.

## R5. Data sheet sources in Warcraft Logs (FR-032)

- **Decision**: The data sheet uses WCL only:
  1. **Rankings with builds**:
     - `worldData.encounter(id).characterRankings(className, specName, metric,
       difficulty, partition, leaderboard: LogsOnly, includeCombatantInfo: true, page: 1)`
       for the current tier's encounters.
     - Raid: zone 53-style raid zone, Mythic difficulty (5), falling back to Heroic (4)
       when the Mythic sample is under the minimum; `metric` = `dps`/`hps`/`bossdps` by
       role (benchmark.py's metric choice).
     - Mythic+: the M+ zone's dungeon encounters, `metric: playerscore`, keystone level
       from `bracketData`.
     - Each entry carries `talents[{talentID, points}]`, `gear[]` (ilvl/enchants/gems),
       `report{code, fightID}` and `bracketData`.
     - `leaderboard: LogsOnly` is mandatory: without it the top entries can be Blizzard
       leaderboard rows with no report, no talents and "Unknown Item" gear (verified).
  2. **Casts per player**: for a capped cohort (R6), the `Casts` table filtered by source
     through the cached `REPORT_PLAYER` family, reduced by `benchmark.reduce_casts_entry`.
     This gives casts per minute and ability ids.
  3. **Shortest gap between casts**: from `events(dataType: Casts, sourceID)` for the
     cohort's top 5 only, for abilities whose stated cooldown is ≥ 30 s (major cooldowns).
  4. **Uptimes**: the `Buffs` / `Debuffs` table by source (existing `get_report_table`
     path), `uptime / fight duration`.
  5. **Stats**: `report.playerDetails(fightIDs, includeCombatantInfo: true)` →
     `combatantInfo.stats` for ≤ 10 cohort members.
  6. **Talent names**:
     - The `talentTree` / `talents` ids are talent-entry ids, not spell ids.
     - Names are resolved through Raidbots' static `talents.json` (verified mapping: entry
       112921 → Darkness, spell 196718), cached per build.
     - This lookup is **optional and off by default** (`wcl_guide_talent_names_url` empty)
       until its terms are checked (task). Without it the data sheet records builds by
       hash and share only, and talent names come from fact-sheet sources.
  7. **Ability names/ids**: from report `masterData` / casts tables. For anything else,
     `gameData { ability(id) { id name } }` (verified).
- **Verified (live queries)**:
  - `gameData.classes` shape and Devourer (DH id 12, spec id 3, slug `Devourer`).
  - Zone 55 "Mythic+ Season 2" with its 8 dungeon encounter ids; raid zone 53 "The
    Venomous Abyss".
  - The `characterRankings` fields above.
  - `playerDetails` `combatantInfo.stats` / `talentTree`; `gameData.ability`.
  - Observation: `bracket: N` returned key level N+1, so filter on `bracketData` and don't
    rely on `bracket`.
- **Budget**: The client has about **720 WCL points per hour**. Data sheets are cached 12 h
  per patch/season and built in `background_lane()`. The cohort is shrunk with
  `benchmark.budget_size()` when the budget is low (R6).
- **Related finding (out of scope, logged for a follow-up)**: `benchmark.leaderboard_page`
  (queries.py:25-51) does not pass `leaderboard: LogsOnly`, so a cohort can include
  report-less Blizzard rows. The data sheet will use LogsOnly; the existing benchmark is left
  unchanged in this feature.

## R6. Data-sheet sample size and cohort

- **Decision**:
  - Builds and gear: every logs-only ranking entry from page 1 (100 per page) of up to 4
    encounters. For raid, these are the 4 encounters with the most parses; for M+, the 4
    dungeons with the most runs. That is up to 400 entries.
  - Casts: `N = 20` players (`wcl_guide_datasheet_min_sample`), spread over those
    encounters, one per player name.
  - Gaps and stats: 5 and 10 players.
  - `sufficient = casts cohort ≥ 20 AND ranking entries ≥ 50`. Below that, facts are kept
    but marked insufficient and are not stated as guidance (FR-033).
  - When `budget_size()` reports low points, the casts cohort halves; it never drops below
    the threshold silently, and an under-threshold sheet is simply marked insufficient.
- **Rationale**:
  - 20 players gives stable medians and p25/p75 for casts per minute.
  - At about 1–3 points per table query, one data sheet costs roughly 4 ranking pages +
    20 casts tables + 5 event queries + 10 player-details, about 60–90 points. That keeps a
    full regeneration wave (in-use guides only) within the hourly budget when spread by the
    concurrency cap of 2.
- **Alternatives**: Top 100 casts (blows the budget); top 5 (unstable, and the
  benchmark's `MIN_MATCHES=3` philosophy is for a cohort around one player, not a spec
  baseline).

## R7. Brief delivery to the agent: loader injection, not a boot-time registry

- **Decision**:
  - `wcl_agent/guide_meta.py` exposes `set_brief_loader(fn)` / `async get_brief(class, spec,
    content_type)`. At startup the backend registers a loader that reads the published brief
    from `spec_guides` through a 60 s in-process TTL cache, and invalidates its own cache
    entry on publish.
  - `get_cooldown_usage` and the new `get_coaching_brief` tool both read through it.
  - `GuideMeta`, `set_guide_meta`, `load_guide_registry` and the `guides` boot step are
    removed (the boot step becomes a loader registration).
- **Rationale**:
  - The current registry (guide_meta.py:35, keyed `(class, spec)` casefolded) holds only
    cooldowns.
  - It is loaded once at boot (main.py:114-124) and updated only by the process that
    generated a guide, so it is stale across instances.
  - Tools are coroutines since feature 013, so an awaited loader is natural.
  - Dependency direction backend → `wcl_agent` is preserved.
- **Alternatives**: Warm registry with periodic reload (more moving parts, still stale for up
  to the reload interval); importing backend DB code into `wcl_agent` (forbidden direction).

## R8. Which content type a chat turn is about (FR-011)

- **Decision**:
  - Use a pure keyword/zone classifier, `classify_content_type(user_text, recent_report_zone,
    mplus_zone_name, dungeon_names, raid_boss_names) -> "raid" | "mplus" | "unknown"`.
  - Signals:
    - Mythic+ terms (`m+`, `mythic+`, `mythic plus`, `keystone`, `key`, `+\d{1,2}`,
      `dungeon`, current-season dungeon names from the M+ zone's encounters).
    - Raid terms (`raid`, `boss`, raid difficulty names, current raid boss names).
    - The most recent `TrackedRaid.zone` (a name) compared with the Mythic+ zone name.
  - `unknown` → `raid`, and the preamble says the content type was assumed.
  - The agent can still fetch the other brief with `get_coaching_brief` when the
    conversation turns, as instructed by `<COACHING_BRIEFS>`.
- **Rationale**: The preamble is built before the model runs (ws.py:340-388). A
  deterministic classifier is testable and free. The tool covers anything it misses, and the
  accuracy check measures wrong-content use (FR-022).
- **Alternatives**:
  - Always inject both briefs: doubles tokens and invites cross-use.
  - Never inline, tool only: an extra model round on every coaching turn and a risk the
    agent skips the call.
  - An LLM classifier: cost and latency on every turn.

## R9. Detecting Mythic+ zones, season and reports

- **Decision**: In `patch.py`:
  - `mplus_zone_from(zones)` = the newest non-frozen zone whose difficulties include id 10
    (name "Mythic+").
  - `current_mplus_season()` = that zone's default partition name, falling back to the zone
    name (e.g. "Season 3").
  - `is_mplus_zone(zone_id)`.
  - Reports are classified by `ReportSummary.zone_id` (cached, cache_models.py:54-76)
    against that zone.
- **Rationale**: The zone list already carries `difficulties` and `partitions` (menu.py
  :19-31, queries.py:6-20). Raid detection already uses "offers Heroic" (patch.py:25-29), and
  the test fixture models the M+ zone as difficulty 10 with season-named partitions
  (test_guide_meta.py:46-57). No keystone fields are fetched anywhere today.
- **Alternatives**: A hard-coded season list (needs edits every season).

## R10. Staleness trigger and the "in use" rule (FR-050/051)

- **Decision**:
  - `maybe_scan_stale_guides()`, throttled in-process to once per 10 minutes, runs
    opportunistically from `GET /api/guides`, the chat preamble and startup, via `spawn`.
  - "In use" = `last_wanted_at` within 14 days. The timestamp is stamped (≤ hourly per row)
    when:
    - the guide is opened;
    - a character's spec resolves to it;
    - its brief is injected or fetched in chat.
- **Rationale**:
  - There is no scheduler in the app; recent raids use request-path triggers with claims
    (services/recent_raids.py:232-260).
  - Cross-instance duplicates are already prevented by the atomic `pending` upsert and the
    unique key.
  - The literal "spec of a saved character" cannot be evaluated by a background job: user
    characters are tenant-scoped under RLS, and the runtime DB role can't read across
    tenants. Stamping at the moments a saved character's spec is resolved or its brief is
    used gives the same practical effect, and lets abandoned profiles stop costing
    regenerations.
- **Alternatives**:
  - A cron/worker service (new deployable).
  - A cross-tenant query with an owner role (weakens RLS).
  - Regenerate everything on every patch (≈80 full runs; rejected in clarification).

## R11. Storage shape for two content types + published/draft

- **Decision**: Extend `spec_guides` with `content_type` and a new unique key
  `(class, spec, content_type)`. Keep one published version per row, plus latest-run
  `status`, `draft`, `review_issues` and `failure_reason`. Migration 0011 backfills
  `content_type='raid'` and `stale_reason='legacy'`. Full table design in data-model §2.
- **Rationale**:
  - Today's upsert flips `status` to pending/failed on the same row (services/guide.py
    :291-345), and `GuideOut` hides the markdown unless ready (api/guides.py:49-70). So a
    refresh hides the guide, which FR-053 forbids.
  - One row per key keeps the existing batch reads (`get_spec_guides_for`) and the dedup
    unchanged in shape.
- **Alternatives**: A versions table (rejected, see plan Complexity Tracking); a separate
  `mplus_guides` table (duplicated code paths, violates DRY).

## R12. Roster from game data (FR-018..FR-020)

- **Decision**:
  - `wcl_agent/roster.py` with `load_roster()` (async): WCL `gameData.classes { id name slug
    specs { id name slug } }`, cached 24 h in a new 014 family `game_classes`, mapped to WCL
    filter values (PascalCase of the slug, matching existing `CLASS_SPECS` keys).
  - `roster_snapshot()` (sync) returns the last loaded roster or the static fallback.
  - The static `CLASS_SPECS` gains `"Devourer"` and becomes fallback-only.
  - `tools.get_spec_options` / validation, `api/guides._validate_spec`, `build_guide_roster`
    and `services/guide` display names read the snapshot.
  - Roles: tank and healer sets unchanged, so Devourer is dps.
- **Rationale**: Today four modules read the static map (text search, R13), and no
  `gameData` query exists (report_tools.py mentions it only in a docstring).
- **External**: Verified 2026-10-18 by live query: `gameData { classes { id name slug specs { id name slug } } }` returns
Demon Hunter `slug "DemonHunter"` with Havoc, Vengeance and **Devourer (`slug "Devourer"`)**. Slugs
are already the WCL filter values (CamelCase), so no mapping table is needed. WCL spec ids are
per-class (not Blizzard spec ids; Devourer's Blizzard id 1480 appears in `combatantInfo.specIDs`).

## R13. GitNexus impact (Constitution VI)

- **Run**: `node .gitnexus/run.cjs impact <sym> --direction upstream` for `CLASS_SPECS`,
  `_run_spec_guide`, `ensure_spec_guide`, `build_guide_roster`, `get_spec_guides_for`,
  `build_preamble`, `get_guide_meta`, `upsert_spec_guide`, `build_agent`. This was repeated
  after `analyze --index-only` (6,411 nodes) and once via MCP `impact` with
  `file_path`/`kind`.
- **Result**: Every target resolves with an empty `type`. The listed processes are
  unrelated (`Check_rate_limit → _memo`, `Cohort_branch → _decode`), with near-identical
  counts (51/53/93). `CLASS_SPECS` gives `UNKNOWN` (module constant). This is the quirk
  recorded on 2026-10-14/16. **Treated as UNKNOWN** per CLAUDE.md.
- **Text-search callers (authoritative for this plan)**:
  - `CLASS_SPECS`: services/guide.py:28,317,363; api/guides.py:14,35; wcl_agent/tools.py
    :17,242,248,415,422; constants.py:37,64.
  - `ensure_spec_guide`: services/guide.py:412; api/guides.py:113.
  - `build_guide_roster`: api/guides.py:81.
  - `get_spec_guides_for`: api/ws.py:363.
  - `get_spec_guide`: repository.py:1066; api/profile.py:41; api/guides.py:92,114;
    services/guide.py:284.
  - `upsert_spec_guide`: services/guide.py:292,333,345.
  - `list_spec_guides`: services/guide.py:253.
  - `build_preamble` / `guide_heading_label`: api/ws.py:46,375,378.
  - `get_guide_meta`: cooldowns.py:175.
  - `set_guide_meta` / `registry_meta`: services/guide.py:261,348.
  - `load_guide_registry`: main.py:78,118.
  - `parse_guide_meta`: services/guide.py:200,322.
  - `INSTRUCTION`: agent.py:478.
  - Tests: test_spec_guides, test_guide, test_guide_reconcile, test_guides_and_boot,
    test_profile_context, test_guide_meta, test_cooldowns, test_prompt_contract, test_roles.
- **How to apply**: Treat all of the above as HIGH. Re-run `impact` before each edit (it may
  be fixed by a GitNexus upgrade), and run `detect_changes --scope all` before each commit.

## R14. Publisher page use and terms (FR-043)

- **Decision**:
  - Research uses Gemini `google_search` grounding plus `url_context`. `url_context` may
    fetch only an allowlist whose robots.txt allows it:
    - `worldofwarcraft.blizzard.com` (tier 1);
    - `www.icy-veins.com` (tier 3);
    - `www.archon.gg` and `murlok.io` (tier 3; their numbers duplicate WCL, so they are
      cited only when WCL lacks the item).
  - **Wowhead is never fetched**: its robots.txt disallows AI crawlers, Google-Extended
    included. It can appear only as a cited link that search surfaced, with the fact carried
    by its snippet; it is tier 3, but snippet-only items are capped at confidence "low".
  - Forums, Reddit and video are tier 4: they can lead to sources, but are never citable.
  - Published guides paraphrase extracted facts with credit and a link, never quote more
    than 25 words, and never reproduce structure or tables (FR-043).
  - The tier and domain table lives in `guide_pipeline/research.py` as one constant.
- **Verified (fetched)**:
  - Wowhead's robots.txt has `Disallow: /` for Google-Extended, GPTBot, ClaudeBot, CCBot
    and Scrapy. Its terms page blocks bots and could not be read.
  - Icy Veins' terms (updated Aug 4, 2026) have no scraping or AI clause; the content is
    copyrighted; robots allow `/`.
  - Archon (RPGLogs, LLC, the same company as WCL) and Murlok robots allow `/`; their terms
    were not readable or not found.
- **Rationale**: This honours the clarified decision (fetch to extract facts, paraphrase,
  credit) while respecting each site's published crawling rules. WCL (licensed via our API
  client) and Blizzard remain the substance; publishers add interpretation.
- **Not legal advice**: a maintainer review of Icy Veins' terms is a tracked task before the
  research stage is enabled in production (`wcl_guide_research_fetch_enabled`, default
  `false` until then; with it off, research is search-grounded snippets only).

## R15. Accuracy-check design (FR-021..FR-025)

- **Decision**: A maintainer-run CLI package `backend/evals/guides` (contract
  `accuracy-check.md`) with JSON fixtures and regex matching:
  - facts per spec × content type;
  - six adversarial fixtures;
  - coaching cases on real report codes.
  It scores stored guides by default; `--live-generate` scores a pipeline change. The
  committed `baseline.json` is recorded first. The deterministic scorers are unit-tested in
  normal pytest.
- **Rationale**: The release gate needs live models and WCL, which are not suitable for CI.
  Regex matching keeps the scoring itself deterministic. An LLM judge is avoided because it
  would reintroduce the problem being measured.
- **Alternatives**: An LLM-as-judge scorer (non-deterministic; shares the model's blind
  spots); pytest-marked live tests (`-m perf`-style). Rejected: reports and baselines fit a
  CLI better.

## R16. Brief budget numbers

- **Decision**: `BRIEF_MAX_CHARS = 6000` and `PREAMBLE_BRIEFS_MAX_CHARS = 12000`, both
  configurable.
- **Rationale**:
  - Today's total guide budget is 4,000 characters, and each guide is cut to 1,500
    (profile_context.py:31-32), well below a useful brief.
  - 6,000 characters (about 1.5k tokens) fits the structured sections in the
    agent-context contract with room for 8–12 items each.
  - 12,000 inline characters means one or two own specs are always whole. Larger profiles
    fall back to the tool, so per-turn tokens stay bounded (PERF-004 / feature 011
    concerns).
- **Alternatives**: Per-brief 3,000 (too small for cooldowns + benchmarks + mistakes);
  unbounded (token growth per turn).
