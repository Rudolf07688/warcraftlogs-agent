# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-04 (sprint 2026-11-04 launched: Telemetry 1)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P11, baseline, change log).

## Where we are

- Sprint 2026-11-02 ran fully autonomously on the owner's steer ("start and complete the
  sprint. No further interactions from me."). 20/20 pts, 14 stories Under Review in
  iteration 366; merged into main (557e3b6) and pushed on the owner's go, with the wrap-up commits.
  Team report: `meta/sprints/2026-11-02/team-report.html`; sprint review in
  `sprints/2026-11-02/`. DB backup before migration 0021: `~/dev/wcl-backups/pre-sprint-2026-11-02.dump`.
- Readings: 1.27 M/pt (was 1.03), coordination 16% (lowest). Build cost rose because
  builders were resumed for the QA fix (fixed in `product-owner.md`). P10 near misses
  (Maren 0.134 M/pt, Shortcut 20%); P11 worked live (0 FAIL, found the soft kickoff miss).
- The owner's `.env` SECRET_KEY is a placeholder: fine on localhost, but the app now refuses
  to start with it off localhost (sc-356). Tell the owner before any shared deploy.

- 2026-11-04: architecture docs rebuilt as index + 13 pages, checked at `1df8f6f`; close-out
  step added (PO wrap-up 5, team-launch gate 4, preference 24, `.claude/team/archdocs.py`).
  First real use: next sprint's wrap-up.

- 2026-11-04 (later): telemetry/observability planned with Maren (read-only co-plan) and the
  owner. Plan locked in `specs/telemetry_spec.md` §14: 3 sprints, 23/23/20 pts, epics 395–397,
  27 stories in Backlog. Owner: board only, no sprint yet; wrapper `bin/claude-otel`; content
  capture ON in dev; persistence (volumes + Alloy file queue) before Grafana.
- 2026-11-04 12:30Z: sprint-2026-11-04 launched (Telemetry 1, 23 pts). Branch from 38606fd,
  worktrees sprint/dev-a/dev-b, board sprint-2026-11-04, Maren resumed with planning context.
  gcloud ADC refreshed by the owner at launch (verified).
- 14:27Z: 053 merged 4412117, 054 merged c212475 (1 security rework round). Live pass PASS
  (board #43); found pre-existing KB embedding timeout via telemetry (sc-428). Waiting: QA sweep, wrap-up.

## Open with the owner

1. Longer-lived Google credentials (service account) for the live pass; offered to draft.
2. Session boundaries: this sprint ran in its own fresh session with no compaction.
3. Owner feedback after the sprint: reports were unreadable (shell CSS bug, fixed a2c0ce5)
   and the team report gained an "Earlier sprints" tab on request. Owner: "Well done".

## For the next sprint (mine)

- Render-check every report (headless screenshot per tab) before sending paths.
- Read the trial again: QA fixes in fresh agents (build per point back toward 0.6?), short
  developer results (Maren's Agent share 32% → < 15%).
- Candidates: "Every chat request starts at about 23k prompt tokens" (sc-367), "uploader
  text still raw in the other tools" (sc-368), breaker identity gaps (sc-369).

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
