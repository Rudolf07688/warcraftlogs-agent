# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-10-31 (pre-restart)

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

- **Owner grant (2026-10-31):** team-lead has autonomy. Act on my own judgment by default
  (see `meta/team/lead.md`, owner preference 15).
- **Session restart** done after aa4a951…2e1087b. If you're reading this after the
  restart, everything above is committed. Pick up from the open threads below.

## Open threads

- Only `lead` is claimed. The product owner and developers pick their names on the next
  team launch.
- **Done (D14):** team-lead now has the `lead` seat, a memory without a persona:
  `meta/team/lead.md`, 273 of 500 words, seeded with seven lessons. `team-launch` reads it
  first, and the SessionStart hook injects it during meta work.
- The next real sprint verifies everything: the coordination share against 41%, footprint
  discipline, the tiers, and the board and memory in practice.
- Memory quality review after a few sprints (open question 3).

## How to resume

1. Read `meta/README.md`, then this file, then the "Decisions", "Open questions" and
   latest "Change log" entries in `meta/team-optimisation.md`.
2. Owner preferences for team work: `meta/owner-preferences.md`.
