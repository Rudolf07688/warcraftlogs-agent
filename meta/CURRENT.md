# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-10-31

## Topic

The agent-team redesign. The full record is in `meta/team-optimisation.md` (decisions
D1–D11, P1–P5, change log).

## Where we are

- **Implemented and committed:** the team board with its auto-inject hook (068d062), and
  the tiered team with sub-agent developers and the `/team-launch` skill (f107786).
- **Now:** making meta knowledge survive compaction and new sessions (this file, the
  SessionStart hook, `meta/owner-preferences.md`, `meta/sessions.md`, the per-sprint usage
  archives).
- **Next, per the owner:** "get real meta" and keep iterating on the team setup.

## Open threads

- The next real sprint verifies the redesign: does coordination fall below 41%, do
  developers without gates stay in their footprint, and are the tiers set right.
- Ask the owner about raising `cleanupPeriodDays`. Transcripts are deleted after 30 days by
  default.

## How to resume

1. Read `meta/README.md`, then this file, then the "Decisions", "Open questions" and
   latest "Change log" entries in `meta/team-optimisation.md`.
2. Owner preferences for team work: `meta/owner-preferences.md`.
