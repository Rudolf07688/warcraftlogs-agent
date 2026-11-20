# Brief 078-wcl-event-windows (dev-2 Tomas)

- **Feature / branch:** 078 / `078-wcl-event-windows`
- **Tier:** S x3, run in sequence in this one run (sc-570 first, then sc-574, then sc-573). No Spec Kit.
- **Model / effort:** opus, medium
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (detached at the base). **Base ref:** `d7dab27` (sprint-2026-11-20 tip at launch).
- **Seat:** dev-2 (Tomas). In parallel: Vera (079, Anthropic request), Edda (080, status line + stored answer), Ansel (081, boss mechanics), Nils (082, prompt).
- **Security-core:** no. A page cursor is something the model passes back to you, so treat it as a hostile input (below).
- **Migration:** none.

## Stories (acceptance criteria verbatim from the tickets)

### sc-570 (1 pt, bug): Event lookups with a start time always come back empty (paging and time windows broken)
`get_report_events` (wcl_agent/tools/report_tools.py) passes `startTime` to WCL but never `endTime`. With a `startTime` and no `endTime`, WCL returns no events at all: time-windowed pulls come back `data: []`, and page 2 via `nextPageTimestamp` is always empty. Reproduced live (report bjXfNc92d8CPGhvB, DamageTaken, fight 1, source 11, limit 5): no start → 5 events, next 821936; start 821936 no end → 0; start 821936 end 1e12 → 5, next 823155; start 1089000 no end → 0; with end 1e12 → 5.
- **Fix.** Whenever `start_time` is set, also send `endTime` (the fight's end, or a large bound; the fightIDs intersection keeps it inside the fight). Check `get_report_graph` / `get_report_table` for the same pattern.
- **Tests.** A unit test that the query variables carry an `endTime` whenever `startTime` is set. A live pre-check through team-lead: page 2 of the repro above returns events.

### sc-574 (2 pts, bug): Coach gave wrong Gravebound damage figures, corrected one answer later
The Gravebound answer said "about 30.9M unmitigated and about 20.7M overkill"; the next answer corrected it: "a single hit of 23.6M, about 21.3M after mitigation". Suspected (not verified): the start-time event pulls were empty (sc-570), so the agent read an aggregate table and mixed fields. Trace 147abbdc2d627e01a16e8a1786a75242.
**Do.**
1. Replay the turn's tool results from the trace and find which field the 30.9M came from.
2. If it is sc-570, close this as a duplicate after that fix and a re-run of the question.
3. Otherwise fix at the source: label the damage fields in the tool output (amount, unmitigated, absorbed, overkill) so the model cannot swap them, and add the case to the answer-judging live check (EXPECT pinned from `livecheck.py --facts bjXfNc92d8CPGhvB`).

PO notes: this is diagnosis first (spike shape). Data sources, read-only: `python3 .claude/team/obsq.py` (Tempo/Loki; the owner's stack may be down, then it can't reach anything) and the tool args in the ticket. If you can't read the trace's tool results, post `live-check:078-pre` asking team-lead to pull the tool results of trace 147abbdc… (the `get_report_table` / `get_report_events` calls) and to run the fixed `get_report_events` for the Gravebound window. "Close as duplicate" means: state the finding as a comment on sc-574, move it to Under Review with sc-570; never Done, never archive. If it is a field mix-up, the labelling fix is in scope; post EXPECT entries under `live-check:078` pinned to stored facts (`livecheck.py --facts bjXfNc92d8CPGhvB`, e.g. the hit's amount field), never to answer wording.

### sc-573 (2 pts, bug): Raid player list fails with a Warcraft Logs server error on Veritass's reports
`get_report_participants` failed 4 times in one turn with `WCL request failed: [{"message": "Internal server error", "locations": [{"line": 1, ...`, on the reports `list_stored_reports_for_character` returned for Veritass (Mythic+ and raid). Trace 9e66e7d1e4569fdf9dac8c0f120c48dc.
**Unknown, to find first:** Warcraft Logs-side, or our query. Reproduce on those report codes (from the trace's tool args) with the tool, then with a reduced query.
**Acceptance.**
- Root cause stated on the ticket.
- If ours: the tool returns participants on those reports; a test pins the query shape.
- If theirs: the tool retries once and then returns a short, typed error ("Warcraft Logs failed on this report's player list") the agent can relay in one line.

PO notes: you never call WCL yourself. Write the exact repro (the report codes from the trace, the tool call, then the reduced queries: `playerDetails(fightIDs:)` alone, with `endTime region`, per fight) as `live-check:078-pre` while you build sc-570; team-lead runs it at once. Fact `raid-summary-tool-keys`: the Raids page finds stored participant rows by recomputing your exact field text and variables, so a query-shape change empties that part unless you keep the keys in step (test_072 fails first). If you need `backend/app/services/raid_summary.py` or the WCL client (`wcl_agent/client/**`; `AsyncWCLClient.query` is effectively HIGH risk), post a blocker and I grant it.

## File footprint (board `owner:` keys, to tomas)
- `wcl_agent/tools/report_tools.py`, `wcl_agent/tools/participants.py`
- `backend/tests/test_participants_tool.py`, new `backend/tests/test_078_*.py`
Anything else is a blocker. Prompt budget share (contract:prompt-budget): +100 tokens of tool docstrings at most.

## Hostile inputs (the page cursor and time window come back from the model)
- `start_time` past the fight's end, negative, or 0 with a page cursor
- a `nextPageTimestamp` from another fight or report passed back as `start_time`
- `start_time` with no fight id (whole report): the `endTime` you send must not widen the window beyond what the caller asked
Assert on the variables actually sent to the fake WCL client (`wcl_fakes.install`), not on the tool's input.

## Live pre-check
If a question needs the real stack, post `live-check:078-pre` with the exact command while building; team-lead runs it at once. Never call WCL or read `.env` yourself.

## Stories on Shortcut
Move sc-570, sc-574, sc-573 to In Progress when you start, Under Review in your hand-off.

## Known facts
- **raid-summary-tool-keys** (file:wcl_agent/tools/participants.py): The Raids page summary (072) finds stored rows by recomputing the exact store keys our tools send: participants and player-details (fight 0), per-boss Summary tables (kickoff fights) and get_report_rankings with Rankings/Historical (fight 0 and per boss). A change to a tool's field text, variable declarations or variable names silently empties that part; test_072 stores rows from the tools' own fake-client calls, so it fails first.
- **boss-summary-shared** (report_tools.py::boss_summary): `get_report_fights` returns `last_kill` and `boss_summary` outside the cap; `kickoff_prefetch` imports `boss_summary`, so keep its signature and keys stable.
- **uploader-text-neutralise** (report_tools.py::neutralise): uploader-controlled WCL text reaches the model only through `neutralise`, then a cap. Neutralise after projecting, cap after neutralising.
- **wcl-player-actors-include-bystanders**: masterData Player actors include bystanders (subType "Unknown"); who raided is the union of fights' friendlyPlayers.
- **tool-docstring-is-prompt**: a tool's whole docstring is its model-facing description; test_064 caps instruction plus schemas; prompt text is pinned verbatim in several tests (test_050_report_fights also pins a docstring).
- **wcl-agent-no-backend-imports**: `wcl_agent` never imports `backend`.
- **wcl-fakes-install**: fake WCL with `backend.tests.wcl_fakes.install(monkeypatch, responder)`; the fake records `.calls` and `.count(needle)`.
- **cache-get-or-load-critical**: `get_or_load` / `_shared` are CRITICAL; keep changes additive (values, TTLs, locks untouched); run the cache tests before hand-off.
- **cache-single-flight-starter-context**, **redis-cache-tenantless**: shared flights run in the starter's context; the Redis cache is tenant-less.
- **pg-tests-shared-db**: Postgres tests share one DB; unique data, no exact global lists.
