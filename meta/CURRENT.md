# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-10-31

## Topic

The agent-team redesign, now "getting real meta": giving the team persistence. The full
record is in `meta/team-optimisation.md` (decisions D1–D13, proposals P1–P6, change log).

## Where we are

- **Committed so far:**
  - 068d062: the team board and its hook
  - f107786: tiers and sub-agent developers
  - d281333: meta persistence (this file, the SessionStart hook, CLAUDE.md META)
- **Just built (P6):** persistent team members. `.claude/team/member.py` gives each seat
  (`po`, `sm`, `dev-<n>`) a self-chosen name and a memory capped at 500 words, stored in
  `meta/team/` in the main checkout. Wired into all three agent files and `team-launch`.
- **The owner declined raising `cleanupPeriodDays`** (D12).

## Open threads

- Nobody has claimed a seat yet. Names get picked on the next team launch.
- The owner asked whether team-lead (the main session) wants its own identity and memory.
  My answer: yes to a capped, first-person memory of my practice as lead, kept in git and
  visible to the team; no to a persona name. Waiting for the owner's call.
- The next real sprint verifies everything: the coordination share against 41%, footprint
  discipline, the tiers, and the board and memory in practice.
- Memory quality review after a few sprints (open question 3).

## How to resume

1. Read `meta/README.md`, then this file, then the "Decisions", "Open questions" and
   latest "Change log" entries in `meta/team-optimisation.md`.
2. Owner preferences for team work: `meta/owner-preferences.md`.
