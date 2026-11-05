# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-05 evening (retro done, knowledge layer built; main pushed 7aadd21)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D20, proposals P1–P13, baseline, change log).

## Where we are

- Telemetry 3 merged to main 6b1a465. **Owner ended the telemetry epic** in the retro.
  Stories Under Review (Done is the owner's). Main pushed by the owner's word (7aadd21).
- Retro → **P13 / D20, owner go: team knowledge layer, built and committed.**
  `.claude/team/facts.py` plus 66 facts in `.claude/team/facts/`, anchored to symbols, files
  and components. They surface in briefs (`facts.py brief`), on demand (`for`) and at every
  commit (pre-commit hook). `stale`/`verify` run at close-out. Agents write facts directly
  (owner preference 25); I curate. Also `jobwait.py` (warm waits on developers' long jobs),
  cost per stream in the PO's sizing, and a `Retro:` line in every hand-off. All of it is
  wired into developer/PO/SM.md and team-launch.
- GitNexus on main was rebuilt with `--force --no-parse-cache` after an incremental run left
  a nameless index. team-launch now checks a known symbol after each analyze.

## REMIND THE OWNER

- **Full-team retro is next** (see NEXT below).

## Sprint 2026-11-05b (merged to main bb22117, unpushed)

- 10/10 pts, live 4/4 PASS, cost 1.19/pt, cold 0.44 (P12 target met), P13 first trial: 4 facts
  added, 0 stale. Team report meta/sprints/2026-11-05b/team-report.html. Worktrees removed,
  stack runs from main, GitNexus reindexed (sound). Stories Under Review (Done is the owner's).
- Owner decision open: sc-512 (embed region vs a pinned model location).

## NEXT: full-team retro (owner asked, 2026-11-05, "after compaction")

Relaunch each member by seat, read-only (team-launch wrap-up step 8): Maren (po), Ilse (sm),
Ansel (dev-1), Tomas (dev-2), Nils (dev-3), Vera (dev-4). Give each: the sprint numbers
(team-report.html), their own `Retro:` line (PO final report; board export
meta/sprints/2026-11-05b/board.jsonl), and their `member.py lint --seat` lines. Ilse sat out
this sprint: ask for her view on the tier-S shape and the PO's coordination share (35%).
Relay views side by side with mine; then delete reminder-full-team-retro memory.
My topics: small fact-loaded streams as the default shape; coordination share on small
sprints; EXPECT pins facts not patterns; tool follow-ups (mutate.py vitest, npm ci in check.py,
prompt-pin helper, lib.sh facts in obs briefs); PO credentialed-call routing.

## Open with the owner

1. Wipe the pre-fix Mimir series? (local only)
2. Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

Set aside (owner, 2026-11-05): long-lived Google credentials. The owner signs in when
needed (ADC lasts about 24 h); keep the pre-flight token check and ask for
`! gcloud auth application-default login` when it fails.

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
