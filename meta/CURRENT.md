# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-08 (end of night after sprint 2026-11-07b; everything merged and pushed)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D22, proposals P1–P16, baseline, change log).

## Where we are

- Sprint 2026-11-07b: 25/25 pts merged to main (f11817e) and pushed. Its 10 stories are
  Under Review in iteration "2026-11-07b" (553); Done is the owner's call.
- After the merge: the bin migrate script runs `init_db` and explains a DB ahead of the
  checkout; team-launch step 5 hands the stack over on the sprint tip (owner's live-test
  workflow: `docker compose down` + `./bin/01_start_app.sh` in the main checkout).
- D2 "Claude Code: Agent Team" has a Decisions panel (who chose what, from the board).

## Next meta session

1. Seat review (P16 step 5) of the 11-07b retro proposals (Maren's two hostile-input classes,
   Vera, Ansel, Edda, Tomas, Nils) plus my `board.py … --instead "<Y>"` decision field.
2. P16 steps 2–4 (lessons that fire via hooks, fewer tools, cost per point by stream type).

## Next app sprint: candidates from the owner's live chat (2026-11-07)

- First: event pulls with a start time come back empty (sc-570, 1 pt, reproduced live).
- Speed and stability: prompt caching (sc-568), thinking status line (sc-569), empty answer
  when thinking uses up max_tokens (sc-567).
- Coach quality: boss-mechanic knowledge (sc-571, KB first, web search stays sc-380), tool
  chatter in answers (sc-572), raid player list server error (sc-573), wrong Gravebound
  figures (sc-574, may close with sc-570), too many clarifying questions (sc-575).
- Board tidy-up still open: sc-534 in Shortlist without iteration; iteration 536 still active;
  13 telemetry stories Under Review in iteration 472.

## Open with the owner

3. Wipe the pre-fix Mimir series? (local only)
4. Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

## How to resume

1. Read `meta/README.md`, then this file, then P16 in `meta/team-optimisation.md`, then
   `meta/sprints/2026-11-07b/team-report.html` (retro lines).
2. Owner preferences: `meta/owner-preferences.md`.
