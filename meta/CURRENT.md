# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-02 ~18:50Z (session c88ddb6f: autonomous sprint done, merged locally)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P11, baseline, change log).

## Where we are

- Sprint 2026-11-02 ran fully autonomously on the owner's steer ("start and complete the
  sprint. No further interactions from me."). 20/20 pts, 14 stories Under Review in
  iteration 366; merged into main locally (557e3b6); **not pushed** (main is ahead of origin).
  Team report: `meta/sprints/2026-11-02/team-report.html`; sprint review in
  `sprints/2026-11-02/`. DB backup before migration 0021: `~/dev/wcl-backups/pre-sprint-2026-11-02.dump`.
- Readings: 1.27 M/pt (was 1.03), coordination 16% (lowest). Build cost rose because
  builders were resumed for the QA fix (fixed in `product-owner.md`). P10 near misses
  (Maren 0.134 M/pt, Shortcut 20%); P11 worked live (0 FAIL, found the soft kickoff miss).
- The owner's `.env` SECRET_KEY is a placeholder: fine on localhost, but the app now refuses
  to start with it off localhost (sc-356). Tell the owner before any shared deploy.

## Open with the owner

1. Push main (557e3b6 + wrap-up commit)? Preference 1: ask first.
2. Longer-lived Google credentials (service account) for the live pass; offered to draft.
3. Session boundaries: this sprint ran in its own fresh session with no compaction.

## For the next sprint (mine)

- Read the trial again: QA fixes in fresh agents (build per point back toward 0.6?), short
  developer results (Maren's Agent share 32% → < 15%).
- Candidates: "Every chat request starts at about 23k prompt tokens" (sc-367), "uploader
  text still raw in the other tools" (sc-368), breaker identity gaps (sc-369).

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
