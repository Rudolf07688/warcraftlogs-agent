---
description: "Task list for feature 015 — Grounded, Patch-Aware Class Guides"
---

# Tasks: Grounded, Patch-Aware Class Guides

**Input**: Design documents from `specs/015-grounded-class-guides/` — plan.md, spec.md, research.md (R1–R16), data-model.md, contracts/ (guides-api, agent-context, guide-pipeline, ui-guides, accuracy-check), quickstart.md

**Tests**: Included. The plan names the new and updated test files, and Constitution II requires every increment to be verified. Tests run with `uv run --extra test pytest -q` and use the existing fakes: `backend/tests/wcl_fakes.py`, the SQLite fixtures in `backend/tests/conftest.py`, and `monkeypatch` on model calls.

**Organization**: Grouped by user story. Story phases follow the rollout order in quickstart §4. US4 (the baseline) comes first because FR-024 requires the baseline before any behaviour change. The remaining P1 stories come next, then P2, then P3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US10 = spec.md User Stories 1–10
- **GitNexus rule (Constitution VI, research R13)**: before editing any symbol in research R13's caller list, run `node .gitnexus/run.cjs impact <symbol> --direction upstream --repo .`. If the result shows the known quirk (empty target type, unrelated processes), treat it as UNKNOWN and confirm callers with `grep -rn`. Before each commit, run `node .gitnexus/run.cjs detect-changes --scope all --repo .`.

## Path Conventions

Web app: `backend/app/` (FastAPI), `wcl_agent/` (agent package), `backend/tests/`, `backend/evals/`, `frontend/src/`. Migrations live in `backend/migrations/versions/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuration and package skeletons used by several stories.

- [X] T001 Add the new settings from contracts/guide-pipeline.md §Config to `Settings` in `backend/app/config.py`:
  - `wcl_guide_review_model="gemini-3.1-pro-preview"`
  - `wcl_guide_max_review_rounds=3`
  - `wcl_guide_brief_max_chars=6000`
  - `wcl_guide_preamble_briefs_max_chars=12000`
  - `wcl_guide_datasheet_min_sample=20`
  - `wcl_guide_inuse_days=14`
  - `wcl_guide_report_per_minute=5`
  - `wcl_guide_research_fetch_enabled=False`
  - `wcl_guide_talent_names_url=""`
  - `wow_version_url`
  - `wow_news_url`

  Give each a one-line comment in the file's existing style, and mirror them as commented examples in `.env.example`.
- [X] T002 [P] Create the package skeleton `backend/app/services/guide_pipeline/__init__.py` (docstring naming the stages from contracts/guide-pipeline.md, `run_guide_generation` stub raising `NotImplementedError`) and empty modules `models.py`, `briefing.py`, `llm.py`, `prompts.py`, `authoring.py`, `render.py`, `datasheet.py`, `research.py`, `checks.py`, `review.py` in the same folder, each with a module docstring.
- [X] T003 [P] Create the eval package skeleton: `backend/evals/__init__.py`, `backend/evals/guides/__init__.py`, `backend/evals/guides/__main__.py` (argparse with subcommands `run` and `datasheet`, both stubs), and the folders `backend/evals/guides/{facts/raid,facts/mplus,adversarial,coaching,reports}/` (with `.gitkeep`). Add `backend/evals/guides/reports/*` and `!backend/evals/guides/reports/baseline.json` to `.gitignore`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The content-type dimension in storage, the shared pipeline models, the model-call helper and Mythic+ zone helpers. When this phase ends, behaviour is unchanged: existing guides become `raid` guides.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add `ContentType = Literal["raid", "mplus"]`, widen `GuideStatus` to include `"needs_review"`, and add `GuideDisplay` in `backend/app/schemas.py`. Keep the existing models compiling; they are reshaped in US5.
- [X] T005 Write migration `backend/migrations/versions/0011_guide_content_types.py` (revision `0011_guide_content_types`, down_revision `0010_recent_raids` — check the exact id in `0010_recent_raids.py`). It must, per data-model §2–§3:
  - On `spec_guides`:
    - add `content_type` varchar(8) NOT NULL with server default `'raid'`;
    - widen `status` to varchar(14);
    - add `brief`, `claims`, `briefing`, `evidence`, `draft` and `review_issues` (JSON/JSONB variant as in 0009), plus `season` varchar(40), `failure_reason` varchar(200), `stale_reason` varchar(40) and `last_wanted_at` timestamptz;
    - drop the unique constraint `uq_spec_guide_identity` and recreate it on `(class_name, spec, content_type)`;
    - set `stale_reason='legacy'` on existing rows.
  - Create table `guide_inaccuracy_reports`, with partial index `ix_guide_reports_open`.
  - Provide a full `downgrade()`.
- [X] T006 Update the ORM in `backend/app/db/models.py`:
  - `SpecGuide` gets the new columns and the new 3-column unique constraint, plus docstring notes on published vs latest-run columns (data-model §2).
  - Add `GuideInaccuracyReport` (data-model §3, FK `users.id` ON DELETE CASCADE).
- [X] T007 Re-key the spec-guide helpers in `backend/app/db/repository.py` by content type:
  - `get_spec_guide(session, *, class_name, spec, content_type="raid")`
  - `upsert_spec_guide(..., content_type="raid", **new _UNSET-stamped columns)`
  - `list_spec_guides` (status columns now include `content_type`, `season`, `stale_reason`, `last_wanted_at`, `failure_reason` and a `has_published` expression)
  - `get_spec_guides_for(session, keys: list[tuple[str, str, str]], ...)`, returning a map keyed by the 3-tuple

  Then add:
  - `publish_spec_guide(session, *, class_name, spec, content_type, markdown, brief, claims, game_patch, season, generated_at, sources, major_cooldowns, briefing, evidence)`: atomically sets the published columns, `status='ready'`, and clears `draft`, `review_issues`, `failure_reason` and `stale_reason`.
  - `hold_spec_guide(...)`: sets `status='needs_review'`, `draft` and `review_issues`.
  - `fail_spec_guide(..., reason)`.
- [X] T008 Update every existing caller to the new repository signatures, passing `content_type="raid"` so behaviour is unchanged:
  - `backend/app/services/guide.py` (`ensure_spec_guide` → `ensure_guide(class_name, spec, content_type="raid", *, force=False)` with dedup key `(class, spec, content_type)`; `_run_spec_guide` keeps its old body for now)
  - `backend/app/api/guides.py`
  - `backend/app/api/profile.py`
  - `backend/app/api/ws.py` (`_build_turn_preamble` passes raid keys)
- [X] T009 [P] Add Mythic+ zone helpers to `wcl_agent/patch.py` (research R9), each with a docstring matching the existing helpers:
  - `MYTHIC_PLUS_DIFFICULTY_ID = 10`
  - `mplus_zone_from(zones)`: newest non-frozen zone whose difficulties include id 10
  - `current_mplus_season()`: async; zone name, e.g. "Mythic+ Season 2"
  - `mplus_zone()`: async
  - `is_mplus_zone_id(zone_id)`: async
  - `current_raid_tier()`: async; newest non-frozen Heroic zone name
- [X] T010 [P] Implement the Pydantic pipeline models in `backend/app/services/guide_pipeline/models.py` exactly as in data-model §4.1–§4.7:
  - `GenerationBriefing`, `SampleScope`, `ObservedAbility`, `ObservedUptime`, `ObservedBuild`, `ObservedStat`, `DataSheet`
  - `EvidenceItem`, `FactSheet`, `EvidenceSnapshot`
  - `LogCheck`, `GuideClaim`, `BriefItem`, `BriefCooldown`, `CoachingBrief`
  - `ReviewIssue`, `CheckFailure`, and `RunOutcome` (`published|held|failed` + reason)
  - Field validators: claim text ≤300 chars, `evidence_refs` non-empty, and `log_check` required for the `mistakes|uptimes|cooldowns|benchmarks` sections.
- [X] T011 [P] Implement `backend/app/services/guide_pipeline/llm.py`:
  - one process-wide `google.genai` client (the `suggestions._get_client` pattern);
  - `async def generate_structured(model, prompt, schema: type[BaseModel] | TypeAdapter, *, tools=None, temperature=0.2) -> parsed`, using `response_mime_type="application/json"` + `response_schema` when `tools` is None;
  - `async def generate_grounded(model, prompt, *, url_context: bool) -> GroundedText(text, sources)`, using `google_search` (+ `url_context`) built-in tools and reading `grounding_metadata.grounding_chunks`;
  - both run through `wcl_agent.model_retry.generate_with_retry` via a one-item async-generator adapter, and raise `GuideModelError` on invalid JSON after one retry.
- [X] T012 [P] Migration test in `backend/tests/test_guide_migration.py` (SQLite `create_all` + repository): the 3-tuple unique key allows raid+mplus rows for one spec; `publish_spec_guide` clears draft, issues and stale fields; `hold_spec_guide` keeps published columns untouched; `get_spec_guides_for` keys by `(class, spec, content_type)`.
- [X] T013 [P] Tests for the patch helpers in `backend/tests/test_guide_meta.py`, extending `MENU_PAYLOAD`: the M+ zone is found by difficulty 10, frozen zones are ignored, `current_raid_tier` returns the Heroic zone name, and `is_mplus_zone_id` works.
- [X] T014 Update the existing guide tests for the re-keyed signatures and run the full suite green: `backend/tests/test_spec_guides.py`, `test_guide.py`, `test_guide_reconcile.py`, `test_guides_and_boot.py`, `test_profile.py`.

**Checkpoint**: Storage supports `(class, spec, content_type)`, every existing guide is a published `raid` guide, and the full test suite passes with behaviour unchanged.

---

## Phase 3: User Story 4 - Guide and coaching accuracy is measured (Priority: P1) — baseline first

**Goal**: A repeatable accuracy check with a committed baseline, recorded against today's guides and coaching before any behaviour change (FR-021..FR-025).

**Independent Test**: `uv run python -m backend.evals.guides run --baseline` produces `reports/baseline.json` + `.md` with every metric. The gate is expected to fail today.

### Tests for User Story 4

- [X] T015 [P] [US4] Unit tests for the scorers in `backend/tests/test_eval_scoring.py`, using fixture guides:
  - fact `correct` / `omitted` / `wrong` from regex
  - leakage detection on PTR/Classic URLs and titles
  - patch accuracy
  - claim support from stored verdicts (`None` → counted as unknown)
  - gate verdicts and exit codes 0/1/2

### Implementation for User Story 4

- [X] T016 [P] [US4] Define the fixture schemas as Pydantic models in `backend/evals/guides/fixtures.py` (contracts/accuracy-check.md §Inputs): `FactCase`, `AdversarialCase`, `CoachingCase`, `ExpectedPoint`. Add a loader that validates every JSON file under `backend/evals/guides/`.
- [X] T017 [US4] Implement the scorers in `backend/evals/guides/scoring.py`:
  - `score_facts(guide_text, unconfirmed, cases)`
  - `leakage(sources)`, reusing one shared PTR/Classic marker list that US8 imports (put it in `backend/app/services/guide_pipeline/research.py` as `ENV_MARKERS` now)
  - `patch_accuracy`, `claim_support`, `current_source_precision`, `spec_coverage`, `abstention_quality`, `wrong_content_brief_use`, `coaching_points`
  - `gate(report) -> bool` per contract §Release gate
- [X] T018 [US4] Implement the coaching runner in `backend/evals/guides/coaching.py`:
  - for each `CoachingCase`, run one turn through `backend.app.agent_runner.stream_response` with the default chat model in a fresh session;
  - pass the case's profile preamble when its player is set;
  - capture the final text, `tool_start` records (`get_coaching_brief` arguments) and the injected brief headers;
  - score `raised` / `missed` / `contradicted` and wrong-content brief use.
- [X] T019 [US4] Implement `run` in `backend/evals/guides/__main__.py`:
  - load the published guides from the DB via `repository.list_spec_guides`;
  - get the roster via the current spec list, so spec coverage works before US3;
  - get the live patch via `wcl_agent.patch.current_patch`;
  - check source links with httpx HEAD/GET, a 10 s timeout and ≤ 50 links sampled;
  - evaluate the adversarial cases;
  - write `reports/<UTC>.json` and `.md`, or `baseline.json` with `--baseline`;
  - support the flags `--specs`, `--content`, `--skip-coaching` and `--live-generate` (the last calls `ensure_guide(..., force=True)` and waits for each run);
  - exit codes per the contract.
- [X] T020 [P] [US4] Write the six adversarial fixtures in `backend/evals/guides/adversarial/`: `old_similar_guide.json`, `ptr_newer_than_live.json`, `conflicting_guides.json`, `hotfix_after_publish.json`, `new_spec_thin_data.json`, `raid_question_only_mplus_brief.json`. Each has fixture evidence items or stored-guide stubs plus the expected outcome, per FR-021.
- [X] T021 [P] [US4] Seed the fact fixtures (≥5 facts each) for `Mage-Fire`, `DemonHunter-Devourer`, `Priest-Holy` and `Warrior-Protection` under both `backend/evals/guides/facts/raid/` and `backend/evals/guides/facts/mplus/`. Mark each fact's `notes` with `"UNVERIFIED — maintainer must hand-check against the live game"` until checked.
- [X] T022 [P] [US4] Seed ≥4 coaching cases in `backend/evals/guides/coaching/`: 2 raid and 2 Mythic+ (using public report codes from the user's recent raids or WCL top rankings), each with 3–5 expected points. Mark the expected points `UNVERIFIED` until the maintainer reviews them.
- [ ] T023 [US4] **Manual (maintainer)**:
  - hand-check and edit the facts and coaching points from T021/T022;
  - run `uv run python -m backend.evals.guides run --baseline`;
  - commit `backend/evals/guides/reports/baseline.json`.

  Do this before merging any later phase (FR-024).

**Checkpoint**: Baseline recorded; every later phase is scored against it.

---

## Phase 4: User Story 1 - Guides written for the real date and live patch (Priority: P1) 🎯 MVP

**Goal**: The agent's clock is live. Each guide is generated by a dedicated, tool-less author from a per-run briefing (date, exact patch/build, hotfix time, tier, season, content type, roster). The author leaves out what it cannot confirm, and generation is postponed when the patch is unknown (FR-001..FR-007).

**Independent Test**: Two calls of the instruction provider under different frozen clocks give different `<CURRENT_TIME>` values. A generated guide states the live patch and stores `game_patch` equal to it. With the zone list unavailable, generation ends `failed` with reason `patch_unknown`.

### Tests for User Story 1

- [X] T024 [P] [US1] Rewrite `test_time_line_is_live` and `test_no_template_braces` in `backend/tests/test_prompt_contract.py` for the provider:
  - patch `datetime` twice and assert the format and that the two values differ;
  - assert the static body has no braces;
  - assert `build_agent().instruction` is callable.
- [X] T025 [P] [US1] Briefing tests in `backend/tests/test_guide_pipeline_briefing.py`:
  - version-endpoint parsing from a fixture body (the pipe format from research R1, `us` row, product `wow` only);
  - fallback to the WCL partition, then `PatchUnknown`;
  - hotfix article parsing from a saved HTML fixture (JSON-LD `dateModified`, the Classes → class → spec nesting; a class with no spec heading means the whole class);
  - `hotfix_touches_spec`;
  - mplus briefing raises `SeasonUnknown` when there is no M+ zone.
- [X] T026 [P] [US1] Pipeline tests in `backend/tests/test_guide_pipeline_run.py`, with `llm.generate_grounded` / `generate_structured` monkeypatched:
  - the author prompt contains the briefing fields;
  - no WCL coaching tool or ADK agent is invoked (assert `agent_runner.stream_response` is never called);
  - claims are rendered to markdown with the patch header;
  - an unconfirmed area is listed;
  - an unknown patch stores `failed` / `patch_unknown`;
  - the row is published via `publish_spec_guide`.

### Implementation for User Story 1

- [X] T027 [US1] Convert the agent instruction to an ADK `InstructionProvider` in `wcl_agent/agent.py` (research R4):
  - keep the static body as `_INSTRUCTION_BODY`, with a `<CURRENT_TIME>` placeholder token that is not a brace;
  - add `def build_instruction(ctx=None) -> str` that fills it with `datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")`;
  - keep `INSTRUCTION = build_instruction()` only as a backwards-compatible alias for tests;
  - pass `instruction=build_instruction` in `build_agent`.
- [X] T028 [P] [US1] Add the `LIVE_VERSION` and `HOTFIX_FEED` cache families in `wcl_agent/cache.py` (enum member, `FamilyConfig` TTLs 900 s and 1800 s, `keys.live_version(region)`, `keys.hotfix_feed()`), with value models `LiveVersion` and `HotfixFeed` (`entries[{date, class_name, specs}]`, `article_url`, `latest_at`) in `wcl_agent/cache_models.py`.
- [X] T029 [US1] Implement the briefing sources in `backend/app/services/guide_pipeline/briefing.py`:
  - `fetch_live_version()`: httpx GET `settings.wow_version_url`; parse the `us` row's `VersionsName` / `BuildId` and `## seqn`; through `get_or_load(LIVE_VERSION)`; best-effort.
  - `fetch_hotfix_feed()`:
    - GET `settings.wow_news_url`;
    - find the newest article link whose title starts with "Hotfixes:";
    - GET it and read the JSON-LD `dateModified`/`datePublished`;
    - parse the body with stdlib `html.parser`: date headings → the "Classes" block → bold class names → bold spec names → list items;
    - map names to WCL values via `wcl_agent.constants.normalize_class_name` and spec casefold match;
    - cache via `HOTFIX_FEED`; best-effort.
- [X] T030 [US1] Implement `build_briefing(class_name, spec, content_type) -> GenerationBriefing` in `backend/app/services/guide_pipeline/briefing.py`:
  - `now_utc`;
  - `live_patch` from version `major.minor.patch`, else `wcl_agent.patch.current_patch()`, else raise `PatchUnknown`;
  - `live_build`;
  - `raid_tier`, `mplus_season` (mplus without a season raises `SeasonUnknown`), `latest_hotfix_at`, `hotfix_touches_spec`;
  - roster fields from `wcl_agent.constants.CLASS_SPECS` for now (US3 swaps in `roster_snapshot()`);
  - `product="retail"`, `environment="live"`, `region="US"`;
  - all WCL calls inside `background_lane()`.
- [X] T031 [P] [US1] Write the prompts in `backend/app/services/guide_pipeline/prompts.py` (contracts/guide-pipeline.md §Prompts):
  - `RESEARCH_COLLECT_PROMPT` (evidence collector; the briefing; content type; "mark PTR/beta/Classic/older-patch material, don't drop it"; never quote > 25 words);
  - `AUTHOR_PROMPT` (claims only from the given evidence ids; ≥1 ref per claim; observed wording with scope; omit and list unconfirmed; content type only);
  - a `format_briefing(briefing)` helper that renders the briefing block (date, patch/build, hotfix time, tier/season, content type, class spec list, "if you cannot confirm X for patch P, leave it out").
- [X] T032 [US1] Implement a basic evidence step in `backend/app/services/guide_pipeline/research.py`:
  - `collect_evidence_basic(briefing) -> FactSheet`: one `llm.generate_grounded(settings.wcl_guide_model, RESEARCH_COLLECT_PROMPT, url_context=False)` call, then one `generate_structured(..., list[EvidenceItem])` extraction call, assigning ids `src:<n>`;
  - no hard filters yet (US8 adds them); keep the function name `build_fact_sheet` as the public entry point.
- [X] T033 [US1] Implement `author_claims(briefing, fact_sheet, data_sheet=None) -> AuthorResult(claims, unconfirmed)` in `backend/app/services/guide_pipeline/authoring.py`: a tool-less `generate_structured(settings.wcl_guide_model, AUTHOR_PROMPT + briefing + evidence listing, AuthorResult)`. Drop any claim whose `evidence_refs` don't resolve, and add its section to `unconfirmed`.
- [X] T034 [US1] Implement `render_guide_markdown(briefing, claims, unconfirmed, sources) -> str` in `backend/app/services/guide_pipeline/render.py`:
  - a header line with class, spec, content type, patch (and season), generated date;
  - one section per claim section, in a fixed order, one bullet per claim (claim id kept in an HTML comment for the `guide_extra_claim` check);
  - a "Not covered" list;
  - no quotes or tables.
- [X] T035 [US1] Implement `run_guide_generation(class_name, spec, content_type) -> RunOutcome` in `backend/app/services/guide_pipeline/__init__.py`:
  - briefing (`PatchUnknown`/`SeasonUnknown` → `fail_spec_guide(reason)`) → `build_fact_sheet` → `author_claims` → `render_guide_markdown`;
  - then `publish_spec_guide` with `claims`, `briefing`, an evidence snapshot, `sources` (from the fact sheet) and `game_patch=briefing.live_patch`;
  - model errors → `fail_spec_guide("model_error")` with the published version untouched;
  - wrapped in the existing `_generation_slot()` semaphore.
- [X] T036 [US1] Replace the generation body in `backend/app/services/guide.py`: `ensure_guide` spawns `run_guide_generation`. Delete `_GUIDE_PROMPT`, `_generate_text`, `_stream_text`, `parse_guide_meta`, `_parse_meta_reply`, `_repair_guide_meta` and `GuideMetaBlock` usage (and `GuideMetaBlock`/`GuideCooldownIn` in `backend/app/schemas.py` if no longer referenced; grep first). Update `test_guide_meta.py` / `test_spec_guides.py` to fake `run_guide_generation` or the `llm` helpers instead of `_generate_text`.
- [ ] T037 [US1] Run the US1 tests and the full suite. Then run `uv run python -m backend.evals.guides run --live-generate --specs Mage/Fire --content raid --skip-coaching` and record the patch-accuracy delta versus the baseline in `specs/015-grounded-class-guides/checklists/progress.md` (create it).

**Checkpoint**: MVP. Guides are written for the live date and patch by a dedicated author, and the chat agent's clock is live.

---

## Phase 5: User Story 3 - Every live spec is covered, including Devourer (Priority: P1)

**Goal**: The class/spec roster comes from WCL `gameData`, with a static fallback that includes Devourer, and is used everywhere the static map was (FR-018..FR-020).

**Independent Test**: `GET /api/guides` lists Havoc, Vengeance and Devourer for Demon Hunter with `roster_source="game_data"`. With WCL failing, it still lists Devourer with `roster_source="fallback"`. A character resolved to Devourer gets role `dps`.

### Tests for User Story 3

- [X] T038 [P] [US3] Roster tests in `backend/tests/test_roster.py`, using a `wcl_fakes` responder for `GameClasses`:
  - mapping slugs → `RosterSpec`;
  - Devourer present with role dps;
  - fallback on error;
  - `roster_snapshot()` before and after load;
  - a new unknown spec appears;
  - a removed spec disappears.
- [X] T039 [P] [US3] Add `("Devourer", "dps")` to the role table in `backend/tests/test_roles.py`, and assert `get_spec_options("DemonHunter")` includes Devourer in `backend/tests/test_spec_guides.py`.

### Implementation for User Story 3

- [X] T040 [P] [US3] Add `"Devourer"` to `CLASS_SPECS["DemonHunter"]["specs"]` in `wcl_agent/constants.py`, and update the module docstring: the map is the fallback for `wcl_agent/roster.py`.
- [X] T041 [P] [US3] Add the `GAME_CLASSES` GraphQL query (`query GameClasses { gameData { classes { id name slug specs { id name slug } } } }`) to `wcl_agent/queries.py`. Add the `GAME_CLASSES` cache family (TTL 86400, key `wcl:v1:game:classes`) to `wcl_agent/cache.py`, with a `GameClasses` value model in `wcl_agent/cache_models.py`.
- [X] T042 [US3] Implement `wcl_agent/roster.py` (data-model §6):
  - `RosterSpec` and `Roster` dataclasses;
  - `async load_roster()` via `get_or_load(GAME_CLASSES)`, mapping class display from `name` and filter values from `slug`, falling back to `CLASS_SPECS` on any exception;
  - `roster_snapshot()` (last loaded roster or fallback, module-level, lock-free read);
  - `role_for(spec)`, delegating to `constants.role_for_spec`, which now returns `dps` for any spec not in the tank/healer sets;
  - `specs_for(class_name)`.
- [X] T043 [US3] Switch the static-map readers to the roster:
  - `wcl_agent/tools.py` `get_spec_options` / validation (lines ~237-252, ~410-422) → `roster_snapshot()`;
  - `wcl_agent/constants.normalize_class_name` → also accepts roster classes;
  - `backend/app/api/guides._validate_spec` → `roster_snapshot()`;
  - `backend/app/services/guide.build_guide_roster` and the display-name lookup → roster;
  - `backend/app/services/guide_pipeline/briefing.py` class spec list → roster.
- [X] T044 [US3] Load the roster at startup as an optional boot step `"roster"` in `backend/app/main.py`, next to the existing optional `guides` step, with `detail` = spec count + source. Add `roster_source` to `GuideListOut` in `backend/app/schemas.py` and to the list response in `backend/app/api/guides.py`.

**Checkpoint**: Devourer and any future spec appear in the library, the tools and character role inference.

---

## Phase 6: User Story 2 - The agent coaches from a complete, content-matched brief (Priority: P1)

**Goal**: Each published guide carries a code-built coaching brief. The agent gets whole briefs matched to the turn's content type, inline or through `get_coaching_brief`. `get_cooldown_usage` uses the matching brief, and drafts never reach the agent (FR-008..FR-017).

**Independent Test**: With a seeded Raid brief and Mythic+ brief for a profile spec:
- a raid-log question injects the Raid brief whole;
- a "+12" question injects or fetches the Mythic+ brief;
- a spec with only a Raid brief asked about M+ gets `no_brief` and no raid brief;
- over the budget, whole briefs are omitted and listed in the index.

### Tests for User Story 2

- [X] T045 [P] [US2] Brief tests in `backend/tests/test_coaching_brief.py`:
  - `build_brief` from fixture claims (section mapping; `ability_id` only from the data sheet, else `None`);
  - golden `render_brief_text` per contracts/agent-context.md §1 (header, tags, `LOG:` lines, unconfirmed list, no braces);
  - length vs `wcl_guide_brief_max_chars`;
  - "What the coach looks for" section in the markdown.
- [X] T046 [P] [US2] Classifier tests in `backend/tests/test_content_type.py`:
  - M+ keywords (`m+`, `mythic+`, `keystone`, `+12`, a dungeon name) → mplus;
  - raid terms / a boss name → raid;
  - recent tracked zone = M+ zone name → mplus;
  - nothing → unknown.
- [X] T047 [P] [US2] Preamble tests in `backend/tests/test_profile_context.py`, replacing the 1500/4000 trimming tests:
  - whole-brief inclusion order (own then friends, one per spec);
  - omission at `wcl_guide_preamble_briefs_max_chars` with index status `omitted (budget) — use get_coaching_brief`;
  - "content type assumed: Raid" on unknown;
  - drafts never injected;
  - an empty profile is byte-identical to today.
- [X] T048 [P] [US2] Tool tests in `backend/tests/test_guides_tool.py`:
  - `get_coaching_brief` success;
  - unknown spec → error with valid specs;
  - invalid content type;
  - missing content type → `no_brief` with the FR-014 message and no fallback;
  - no loader → `no_brief`.
- [X] T049 [P] [US2] Update `backend/tests/test_cooldowns.py`:
  - an M+ report (zone = M+ zone) uses the mplus brief's cooldowns;
  - an M+ report with only a raid brief → `guide.available=false`;
  - an explicit `content_type` argument overrides inference.
- [X] T050 [P] [US2] Extend `backend/tests/test_prompt_contract.py`:
  - `<COACHING_BRIEFS>` clauses 1–5 from contracts/agent-context.md §3 are present;
  - `get_coaching_brief` is in `TOOLS` and mentioned in the instruction;
  - the old `<GUIDES>` heading-label wording is removed.

### Implementation for User Story 2

- [X] T051 [US2] Implement `build_brief(briefing, claims, unconfirmed, data_sheet) -> CoachingBrief` and `render_brief_text(brief, freshness) -> str` in `backend/app/services/guide_pipeline/render.py` (data-model §4.6, contracts/agent-context.md §1). Then extend `render_guide_markdown` with a "What the coach looks for" section listing every brief item that has a `log_check` (FR-017).
- [X] T052 [US2] Wire the brief into `run_guide_generation` in `backend/app/services/guide_pipeline/__init__.py`:
  - build the brief after authoring;
  - persist `brief`;
  - set `major_cooldowns` from `brief.cooldowns`;
  - persist `season` for mplus.
- [X] T053 [US2] Replace the cooldown registry with the brief loader in `wcl_agent/guide_meta.py` (data-model §5): keep `GuideCooldown`; add the `BriefRecord` dataclass, `set_brief_loader`, `async get_brief(class_name, spec, content_type)` (casefold normalisation) and `clear_brief_loader()` for tests; remove `GuideMeta`, `set_guide_meta`, `get_guide_meta`, `registry_size` and `clear_guide_meta`. Grep their callers first (research R13).
- [X] T054 [US2] Implement the backend loader in `backend/app/services/guide.py`:
  - `async load_brief_record(class_name, spec, content_type) -> BriefRecord | None`:
    - reads the published `brief` from `spec_guides` with a plain session;
    - computes freshness with `guide_freshness` against the cached live patch (and season for mplus);
    - renders text with `render_brief_text`;
    - uses a 60 s in-process TTL cache keyed by the 3-tuple, plus `invalidate_brief_cache(key)`, called from `publish_spec_guide` callers.
  - Remove `load_guide_registry` and `registry_meta`.
  - In `backend/app/main.py`, replace the `guides` boot step with `set_brief_loader(load_brief_record)`.
- [X] T055 [P] [US2] Implement `classify_content_type(user_text, recent_zone_name, mplus_zone_name, mplus_dungeons, raid_bosses) -> Literal["raid","mplus","unknown"]` as a pure function in `backend/app/services/content_type.py` (research R8), with a compiled regex for `+\d{1,2}`.
- [X] T056 [US2] Rewrite the guide block of `build_preamble` in `backend/app/services/profile_context.py`:
  - new parameters `briefs: dict[tuple[str,str], BriefRecord]` (already filtered to the turn's content type), `available: dict[tuple[str,str], dict[str, str]]` (content type → status) and `content_type_note: str | None`;
  - drop `_PER_GUIDE_CHARS`/`_TOTAL_GUIDE_CHARS` for guides (the guild summary trim stays);
  - include whole brief texts in profile order until `settings.wcl_guide_preamble_briefs_max_chars`;
  - emit the index lines (contract §2.1 step 4);
  - remove `guide_heading_label` (the label now lives in the brief header).
- [X] T057 [US2] Rewrite `_build_turn_preamble` in `backend/app/api/ws.py` to take the turn's `user_text`:
  - load the M+ zone, its dungeon names and the raid boss names from `load_world_zones()` (cached);
  - take the most recent `TrackedRaid.zone`;
  - call `classify_content_type` (`unknown` → `raid` + note);
  - fetch `get_brief` for each profile `(class, spec)` and the chosen content type, plus the published-status map for both types via `get_spec_guides_for`;
  - call `build_preamble`.

  Update the call site at ws.py:256-264 to pass the message text.
- [X] T058 [P] [US2] Implement the `get_coaching_brief(class_name, spec_name, content_type="raid")` tool in `wcl_agent/guides_tool.py` (contracts/agent-context.md §2.2), with roster normalisation and the provenance envelope style of other tools. Add it to `TOOLS` in `wcl_agent/agent.py`.
- [X] T059 [US2] Change `get_cooldown_usage` in `wcl_agent/cooldowns.py`:
  - add the `content_type: str = ""` parameter (docstring updated for the model);
  - infer it from the report's `ReportSummary.zone_id` via `is_mplus_zone_id`;
  - read cooldowns from `await get_brief(class, spec, content_type)`;
  - add `content_type` to the `guide` envelope;
  - `guide.available=false` when no brief, with no cross-type fallback.
- [X] T060 [US2] Replace `<GUIDES>` with `<COACHING_BRIEFS>` in `wcl_agent/agent.py` `_INSTRUCTION_BODY`, with the five clauses from contracts/agent-context.md §3. Mention `get_coaching_brief` and `get_cooldown_usage(content_type)` in the tools section, keeping the no-braces rule.

**Checkpoint**: The agent coaches from whole, content-matched, verified briefs. US2 can be demoed with briefs generated by the US1 pipeline.

---

## Phase 7: User Story 5 - Separate Raid and Mythic+ guides in a clean library (Priority: P2)

**Goal**: Two independently generated guides per spec. The API returns one row per spec with nested raid/mplus summaries. The UI gets the toolbar switch, the other-type dot and viewer tabs. Characters show both statuses, and Mythic+ guides are requested for characters with M+ activity (FR-026..FR-031).

**Independent Test**:
- Generate only Mythic+ for one spec: Raid stays "Not generated".
- The switch changes rows, filter and counts.
- The dot reflects the other type.
- The viewer tabs switch content.
- 360 px width and keyboard-only work.
- SC-014 timing: under 30 s.

### Tests for User Story 5

- [X] T061 [P] [US5] API tests in `backend/tests/test_guides_api_v2.py`:
  - `GET /api/guides` shape: one row per spec with `raid`/`mplus` `GuideSummary`, `has_published`, `refreshing`, `role`;
  - `GET /{cls}/{spec}/{ct}` `display` rules (published / draft / none);
  - `POST .../generate` only spawns that content type (faked `run_guide_generation`);
  - `ct="pvp"` → 422;
  - an unknown spec → 404;
  - rate limit 429.
- [X] T062 [P] [US5] Profile tests in `backend/tests/test_profile.py`:
  - `CharacterOut.guides` has raid and mplus statuses;
  - saving a character with M+ rankings in the M+ zone requests both guides, otherwise raid only (fake `get_character_zone_rankings`).

### Implementation for User Story 5

- [X] T063 [US5] Reshape the guide schemas in `backend/app/schemas.py` per contracts/guides-api.md: `GuideSource` (+tier, date), `GuideSummary`, `GuideListItem` (nested `raid`/`mplus`, `role`), `GuideListOut` (+`roster_source`), `GuideOut`, `GuideReportIn`, `GuideReportOut`, `CharacterGuides`. Replace `CharacterOut.guide_status`/`guide_updated_at` with `guides: CharacterGuides` and update `from_character(char, guides_by_type)`.
- [X] T064 [US5] Rewrite `build_guide_roster(rows, live_patch, live_season)` in `backend/app/services/guide.py` to emit one item per roster spec, with both content-type summaries computed by a shared `summarize_guide(row, live_patch, live_season)` helper (freshness from `stale_reason`, patch, season).
- [X] T065 [US5] Rewrite the routes in `backend/app/api/guides.py`:
  - `GET /api/guides`;
  - `GET /api/guides/{class_name}/{spec}/{content_type}` (`display`, `review_issues` only for draft, `unconfirmed` from `brief.unconfirmed`, `failure_reason`);
  - `POST /api/guides/{class_name}/{spec}/{content_type}/generate`.

  Use a `content_type: ContentType` path param (FastAPI → 422) and remove the old two-segment routes.
- [X] T066 [US5] Update `backend/app/api/profile.py`: `_char_out` and the profile list load both content-type rows in one `get_spec_guides_for` call and build `CharacterGuides`.
- [X] T067 [US5] Update `run_character_guide` in `backend/app/services/guide.py`:
  - after resolving the spec, `ensure_guide(cls, spec, "raid")`;
  - then `ensure_guide(cls, spec, "mplus")` when `get_character_zone_rankings(name, server, region, zone_id=<M+ zone id>)` (background lane) returns ≥1 ranking with a spec (FR-030).
- [X] T068 [P] [US5] Frontend types in `frontend/src/types.ts`: `ContentType`, `GuideStatus` (+`needs_review`), `GuideDisplay`, `GuideSummary`, `GuideListItem`, `Guide`, `GuideSource` (+tier, date), `CharacterGuides`, with `Character.guides` replacing `guide_status`/`guide_updated_at`.
- [X] T069 [P] [US5] REST client in `frontend/src/api/restClient.ts`: `listGuides()` (new shape), `getGuide(cls, spec, ct)`, `generateGuide(cls, spec, ct, force)`, `reportGuide(cls, spec, ct, note)`.
- [X] T070 [P] [US5] Add `getGuideContentType()`/`setGuideContentType()` to `frontend/src/uiPrefs.ts` (key `wcl.ui.guideContentType`, default `"raid"`, defensive try/catch like `getSidebarWidth`).
- [X] T071 [P] [US5] Update `frontend/src/components/StatusBadge.tsx`:
  - add `needs_review` to `GUIDE_TONE` (warn), `GUIDE_LABEL_SHORT` and `GUIDE_LABEL_LIBRARY`;
  - add a `GUIDE_GLYPH` map for the characters indicator (`✓ – … ! ×`) per the guides-api.md status table.
- [X] T072 [US5] Add the shadcn tooltip through the shadcn MCP: run `npx shadcn@latest add @shadcn/tooltip` in `frontend/` (creates `frontend/src/components/ui/tooltip.tsx`), then run the MCP audit checklist (`get_audit_checklist`) and fix what it flags (Constitution VII).
- [X] T073 [US5] Extract the viewer into `frontend/src/components/profile/GuideViewerDialog.tsx` (contracts/ui-guides.md §Viewer):
  - `Dialog` with a class-coloured title;
  - `Tabs` Raid | Mythic+ opening on the clicked type, fetching each tab once;
  - per tab: provenance (`Patch …` / `Season …`), freshness badge, refreshing indicator, markdown via `StreamMarkdown`, Sources with tier labels, a muted "Not covered" list;
  - empty state with an inline Generate button, and the pending text.
- [X] T074 [US5] Rework `frontend/src/components/profile/ClassGuidesTab.tsx` per contracts/ui-guides.md §Library:
  - toolbar `ToggleGroup` Raid | Mythic+ (persisted via uiPrefs) between search and status filter;
  - rows show the selected type's summary and actions keyed by `(class, spec, contentType)`;
  - other-type dot using `Tooltip`, with an `aria-label`; clicking it switches type;
  - filter, card counts and the toolbar count use the selected type;
  - polling when either type is pending;
  - use `GuideViewerDialog`.
- [X] T075 [US5] Replace `GuideBadge` with `GuideIndicators` in `frontend/src/components/profile/CharactersTab.tsx`: two compact items, `Raid <glyph>` and `M+ <glyph>`, each with an `aria-label` (e.g. "Mythic+ guide: not generated"), shown only when the spec is resolved. Keep polling on either pending status.
- [ ] T076 [US5] `cd frontend && npm run build && npm run lint`. Then do the manual check per quickstart §3 row 5 (desktop 3-column, 360 px, keyboard-only, screen-reader labels on the switch and dot, SC-014 timing) and record the results in `specs/015-grounded-class-guides/checklists/progress.md`.

**Checkpoint**: Raid and Mythic+ guides can be generated, viewed and tracked independently, and the UI is unchanged in look.

---

## Phase 8: User Story 6 - Guides built on measured Warcraft Logs evidence (Priority: P2)

**Goal**: A per-spec, per-content-type data sheet from logs-only top rankings: builds and gear, casts per minute, shortest cast gaps, uptimes, stats and real ability ids. It feeds the author, and ability ids come only from it (FR-032..FR-035).

**Independent Test**: `uv run python -m backend.evals.guides datasheet Mage/Fire raid` prints a sufficient sheet (n ≥ 20) whose cpm, gaps and ids match WCL for 3 hand-checked abilities. A generated brief's cooldown ids all come from the sheet.

### Tests for User Story 6

- [X] T077 [P] [US6] Data-sheet tests in `backend/tests/test_guide_pipeline_datasheet.py`, using `wcl_fakes` responders for rankings (with `talents`/`gear`), casts tables, Casts events, Buffs tables and playerDetails:
  - query uses `leaderboard: LogsOnly`, `includeCombatantInfo: true` and `metric: playerscore` for mplus;
  - entries without a report are skipped;
  - medians and p25/p75;
  - `min_gap_s`;
  - uptime %;
  - stat medians;
  - talent pick rates / build hash shares;
  - sample under threshold → `sufficient=False`;
  - low budget halves the cohort;
  - cache hit on second call.
- [X] T078 [P] [US6] Author test in `backend/tests/test_guide_pipeline_run.py`: an ability id in a claim that is not in the data sheet is stripped to `None` by `build_brief` (FR-034), and observed claims carry scope text.

### Implementation for User Story 6

- [X] T079 [P] [US6] Add a `SPEC_RANKINGS` GraphQL query to `wcl_agent/queries.py`: `worldData.encounter(id).characterRankings(className, specName, metric, difficulty, partition, leaderboard: LogsOnly, includeCombatantInfo: true, page)` (research R5).
- [X] T080 [P] [US6] Add the `SPEC_DATASHEET` cache family (TTL 43200, key `wcl:v1:datasheet:{content_type}:{class}:{spec}:{patch_or_season}`) to `wcl_agent/cache.py`. Store the serialised `DataSheet` as the value (a `DataSheetCache` wrapper model in `wcl_agent/cache_models.py` holding the JSON dict, so `wcl_agent` doesn't import backend models).
- [X] T081 [US6] Implement `build_data_sheet(briefing) -> DataSheet` in `backend/app/services/guide_pipeline/datasheet.py` (research R5/R6, contracts/guide-pipeline.md §Data-sheet queries):
  - pick encounters: raid = the 4 current-tier encounters with the most rankings (Mythic, falling back to Heroic when < 50 entries); mplus = the 4 M+ dungeons with the most runs;
  - read page 1 of rankings (talents, gear, report refs);
  - choose a 20-player cohort (unique names, spread over encounters, halved when `benchmark.budget_size()` is low);
  - casts by source via `report_tools._player_table` (`REPORT_PLAYER` cache) + `benchmark.reduce_casts_entry` → cpm stats (factor a shared `median_range(values)` helper out of `benchmark.aggregate_measures` instead of duplicating it — Constitution I);
  - `events(dataType: Casts, sourceID)` for 5 players → `min_gap_s` for abilities with ≥2 casts and a gap ≥ 20 s;
  - Buffs/Debuffs tables → uptime %;
  - `playerDetails(includeCombatantInfo: true)` for 10 players → stat medians;
  - talent pick rates and build-hash shares from ranking `talents`, plus optional names from `settings.wcl_guide_talent_names_url` (cached `TALENT_NAMES` per build, off by default);
  - all inside `background_lane()`, cached via `SPEC_DATASHEET`.
- [X] T082 [US6] Feed the data sheet into the pipeline in `backend/app/services/guide_pipeline/__init__.py` and `authoring.py`:
  - build the sheet after the briefing (failure → `None`, logged; generation continues with `data_sufficient=False`);
  - pass `ds:*` facts to the author prompt (`format_data_sheet` in `prompts.py`, marking insufficient facts "not citable as guidance");
  - include the sheet in the evidence snapshot;
  - `build_brief` takes ability ids only from the sheet and sets `data_sufficient`.
- [X] T083 [US6] Implement the `datasheet` subcommand in `backend/evals/guides/__main__.py`: build the briefing and data sheet for the given spec and content type, and print a readable table (scope, sufficiency, abilities cpm/gap, uptimes, top builds, stats).

**Checkpoint**: Briefs contain measured benchmarks and verified ability ids.

---

## Phase 9: User Story 7 - Automatic checks stop inconsistent guides (Priority: P2)

**Goal**: Deterministic checks gate publication. A failure triggers one revision and then `failed` with a recorded reason; US9 later turns this into the review loop (FR-036..FR-038).

**Independent Test**: One fixture per defect (unknown ability, far-off cooldown, wrong patch/season, PTR source, pre-hotfix source, unreferenced claim, missing log check, brief too long, extra guide claim) each produces the matching `CheckFailure`, and the guide is not published.

### Tests for User Story 7

- [X] T084 [P] [US7] Check tests in `backend/tests/test_guide_pipeline_checks.py`: one test per check in contracts/guide-pipeline.md §Deterministic checks, plus a clean-pass fixture. Include the edge rules: `ability_unknown` skipped when the data sheet is insufficient; the charges relaxation for `cooldown_mismatch`; `source_prehotfix` skipped when `latest_hotfix_at` is None.

### Implementation for User Story 7

- [X] T085 [US7] Implement `run_checks(briefing, claims, brief, brief_text, markdown, data_sheet, fact_sheet) -> list[CheckFailure]` in `backend/app/services/guide_pipeline/checks.py`. The checks are `ability_unknown`, `cooldown_mismatch` (0.8× / 2.5× rules), `patch_mismatch`, `season_mismatch`, `source_env`, `source_prehotfix`, `claim_unreferenced`, `log_check_missing`, `brief_too_long` and `guide_extra_claim` (every rendered bullet's claim-id comment maps to a claim).
- [X] T086 [US7] Implement `revise_claims(briefing, sheets, claims, failures, issues=()) -> AuthorResult` in `backend/app/services/guide_pipeline/authoring.py`. It makes one tool-less structured call with `REVISE_PROMPT` (added to `prompts.py`): fix or remove the listed claims, and cut the lowest-confidence items if the brief is too long.
- [X] T087 [US7] Integrate in `run_guide_generation` (`backend/app/services/guide_pipeline/__init__.py`): render → `run_checks` → (on failures) one `revise_claims` → re-render → re-check → still failing → `fail_spec_guide("check:<first check>")` with `review_issues` set to the failures. Published version untouched.

**Checkpoint**: No guide with a structural defect can be published.

---

## Phase 10: User Story 8 - Research limited to current, trustworthy sources (Priority: P3)

**Goal**: A tiered, allowlisted, version-filtered fact sheet, where hard filters run in code before the author sees anything (FR-039..FR-044).

**Independent Test**: With fixture grounded results containing a PTR page newer than live, a Classic page, an other-content-type page, a tier-4 forum post and a pre-hotfix page, none appear among the evidence the author receives, and all are recorded in `fact_sheet.dropped` with reasons.

### Tests for User Story 8

- [X] T088 [P] [US8] Research tests in `backend/tests/test_guide_pipeline_research.py`:
  - tier assignment by domain;
  - Wowhead never in the `url_context` allowlist and snippet items capped at low confidence;
  - the five drop reasons;
  - an equal-tier conflict recorded and both items marked unconfirmed;
  - tier-4-only facts not citable;
  - ranking order (patch match before freshness);
  - `url_context` only when `wcl_guide_research_fetch_enabled` is true (Blizzard always allowed);
  - injected instructions inside evidence are kept as text and flagged, never followed.

### Implementation for User Story 8

- [X] T089 [US8] Add `SOURCE_TIERS` (domain → tier, fetch-allowed flag) and `ENV_MARKERS` (PTR/beta/Classic URL path and title patterns, e.g. `/ptr`, `ptr-2`, `/classic`, `wotlk`, `cata`, `mop-classic`, `beta`, "Classic") in `backend/app/services/guide_pipeline/research.py`, per research R14.
- [X] T090 [US8] Implement `hard_filter(items, briefing) -> (kept, dropped)` and `rank_evidence(kept, briefing)` in `backend/app/services/guide_pipeline/research.py`:
  - drop wrong product or environment;
  - drop a patch older than live major.minor (or a different patch-level for hotfix-sensitive topics);
  - drop the wrong class, spec or content type;
  - drop items dated before `latest_hotfix_at` when `hotfix_touches_spec` (else flag possibly stale);
  - tier 4 is kept only as non-citable discovery;
  - equal-tier conflicts go to `conflicts`;
  - sort by relevance, patch match, tier and date.
- [X] T091 [US8] Upgrade `build_fact_sheet` in `backend/app/services/guide_pipeline/research.py` to the two-call flow (research R3):
  - the grounded collect call with `url_context` gated by setting and allowlist (the prompt lists allowlisted domains and tells the model to fetch only those);
  - the structured extraction into `EvidenceItem`s with tier, env and patch tags;
  - `hard_filter` + `rank_evidence`;
  - cache via a `GUIDE_RESEARCH` cache family (`wcl_agent/cache.py`, TTL 21600, key includes content type, class, spec, patch, hotfix timestamp);
  - include open inaccuracy reports as "claims to verify" once US10 provides them (parameter defaults to empty).
- [X] T092 [US8] Ensure the author never sees dropped or tier-4 items: `format_fact_sheet` in `prompts.py` lists only citable items, with ids. Persist `dropped` in the evidence snapshot for the leakage metric.

**Checkpoint**: Wrong-version material is structurally unavailable to the author.

---

## Phase 11: User Story 9 - Independent review and correction before publishing (Priority: P3)

**Goal**: A stronger, different reviewer verifies every claim against the evidence for up to 3 rounds. Passing guides publish; others are held as `needs_review` with issues. The UI shows the last verified guide or the warned draft, and the agent never sees drafts (FR-045..FR-049).

**Independent Test**:
- A seeded-error draft (wrong cooldown, removed talent, unsupported claim, raid tip in an M+ brief) has every error fixed or removed within ≤3 rounds.
- An unfixable draft ends `needs_review`. The viewer shows the published guide plus a "held" notice, or the draft with a warning when no published version exists.
- `get_coaching_brief` returns the published brief or `no_brief`.

### Tests for User Story 9

- [X] T093 [P] [US9] Review-loop tests in `backend/tests/test_guide_pipeline_review.py` (faked `generate_structured`):
  - verdicts are applied (contradicted → revised, unconfirmed → removed and added to `unconfirmed`);
  - stops early on a pass;
  - stops at `wcl_guide_max_review_rounds` → `hold_spec_guide` with issues;
  - the reviewer model differs from the author model (startup warning when equal);
  - the reviewer prompt contains only cited evidence and the "your own knowledge is not evidence" rule;
  - publish happens only when all remaining claims are confirmed and checks pass.
- [X] T094 [P] [US9] Visibility tests in `backend/tests/test_guides_api_v2.py` and `backend/tests/test_guides_tool.py`:
  - `needs_review` with a published version → `display=published`, and status reported;
  - without a published version → `display=draft` + `review_issues`;
  - `load_brief_record` never returns a draft.

### Implementation for User Story 9

- [X] T095 [US9] Add `REVIEW_PROMPT` to `backend/app/services/guide_pipeline/prompts.py` (verify, not write; judge only against the cited evidence text and data-sheet values shown; return a verdict per claim with the evidence ids used; flag content-type mismatches). Implement `review_claims(briefing, claims, data_sheet, fact_sheet) -> ReviewResult(verdicts, issues)` in `backend/app/services/guide_pipeline/review.py`, using `settings.wcl_guide_review_model`.
- [X] T096 [US9] Replace the single-revision flow in `run_guide_generation` with the loop from contracts/guide-pipeline.md §Loop: for each round ≤ `wcl_guide_max_review_rounds`, run checks + review; if every claim is confirmed and there are no failures, publish; otherwise revise. When rounds are exhausted, call `hold_spec_guide(draft={brief, claims, markdown, briefing, generated_at}, review_issues=…)`. Removed claims' sections go into `brief.unconfirmed`. Add a startup warning in `backend/app/main.py` when `wcl_guide_review_model == wcl_guide_model`.
- [X] T097 [US9] Show drafts and held updates in `frontend/src/components/profile/GuideViewerDialog.tsx` (contracts/ui-guides.md):
  - `display=draft` → warning `StatusAlert` "Unverified draft — these areas could not be confirmed:" + the `review_issues` list above the markdown;
  - `needs_review` with a published version → a small notice "An update was held for review; showing the last verified guide.";
  - library row badges per the guides-api.md status table in `ClassGuidesTab.tsx`.

**Checkpoint**: Only reviewed, evidence-confirmed guides reach users as verified or reach the agent.

---

## Phase 12: User Story 10 - Guides stay current and users can report errors (Priority: P3)

**Goal**: Patch, season and hotfix changes mark guides stale. In-use guides regenerate immediately and others on next open. Users report inaccuracies, the next regeneration judges them, and maintainers see them (FR-050..FR-055).

**Independent Test**:
- Setting a row's `game_patch` older than live → after the library loads, `stale_reason=patch_changed`.
- A row with recent `last_wanted_at` regenerates; another regenerates only when opened.
- A submitted report appears in the admin list and is `fixed` or `rejected` after regeneration.

### Tests for User Story 10

- [X] T098 [P] [US10] Stale-scan tests in `backend/tests/test_stale_scan.py`:
  - `patch_changed`, `season_changed` (mplus only);
  - `hotfix` (class-wide and spec-specific; not for untouched specs);
  - `legacy` kept;
  - throttle (second call within 10 min is a no-op);
  - in-use rows → `ensure_guide(force=True)`, others untouched;
  - opening a stale guide queues regeneration;
  - `last_wanted_at` stamping is throttled to once per hour.
- [X] T099 [P] [US10] Report tests in `backend/tests/test_guide_reports.py`:
  - POST creates an `open` report (201), CSRF required, 5–500 chars, 404 without a published version, 429 over the limit;
  - the admin list requires a platform admin and filters by status;
  - the reviewer verdict sets `fixed`/`rejected` + `outcome_note` + `resolved_at`.

### Implementation for User Story 10

- [X] T100 [US10] Implement `maybe_scan_stale_guides()` in `backend/app/services/guide.py` (contracts/guide-pipeline.md §Staleness):
  - in-process throttle (10 min, monotonic clock);
  - read live patch, season and hotfix (cached);
  - set `stale_reason` on published rows;
  - for stale rows with `last_wanted_at` ≥ now − `wcl_guide_inuse_days`, call `ensure_guide(..., force=True)`;
  - spawn via `background.spawn` with key `"stale-scan"`.

  Call it from `GET /api/guides` (backend/app/api/guides.py), `_build_turn_preamble` (backend/app/api/ws.py) and a startup boot step (backend/app/main.py).
- [X] T101 [US10] Implement `touch_guide_wanted(keys)` in `backend/app/services/guide.py`: a batched, throttled `last_wanted_at` update in a plain session, spawned non-blocking. Call it from:
  - the guide GET route (and queue regeneration there when the guide is stale and not pending — FR-051 "on next open");
  - `run_character_guide` after spec resolution;
  - `_build_turn_preamble` for injected briefs;
  - `load_brief_record` callers via the tool (a stamp callback passed alongside the loader).
- [X] T102 [US10] Add repository helpers to `backend/app/db/repository.py`: `create_guide_report`, `list_open_guide_reports(class, spec, ct)`, `resolve_guide_report(id, status, outcome_note)` and `list_guide_reports(status)`. Add a `guide_report_limiter = InProcessRateLimiter(per_minute=settings.wcl_guide_report_per_minute)` in `backend/app/auth/rate_limit.py`.
- [X] T103 [US10] Add `POST /api/guides/{class_name}/{spec}/{content_type}/reports` to `backend/app/api/guides.py`, and the new router `backend/app/api/admin_guides.py` with `GET /api/admin/guide-reports` (`require_platform_admin`, `GuideReportAdminOut` in `backend/app/schemas.py`). Register the router in `backend/app/main.py`.
- [X] T104 [US10] Feed open reports into generation:
  - `run_guide_generation` loads them and passes them to `build_fact_sheet` (claims to verify) and `review_claims`;
  - the reviewer returns `report_verdicts[{report_id, status, reason}]`;
  - after the run (publish or hold), `resolve_guide_report` each judged report.

  Files: `backend/app/services/guide_pipeline/__init__.py`, `research.py`, `review.py`, `prompts.py`.
- [X] T105 [P] [US10] Create `frontend/src/components/profile/ReportGuideDialog.tsx` (`Dialog` + `Field` + `Textarea` with a 5–500 character counter + `Button`, CSRF via `reportGuide`, success and 429 `StatusAlert`, focus return). Add a "Report an inaccuracy" button to the published view in `GuideViewerDialog.tsx`.
- [X] T106 [US10] Show `stale_reason`-based freshness and the "Refreshing" state in `ClassGuidesTab.tsx` and `GuideViewerDialog.tsx`: the "May be out of date" title text names the reason (patch, season or hotfix).

**Checkpoint**: Guides stay fresh at bounded cost, and users can flag errors that the pipeline then judges.

---

## Phase 13: Polish & Cross-Cutting Concerns

- [X] T107 [P] Update the docs:
  - `README.md`: feature 015 section covering guides per content type, the accuracy-check command and the new settings;
  - `documentation/ai_guide.md`: the guide pipeline overview and the agent's brief contract;
  - `.env.example`: verify the new settings are present.
- [X] T108 [P] Log one structured INFO line per guide run in `backend/app/services/guide_pipeline/__init__.py`: class, spec, content type, outcome, rounds, check failures, claim counts (confirmed/removed), data-sheet sample size, evidence kept/dropped, duration, model ids. This is the input for SC-013 timing.
- [X] T109 Run the full suite (`backend/tests/`) with `uv run --extra test pytest -q` and `cd frontend && npm run build && npm run lint`, and fix any failures.
- [ ] T110 Run the release gate: `uv run python -m backend.evals.guides run --live-generate --specs Mage/Fire,DemonHunter/Devourer,Priest/Holy,Warrior/Protection --content raid,mplus`. Record the report path, gate verdict and deltas versus `baseline.json` (SC-001..SC-011) in `specs/015-grounded-class-guides/checklists/progress.md`. Iterate prompts and thresholds until the gate passes.
- [ ] T111 Walk through every story row of `specs/015-grounded-class-guides/quickstart.md` §3 and record the results in `checklists/progress.md`.
- [ ] T112 **Manual (maintainer)**: review the terms of Icy Veins (and Raidbots if talent names are wanted) before setting `WCL_GUIDE_RESEARCH_FETCH_ENABLED=true` / `WCL_GUIDE_TALENT_NAMES_URL` (research R5/R14). Record the decision in `checklists/progress.md`.
- [ ] T113 Run `node .gitnexus/run.cjs detect-changes --scope all --repo .` (re-run if `partial`/`truncated`), review the affected flows, then commit in scoped commits per phase.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)** → **Foundational (P2)**, which blocks all stories.
- **US4 (baseline)** must finish (T023 committed) **before merging** any later phase's behaviour change (FR-024). Its harness code can be built in parallel with US1 development.
- **US1** → needed by US2 (claims and the pipeline to build briefs from), US6, US7, US8, US9 and US10.
- **US3** is independent of US1/US2 (it touches the roster only). US1's briefing picks it up in T043.
- **US2** needs US1. Its tests seed briefs directly, so it does not need US5.
- **US5** needs Foundational and US2's brief fields (T052) for `season`/`unconfirmed`. The frontend tasks T068–T075 need T063–T065.
- **US6** needs US1 (pipeline) and US2 (`build_brief` ability ids).
- **US7** needs US1, US2 and US6 (`ability_unknown` / `cooldown_mismatch` use the data sheet; both are skipped gracefully when the sheet is insufficient).
- **US8** needs US1 and US7's `source_env` check (it shares `ENV_MARKERS`).
- **US9** needs US7 (it replaces the single-revision flow) and benefits from US6 and US8.
- **US10** needs US5 (API routes and viewer) and US9 (reviewer judges reports).
- **Polish** comes after all chosen stories.

### Story completion order (rollout, quickstart §4)

Setup → Foundational → US4 → US1 → US3 → US2 → US5 → US6 → US7 → US8 → US9 → US10 → Polish

### Within each story

Tests first (expected to fail) → models and repository → services → endpoints and tools → UI → manual check.

---

## Parallel Execution Examples

**Foundational**: T009 (patch helpers), T010 (pipeline models) and T011 (llm helper) touch different files. Run them together after T004–T008, then T012/T013 in parallel.

**US4**: T015, T016, T020, T021 and T022 in parallel; then T017 → T018 → T019 → T023.

**US1**: T024, T025, T026 (tests), T028 (cache families) and T031 (prompts) in parallel; then T027 alongside T029 → T030 → T032 → T033 → T034 → T035 → T036.

**US3**: T038, T039, T040 and T041 in parallel → T042 → T043 → T044.

**US2**: T045–T050 (all test files) together with T055 (classifier) and T058 (tool); then T051 → T052, T053 → T054, then T056 → T057, T059 and T060.

**US5**: backend T063 → T064 → T065/T066/T067; frontend T068, T069, T070 and T071 in parallel once T063 is fixed; then T072 → T073 → T074 → T075 → T076.

**US6**: T077, T078, T079 and T080 in parallel → T081 → T082 → T083.

**US10**: T098, T099 and T105 in parallel; T102 → T103; T100 → T101; T104 after T102.

---

## Implementation Strategy

### MVP first

1. Phases 1–2 (no behaviour change).
2. Phase 3 (US4): build the harness, hand-check the fixtures and **commit the baseline**.
3. Phase 4 (US1): live clock + briefing + dedicated author → **stop and validate** (the patch accuracy metric should reach 100% for regenerated guides).
4. Phase 5 (US3): Devourer and the roster.

The MVP is US4 + US1 + US3. It fixes the reported Devourer gap, the frozen clock and the patch guessing, measured against the baseline.

### Incremental delivery

5. US2: the agent gets whole briefs (the largest coaching-quality gain).
6. US5: Mythic+ guides and the UI.
7. US6 → US7: measured evidence and the structural gate.
8. US8 → US9: version-filtered research and the review loop (the full hallucination defence).
9. US10: freshness and the feedback loop.

Re-run the accuracy check after each step. The release gate (T110) must pass before the feature is considered done.

---

## Notes

- Total: 113 tasks. [P] marks tasks with no shared files and no dependency on an incomplete task.
- Every task names its file(s). Manual tasks (T023, T076, T110–T112) record results in `checklists/progress.md`.
- Never truncate a brief, never give a draft to the agent, never fetch Wowhead. These are hard rules from the contracts.
- Commit after each phase checkpoint, after running `detect-changes` (T113 pattern).
