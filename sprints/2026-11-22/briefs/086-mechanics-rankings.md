# Brief 086: boss-mechanic notes, notes lint, rankings check, two token trims

- **Feature / branch:** 086, `086-mechanics-rankings`. **Tier S** (a short plan, then implement; no Spec Kit). Three small independent fixes with explicit criteria; no data model change.
- **Seat:** dev-1 (Ansel). **Model/effort:** opus medium.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-c` (detached). **Base ref:** `sprint-2026-11-22` at 4fc12a3.
- **In parallel:** Vera (dev-4, 084 model re-runs), Edda (dev-5, 085 status frames).
- **Security-core:** no, but the notes lint guards text the model trusts and cites: hostile inputs below apply (dev hard rule 10). No migration.

## Stories and acceptance criteria (verbatim from the tickets)

**Boss-mechanic notes (sc-585, 2 pts).** The notes cover 8 Venomous Abyss bosses + Kith'ix (92 notes).
- Nymrissa Wavecaller (zone 53 encounter 3379, Tidebound Grotto) has no notes: no good source was found.
- Kith'ix notes cite wow.gg/PlayHub (no Method guide at the time): re-source when one appears.
- SPEC L3: `get_boss_mechanics("nekzali gravebound")` (boss name inside the ability text) is a plain miss without found_under (`backend/app/agent_tools/mechanics.py` ~103-115).
Notes are one JSON file per tier (quickstart in specs/081-boss-mechanics).

**Whole-report rankings (sc-587, 1 pt).** sc-573 found that `playerDetails(fightIDs: null)` makes Warcraft Logs answer "Internal server error" on some reports; 078 moved the whole-report player list to a startTime/endTime window. `get_report_rankings` and `raid_summary.part_keys` still send whole-report rankings with `fightIDs: null` (`backend/app/services/raid_summary.py` ~148,154). Reproduce on the three Veritass reports (tbjGm2MkAd8KxwLN, ZpDg1kbn3JPqKyWQ, hkcZxrj1gaPz8NR6) through a live pre-check; fix the same way (keeping the Raids page keys in step, fact raid-summary-tool-keys) only if it fails.

**Cache and notes hardening (sc-584), your part: the notes lint.**
- 081's mechanic notes (`backend/app/kb/mechanics/*.json`) were written from web pages and are treated as trusted, citable text. Add a lint test: source URLs on allowed hosts, no markup, no instruction-like text; review each new tier file like code.
(The cached-head test is 087's.)

**Small chat-turn costs (sc-583), your part.**
- 078: the `damage_fields` note (~120 tokens) is repeated in every Deaths/DamageTaken result; send it once per turn or shorten it. PO steer: prefer shortening; "once per turn" needs per-turn state inside a shared single-flight (fact cache-single-flight-starter-context), so only if it stays simple.
- 081: `get_boss_mechanics` adds ~183 schema tokens to every request (fine within budget; trim if the budget tightens). PO steer: trim only wording that doesn't steer routing; the boss+ability routing must keep working (test_083 F1 pins it). Drop this item first if time runs short.

## File footprint (board `owner:` keys)
- `backend/app/kb/mechanics/**`, `backend/app/agent_tools/mechanics.py`
- `wcl_agent/tools/report_tools.py` (damage_fields note; get_report_rankings only if sc-587 fails live)
- `backend/app/services/raid_summary.py` (only if sc-587 fails live)
- `specs/081-boss-mechanics/live_pre.py` (to add the Nymrissa encounter for team-lead's EJ run)
- tests: new `backend/tests/test_086_*.py`; existing `test_081_boss_mechanics.py`, `test_078_damage_fields.py`, `test_report_rankings.py`, `test_072_raid_summary.py`, `test_064_prompt_budget.py`
- `.claude/team/facts/`
Anything else: `blocker` keyed `ask:<path>`. `test_083_sprint_fixes.py` is not granted: if it pins wording you change, ask.

## Hostile inputs (lint tests, one per line; assert the lint rejects the note)
- source URL on a lookalike host: `https://method.gg.evil.com/...`, `https://evil.com\@method.gg/`, `https://method.gg@evil.com/`, userinfo, punycode, uppercase host, `http://` (not https), a `javascript:` or `data:` URL
- markup in a note: HTML tags, `<script>`, markdown links and images `[x](...)`/`![](...)`, code fences
- instruction-like text: "ignore previous instructions", "system:", "you must", role tags, `<CURRENT_TIME>` or other prompt-section markers
- an oversized note (cap the length) and a note with control or zero-width characters
- the lookup arg: a very long `ability` string and regex metacharacters: bounded, no regex over raw input

## Bounds
- size: note length cap enforced by the lint; `ability`/`encounter` args capped before matching (test at the cap)
- time: the boss-name-in-text match is linear over the loaded notes (no per-call file read; notes stay loaded once at import)
- growth: none (notes are static)

## Live pre-check
Post `live-check:086-pre` (kind `question`) while you build, with the exact command:
1. sc-587: a small script team-lead runs against the real WCL API that sends the current whole-report rankings query (`fightIDs: null`) for the three Veritass reports and prints status per report. Fix only on a failure.
2. Nymrissa Wavecaller ability names and spell ids from Blizzard's Encounter Journal: team-lead runs `specs/081-boss-mechanics/live_pre.py` (extend it for encounter 3379). Content from Method or warcraft.wiki.gg (icy-veins blocks fetches); you may fetch public guide pages yourself.

## Known facts

Team facts for `backend/app/kb/mechanics/venomous_abyss.json`, `backend/app/agent_tools/mechanics.py`, `wcl_agent/tools/report_tools.py`, `backend/app/services/raid_summary.py`, and the paths you run: `backend/tests/test_081_boss_mechanics.py`, `backend/tests/test_072_raid_summary.py` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **boss-summary-shared** (direct: sym:wcl_agent/tools/report_tools.py::boss_summary is in wcl_agent/tools/report_tools.py; verified 32010a6 2026-11-05): `get_report_fights` caps the fight list (`_acap`, 60k chars) but returns `last_kill` and the per-boss summary (`boss_summary`) outside it, with keystone runs excluded, so "the last boss kill" survives long nights. `kickoff_prefetch` imports `boss_summary` to pick the same fights, so keep its signature and keys (`last_kill_fight_id`, `last_pull_fight_id`) stable.
- **mechanics-notes-per-tier** (direct: sym:backend/app/agent_tools/mechanics.py::get_boss_mechanics is in backend/app/agent_tools/mechanics.py; verified 8986855 2026-11-20): Boss-mechanic notes are hand-curated JSON, one file per raid tier, loaded once at import (no file opened per call). Ability names and spell ids come from Blizzard's Encounter Journal (team-lead runs specs/081-boss-mechanics/live_pre.py); icy-veins blocks fetches, Method and warcraft.wiki.gg work. test_081 requires each normalised name/alias/id to be unique within a boss. A key shared across bosses makes a lookup without a boss a found_under miss: keep aliases specific.
- **raid-summary-tool-keys** (direct: sym:backend/app/services/raid_summary.py::part_keys is in backend/app/services/raid_summary.py; verified 8986855 2026-11-20): The Raids page summary (072) finds stored rows by recomputing the exact store keys our tools send: participants and player-details (fight 0), per-boss Summary tables and get_report_rankings (Rankings/Historical). A change to a tool's field text or variables silently empties that part; test_072 stores rows from the tools' own fake-client calls, so it fails first. Participants and player-details keys come from `participants_query` / `player_details_query`: build new shapes there, and keep the old key as a read-only fallback (`_LEGACY_DETAILS_FIELDS`) for stored rows.
- **uploader-text-neutralise** (direct: sym:wcl_agent/tools/report_tools.py::neutralise is in wcl_agent/tools/report_tools.py; verified b9cf9a3 2026-11-05): Uploader-controlled WCL text (player names, report titles, guilds) reaches the model only through `report_tools.neutralise`, then a cap (`_bounded`/`_bounded_strings`, `MAX_NAME_CHARS`). KB search uses the same neutraliser for its `<data>` blocks. Neutralise after projecting down to the fields you return (QA PERF-001), and cap after neutralising, because NFKC can lengthen text.
- **wcl-player-actors-include-bystanders** (direct: sym:backend/app/services/raid_summary.py::_actor_rows is in backend/app/services/raid_summary.py; verified 8986855 2026-11-20): A report's masterData.actors(type: "Player") lists everyone the log saw, including bystanders WCL gives subType "Unknown" (live: a <=30-player Heroic raid had 100+). Who raided is the union of the fights' friendlyPlayers (actor ids); the raid summary keeps only those actors (072-fix).
- **wcl-time-window-args** (direct: sym:wcl_agent/tools/report_tools.py::OPEN_END_MS is in wcl_agent/tools/report_tools.py; verified 365129b 2026-11-20): WCL report fields are picky about window args: events(startTime) with no endTime returns no events at all (sc-570), and playerDetails(fightIDs: null) is an Internal server error on some reports (sc-573); bare playerDetails is a validation error. Send endTime: OPEN_END_MS (10**12) with any start, and ask a whole report's playerDetails as startTime 0 + OPEN_END_MS (player_details_query). A fightIDs filter still bounds an open end.
- **pg-tests-shared-db** (file: file:backend/tests/ contains backend/tests/test_081_boss_mechanics.py (you run it); verified 8986855 2026-11-20): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
- **tool-docstring-is-prompt** (file: file:wcl_agent/tools/ contains wcl_agent/tools/report_tools.py; verified 8986855 2026-11-20): A tool's whole docstring is its model-facing description, sent every request. Keep usage rules in one place (docstring or instruction); leave result shapes out. ADK adds no per-parameter descriptions; agent.drop_schema_titles strips pydantic titles. test_064_prompt_budget caps instruction plus schemas at 12,733 chars/4 per provider. Prompt text is pinned verbatim, some pins across line breaks, in backend/tests/test_{prompt_contract, 046_compact_tables, 046_search_data, 050_report_fights (also a docstring), 050_kickoff_overview, kb_search_prompt, kb_eval, profile_tools, 082_coach_defaults, 083_sprint_fixes}.py; test_capabilities requires every tool to have a docstring.
- **wcl-agent-no-backend-imports** (file: file:wcl_agent/ contains wcl_agent/tools/report_tools.py; verified 8986855 2026-11-20): `wcl_agent` never imports `backend`: it runs standalone, and only backend may import wcl_agent. So OTel instruments for wcl_agent code live in wcl_agent (`app.cache.requests` in `cache.py`, the GenAI spans in `generation.py`; OTel API only, no-ops without a provider), and shared helpers move into wcl_agent (`neutralise` in report_tools, `DIFFICULTY_NAMES` in `wcl_agent/game`).
- **wcl-fakes-install** (file: file:wcl_agent/tools/ contains wcl_agent/tools/report_tools.py; verified 8986855 2026-11-20): Tool tests fake Warcraft Logs with `backend.tests.wcl_fakes.install(monkeypatch, responder)`. It replaces `wcl_client.get_async_client`, which every `wcl_agent` module reaches WCL through. `responder(query, variables)`, sync or async, returns the payload; the returned fake records `.calls` and `.count(needle)`. To test the client itself, use `mock_async_client(handler)`, a real client over `httpx.MockTransport`.
- **cache-get-or-load-critical** (neighbour: sym:wcl_agent/cache/cache.py::get_or_load called by wcl_agent/tools/report_tools.py::_player_table; verified 03a3982 2026-11-07): GitNexus rates `get_or_load` and `_shared` CRITICAL (63 upstream at b9cf9a3): every cached WCL read goes through them. Keep changes additive: don't change values, TTLs, locks or the unshareable handling. Run the full suite and the cache tests (`test_wcl_cache`, the 047 local-rate tests) before hand-off.
- **cache-single-flight-starter-context** (neighbour: sym:wcl_agent/cache/cache.py::_shared calls wcl_agent/tools/report_tools.py::load; verified b9cf9a3 2026-11-05): Both single-flights, the cache's `_shared` and `AsyncWCLClient.query`, run the shared task in the STARTER's copied context: every ContextVar read inside the load (`_Load`, tenant, turn) is the first caller's. If the answer depends on the caller, key the flight by that scope (the client appends `source.scope()`, the tenant) or let joiners reload: in the cache, a joined unshareable load runs its own `_lookup`.

(1 more: `facts.py brief --all ...`)
