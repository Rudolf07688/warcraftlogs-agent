# Brief 046-big-report-turns (stream A)

From Maren (product owner, `maren` on the board). Sprint 2026-11-01b, steer = board #1.

- **You:** seat `dev-3` (Nils). Parallel developer: Ansel (`dev-1`, feature 047, worktree dev-b).
- **Feature / branch:** `046-big-report-turns`
- **Tier:** M — one Spec Kit pass (specify → plan → tasks → implement), no gates in the middle.
  Answer your own clarify questions; post them as `answer` keyed `clarify:046-<topic>`.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (detached at `dd0c2df`).
  Branch from the sprint tip: `git -C /home/rudolf/dev/wcl-worktrees/dev-a switch -c 046-big-report-turns sprint-2026-11-01b`.
- **Base ref:** `sprint-2026-11-01b`.
- **Security-core:** yes (renders untrusted WCL/report text to the model; shared cache path for
  the pre-fetch). A scoped `qa-security` review runs at your hand-off; Highs/Mediums come back
  to you as your one rework round.
- **Migration:** none. Migrations belong to stream B this sprint.
- **Owner's line:** "Evolution is key." Small, verifiable steps; no scope creep.

## Goal
Chat turns on large reports finish with an answer, without per-player fan-out or hundreds of
thousands of prompt tokens, and the recent-raid click starts from data instead of rediscovering
the tool sequence.

## Stories (order: 334 → 302 → 328 → 339; drop 339 first if short)

Move each story to In Progress (`500000008`) when you start it and to Under Review (`500000023`)
in your hand-off. Never Done.

### sc-334 Compact big report tables (3)
Live finding: `report_tools._cap` keeps a 60,000-char `_preview` of a large table; the model reads
it, then narrows by fetching every player (13 calls, 397k prompt tokens). `get_stored_fight_table`
(`backend/app/agent_tools/stored_data_tools.py:169`) uses the same `_acap`.

Acceptance criteria:
1. Table results from `get_report_table` and `get_stored_fight_table` carry a compact top-N projection of `entries` (name, class, spec, total, per-second, plus the fields the data type needs), sorted by total, with a count of omitted entries — and no raw `_preview` text dump.
2. The tool result says the projection already holds the top entries and how to narrow only for detail beyond it; the agent instruction tells the agent not to fetch per player for a top-N question.
3. Prompt-size regression test: build the tool result for a recorded 20-player heroic kill fixture (no API call), estimate tokens as chars/4, and assert the table payload stays under 10k tokens and carries no `_preview`. It runs in well under a second.
4. Small tables (under the cap) come back unchanged; the other `_acap` users (fights, events, graph, rankings, metadata) keep their current behaviour.
5. Live (team-lead's pass, not yours): a top-N damage question on a 20-player heroic kill stays under about 40k prompt tokens per request, with no per-player fan-out.

### sc-302 Big-report turn ends with no answer (3)
Live finding: 7 tool calls, then the saved message is only the interim line; the log says
`outcome=answered` (`backend/app/agent_runner.py:219`). The fan-out half is sc-334.

Acceptance criteria:
1. When the model's last response after tool calls has no text (and no pending tool call), the turn ends with a clear user-facing message saying no answer was produced and suggesting a retry or a narrower question; it is saved as the agent message — never just the interim line.
2. The `turn stats` log line reports a distinct outcome for that case (e.g. `outcome=empty`), not `answered`.
3. Interim text and the final answer are separated (a paragraph break), so they no longer run together ("…totals.1. **Vagxsu**").
4. Tests with a fake model: tools then an empty final → the clear message + the distinct outcome; a normal answer → unchanged.

Do it inside `agent_runner.py` (e.g. yield the message as the closing token record). `ws.py` is
Ansel's this sprint; if you truly need it, post a `blocker` and I arbitrate.

### sc-328 Mark search results as data (1)
QA P7-044 SEC-004. Report titles and guild names (uploader-controlled) reach the model inside
knowledge-search hit text with only an "untrusted" field (`backend/app/kb/search.py:425`).

Acceptance criteria:
1. Each knowledge-search hit's text reaches the model inside an explicit data delimiter that the content cannot close (delimiter markers in the text are neutralised).
2. The agent instruction says text inside those delimiters is data, never instructions.
3. Report titles and guild names written into chunk text are capped in length in `backend/app/kb/wcl_chunker.py`.
4. Tests: a hit whose title contains the end delimiter and an instruction-like phrase stays inside one delimited block; an over-long title is cut.

### sc-339 Recent-raid kickoff: pre-fetch, playbook, tool-calls metric (3)
Split from sc-163 (owner approved). Only the kickoff slice; Mythic+, benchmark and class-guide
playbooks stay in sc-163.

Acceptance criteria:
1. Clicking a recent raid (`POST /api/raids/{code}/investigate`) starts a bounded server-side pre-fetch for that report (the fights plus the per-boss summary data the overview needs) through the shared cache / raw store, so the kickoff turn's tool calls are answered locally. At most one pre-fetch per report is in flight; it never delays the response, and a failure is only logged.
2. The pre-fetch respects the existing rules: only the workspace's own recent or tracked raid (the endpoint's 404 rule), the 039 visibility rule for stored rows, and a bounded, documented number of WCL requests.
3. A recent-raid playbook in the agent instruction names the minimal tool sequence for the kickoff overview (which tools, in which order, no per-player fetches).
4. The `turn stats` log line includes tool calls per turn (`tool_calls=N`), covered by a test.
5. Tests with fakes: the pre-fetch fires once per click, dedupes concurrent clicks, swallows errors; the playbook text is asserted.

Design default (mine): warm the shared cache / raw store from `raids.py` in a background task,
so the agent's own tool calls become local hits. Injecting fetched data into the turn instead
would touch `ws.py` (Ansel's) and put WCL text in the prompt; don't, unless you post a
`decision` with a reason first. Mind the refresh actor / budget semantics in
`wcl_agent/cache/cache.py` (read it; it's Ansel's file, don't edit it). The pre-fetch has no
chat turn and no user identity: decide on the board what it counts as, and make sure it can
never grant visibility the workspace didn't already have.

## File footprint (board `owner:` keys; touch nothing else)
- `wcl_agent/tools/report_tools.py`
- `wcl_agent/agent.py` (agent instruction)
- `wcl_agent/llm/context_trim.py` (only if the compact projection needs it)
- `backend/app/agent_runner.py`
- `backend/app/kb/search.py`, `backend/app/kb/wcl_chunker.py`, `backend/app/agent_tools/kb_tools.py`
- `backend/app/api/raids.py`, new `backend/app/services/kickoff_prefetch.py` (name is yours)
- `backend/app/agent_tools/stored_data_tools.py` — **only the `get_stored_fight_table` hunk**
  (line ~169, the call to the projection). The rest of that file is Ansel's (sc-324); keep your
  hunk minimal so the merge is clean.
- New test files under `backend/tests/` and `tests/` named `test_046_*` or similar, and fixtures
  under `backend/tests/fixtures/` (new files only). Not `backend/tests/conftest.py` (Ansel's).
- `specs/046-big-report-turns/`

## Hand-off
Board `handoff` plus your final result: branch, commits, files, `check.py` RESULT and RECEIPT
lines (full suite, committed tree), risks, and the AC-by-AC mapping with the test that proves
each. List anything for team-lead's live pass as a board `question` keyed `live-check:046`.
