# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-22 (P18 lexicon: harvest done)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D22, proposals P1–P16, baseline, change log).

## Where we are

- 2026-11-22: chat-reliability sprint (sc-580..587, 17 pts) merged to main a97631d and pushed
  on the owner's word. Stories Under Review. Team report:
  `meta/sprints/2026-11-22/team-report.html`. Cost 1.63 M/pt (fix round 3.74 = 13%; 1.41
  without it); 11-20 was 1.08.
- Deferred: sc-603..608 (sc-608 = Claude reads the owning boss as a location in the
  wrong-boss mechanic answer) + sc-436 flaky raw-store tests.
- New meta proposals from 11-22: livecheck in its own workspace (live-test chats pollute
  search_knowledge); facts.py stale skips facts re-stamped this sprint (Tomas); fix-round
  briefs name stories (3 devs + Maren); point QA follow-ups for the hardening.

## In discussion now

- **P18 team lexicon (owner idea, 2026-11-22).** A living "rosetta stone" the team owns and
  evolves. Owner chose pgvector (not Weaviate) and the harvest first; focus is the lexicon,
  later a "heatmap" of agents' semantic outputs. Harvest done: `.claude/team/lexharvest.py`,
  report `meta/lexicon/harvest-2026-11-22/report.html`. Findings: an ACK/GO/MERGED protocol
  was born and died with the scrum master; paths are the biggest repeat (~33k tok); status
  lines written 100 ways (grammar candidates); brief boilerplate. Proposed seed: places
  (@sprint …), status lines (TESTS, SEV, MERGED …), concept terms. Waiting on the owner's
  pick; then lexicon file + `lex.py` (propose/usage/budget). Step 2 idea: harvest the
  standing prompts (agent definitions), the biggest token lever.

- **P17 built and first run.** `member.py goal` + wrap-up step 10 "Teach"; Nils's 1:1 done (goal 1:
  volume test at the bound). Nils not seated 11-22, so his goal carries; follow up next wrap-up.

## Next meta session

1. The 11-22 proposals above, then the seat review (P16 step 5) of the 11-07b proposals.
2. P16 steps 2–4 (lessons that fire via hooks, fewer tools, cost per point by stream type).

## Open with the owner

- Board tidy-up: sc-534 now in iteration 576; iterations 536/553/472 still open.
- Wipe the pre-fix Mimir series? (local only)
- Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

## How to resume

1. Read `meta/README.md`, then this file, then P16 in `meta/team-optimisation.md`, then
   `meta/sprints/2026-11-22/team-report.html` (retro lines).
2. Owner preferences: `meta/owner-preferences.md`.
