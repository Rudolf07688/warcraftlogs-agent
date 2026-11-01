# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-01 18:55 (sprint 2026-11-01b wrapped in session f6f1e132; merge question with the owner)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P9, baseline, change log).

## Where we are
- **Sprint 2026-11-01b wrapped** (20/20, 1.03 M/pt, P9 held: 0 green-that-wasn't, 0 wake-ups,
  lint 14 → 3; report meta/sprints/2026-11-01b/team-report.html). Was: (first P9 trial): 20 pts, tier M, Maren + Nils (big-report
  turns) + Ansel (.env tests, KB debt). Branch `sprint-2026-11-01b` at dd0c2df, board of the
  same name. Planned with the PO "in the room" first (owner asked for both viewpoints).
- Owner preference 23: name tickets for the owner, never bare ids (dd0c2df).
- 25fe6c1 + 99df14d are pushed (origin/main = 99df14d): push question closed.

- The fresh-session hand-off worked (2nd boundary now): nothing settled was re-asked.
  Session ids: `meta/sessions.md` (back-filled to today).
- **P9 built** on the owner's go: `check.py` (clean runs, receipts, `verify --index`),
  `pg.py`, `mutate.py`, `guards.py`, `board.py wait`, `member.py lint` (read-only),
  `.gitnexusignore` (GitNexus skipped `wcl_agent/cache/`). Agent files and team-launch use
  them. All tested on real runs; probe confirmed a sub-agent's own background job wakes it.
- Measured: full suite 101 s in a clean worktree (all green); hook 40 ms; `pg.py up` 6 s.
- Filed **sc-336**: the suite reads the real `.env` in the main checkout (21 failures, live
  Model Garden calls). Added a prompt-size test AC to **sc-334**.

## Open with the owner

1. **Longer-lived Google credentials** (service account) for the live pass; I offered to
   draft the exact permissions.
2. **Session boundaries** on trial: one session per sprint, separate meta sessions.

## For the next sprint (mine)

- Candidates: sc-336 (small, makes every run clean) and sc-334.
- Watch P9: "green that wasn't" (target 0), my wake-ups (fallback only), receipt reuse at
  merges, `lint` lines before and after wrap-up.
- P8: split my spend by activity. Cheap token-budget check before the live pass.

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
