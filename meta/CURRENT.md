# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-10-31 (end of sprint 2026-10-31b)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D16, proposals P1–P6, baseline table, change log).

## Where we are

- **Sprint 2026-10-31b finished:** 21/21 pts of hardening + QA debt (036, 037, 038 fixes) on
  branch `sprint-2026-10-31b` (tip d15ecf7). Not merged to main yet; awaiting the owner's merge
  answer. Cost per point 0.83 (from 1.39), coordination 29% (from 41%), zero escalations.
  Team report: `meta/sprints/2026-10-31b/team-report.html`.
- **Team members now exist:** Maren (po), Ansel (dev-1), Tomas (dev-2), each with a first
  memory with "Autonomy lessons". Lead memory updated (crash recovery).
- **D15:** the whole team has the autonomy grant (owner preference 16).
- **D16:** team-lead owns `.env` and live testing (owner preference 17). Provider is now
  `anthropic` with a key. First live pass done; found sc-289 (tool_start flood).
- **Incidents:** machine crash mid-sprint (recovered, nothing lost); a VS Code setting
  injected `.env` into shells (owner set it to false; restart the session to clear it).

## Open threads

- Owner: merge `sprint-2026-10-31b` to main? Then push (owner asks explicitly).
- Owner decisions from Maren's report: accept the SEC-001 trade-off and sc-221 AC5 as partial.
- Next sprint idea from the report: tier-S security fixes get one bypass attempt before
  hand-off and at merge.
- Memory quality review after a few sprints (open question 3).

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
