# Brief 050-report-fights-and-kickoff (stream A)

From Maren (product owner, `maren` on the board). Sprint 2026-11-02, steer = board #1
(fully autonomous: no owner questions at any point; decide and record on the board).

- **You:** seat `dev-3` (Nils). Parallel developers: Ansel (`dev-1`, feature 051, worktree dev-b)
  and Tomas (`dev-2`, feature 052, worktree `/home/rudolf/dev/wcl-worktrees/dev-c`).
- **Feature / branch:** `050-report-fights-and-kickoff`
- **Tier:** M: one Spec Kit pass (specify, plan, tasks, implement), no gates in the middle.
  Answer your own clarify questions; post them as `answer` keyed `clarify:050-<topic>`.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (detached at `3b5e3ca`).
  `git -C /home/rudolf/dev/wcl-worktrees/dev-a switch -c 050-report-fights-and-kickoff sprint-2026-11-02`
- **Base ref:** `sprint-2026-11-02`.
- **Security-core:** yes (marks uploader- and model-written text for the model). A scoped
  `qa-security` review runs at your hand-off; Highs/Mediums come back as your one rework round.
- **Migration:** none.
- **Spec dir:** `specs/050-report-fights-and-kickoff/`.

## Goal
"The last boss kill" means the last kill in the report, the recent-raid overview costs much less,
and no uploader-written text reaches the model outside the data marking.

## File footprint (stay inside; ask on the board before touching anything else)
- `wcl_agent/tools/report_tools.py`, `wcl_agent/tools/tools.py` (difficulty map only),
  `wcl_agent/game/**`, `wcl_agent/agent.py`
- `backend/app/kb/search.py`, `backend/app/kb/wcl_chunker.py`
- `backend/app/services/name_resolver.py`, `backend/app/services/profile_context.py`
  (difficulty map only)
- `backend/app/api/raids.py`: only `kickoff_prompt_for` (if the playbook text moves into the
  kickoff prompt for sc-358); the `investigate_raid` endpoint body is Tomas's (shared file, split by hunk)
- `specs/044-kb-search/contracts/**` (the search contract update), `specs/050-*/**`
- tests for these: `backend/tests/**` and `wcl_agent` tests, new files or files only you touch.
  `backend/app/services/kickoff_prefetch.py` is Tomas's (`pick_boss_fights` there already picks
  the last kill per boss; reuse its logic by moving it into `wcl_agent/game` only if you agree it
  on the board with Tomas first; otherwise leave it).

## Stories (order: 365, 330, 358, 351; drop 330 first if short)
Move each story to In Progress (`500000008`) when you start it and to Under Review
(`500000023`) in your hand-off. Never Done. ACs below are mine, derived from each ticket.

### Agent picks the wrong last boss kill (sc-365, 2, bug)
Ticket: live pass 2026-11-01b, report BKNtypgnhrxXvj84. Turn 1 ("top 3 damage dealers on the last
boss kill") used Ula'tek, fight 32 (correct). Turn 2, a top-5 bar chart on the same report, used
Den of Nalorakk, fight 2. The model chooses the fight. Suggested fix: have the fights summary mark
the last kill explicitly (e.g. `last_kill_fight_id`, kills ordered by end time); a test on a fixture
with several kills.
My code reading: `get_report_fights` returns every fight (trash too) through `_acap`
(`MAX_JSON_CHARS` 60,000). On a long night the list becomes a `_preview` text prefix that holds
only the early fights, so the last kill can disappear. Fights carry no start/end times. Confirm or
refute this first; "not this cause, with evidence" is a fine finding.
Acceptance criteria:
1. `get_report_fights` returns an explicit last-kill field (fight id, boss name, difficulty), chosen by the latest end time among boss kills (encounter id set, kill true); `null` when nothing was killed.
2. The last-kill field and a per-boss summary survive any capping: a fixture with many trash pulls and several kills, whose full list exceeds the cap, still shows the right last kill.
3. The agent instruction tells the model to use that field for "last kill / last boss" questions.
4. Tests on a multi-kill fixture (including a kill order that differs from fight id order if end times allow it), no network.
5. Live (team-lead's pass): both turns on BKNtypgnhrxXvj84 use the same, last killed boss.

### One difficulty id-to-name map (sc-330, 1, chore)
Ticket: the difficulty id->name map exists twice: `wcl_agent/tools/tools.py` `_DIFFICULTY_NAMES` and
`backend/app/services/profile_context.py` `_DIFFICULTY`; 044's name resolver imports the tools.py
one. Merge both into `wcl_agent/game` (e.g. `constants.DIFFICULTY_NAMES`).
Acceptance criteria:
1. One map in `wcl_agent/game`; both former definitions removed and every user imports it.
2. No output change: existing tests pass unchanged.

### Recent-raid kickoff answer still about 55k prompt tokens (sc-358, 2)
Ticket: compaction shrinks a Summary table about 4x (225 KB to 15.4k chars), but the kickoff answer
request is still about 55k tokens: each compacted Summary repeats the player list up to five times,
and per-player details plus the composition list are about 37%. Measured on the synthetic 20-player
fixture. Locations: `report_tools.py` (compact Summary projection), `agent.py` (RECENT_RAID_KICKOFF
playbook, ~330 tokens in every request). Suggested fix: a slimmer per-boss view for the kickoff (top
10 rows, no per-player details or composition), saving about 20k tokens; send the playbook text only
on kickoff turns.
Acceptance criteria:
1. The kickoff path uses a slim per-boss Summary view: at most 10 rows per list, no per-player details, no composition list, no repeated player list.
2. The kickoff playbook text is no longer in every request's instruction, only in kickoff turns.
3. Prompt-size regression test on the synthetic 20-player fixture: the kickoff answer request is at least 15k tokens (chars/4) smaller than today; record before/after in the hand-off.
4. Non-kickoff Summary requests keep their current shape.
5. Live (team-lead's pass): a recent-raid kickoff answers with a prompt under about 35k tokens.

### Untrusted text outside the data block (sc-351, 2, security)
Ticket: `backend/app/kb/search.py:73,319,417-427`: `source.label` (player names from the log) and
guide `section` headings sit outside `<data>`, only cut at 200 chars. Neutralising only plain `<`/`>`:
the replacements form look-alikes, and full-width or `&lt;/data&gt;` pass through. `wcl_chunker.py:359,382`.
`report_tools.py`: `get_report_fights` and compact tables carry titles/guild/player names uncapped and
unmarked (pre-existing). The 044 search contract shows hit text without `<data>`.
Suggested fix: neutralise and cap label/section (or move them inside the block); NFKC-normalise
before neutralising, or a per-call random marker; cap names in report tools; update the 044 contract.
Acceptance criteria:
1. Every search hit's label and section are inside the data block or neutralised and capped the same way as hit text.
2. Neutralising handles look-alikes: NFKC first, so full-width and entity-encoded delimiters can't close the block; tests for `</data>`, `＜/data＞`, `&lt;/data&gt;` and the replacement characters themselves.
3. Report tools cap uploader-written strings (report title, guild, player and fight names) to a stated length.
4. The 044 search contract matches the code.

## Live checks
Post one `livecheck` board entry per live AC (prompt, report code, EXPECT). For sc-365 use report
BKNtypgnhrxXvj84: EXPECT both turns name the same boss, the last boss killed (Ula'tek, fight 32 per
the ticket; confirm the last kill from the fixture or the stored summary if you can, without a live call).

## Hand-off
Board `handoff` plus your final result: branch, commits, files, the `check.py` RESULT and RECEIPT
lines, risks, AC mapping per story, and before/after token numbers for sc-358.
