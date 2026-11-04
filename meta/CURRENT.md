# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-04 (evening: Telemetry 2 about to start)

## Next sprint steer

Owner, 2026-11-04: "let's start Telemetry 2. Bring the PO in to discuss (and make sure the
telemetry stack is running before we start this session)". Plan: planning with Maren in the
room (read-only, challenge my view, side-by-side table), then launch. The session must run
under `bin/claude-otel` (owner restarts with `bin/claude-otel --continue`); check
`CLAUDE_CODE_ENABLE_TELEMETRY` in env before setup. Stack already up and healthy.

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D19, proposals P1–P11, baseline, change log).

## Where we are

- Sprint 2026-11-04 (Telemetry 1, epic 395) closed: 23/23 pts + D13 (3 pts, sc-439) added
  live on the owner's request. Merged into main (57c77ba) and pushed with the close-out (f5886ad) on the owner's go. Worktrees
  and sprint branches removed; QA reports copied to `qa-reports/2026-11-04*`. Owner moved
  all 10 stories to Done 2026-11-04 (I applied it); epic 395 done. The 24 older Under Review stories
  (2026-11-01b, 2026-11-02) also Done on the owner's word; board has none Under Review.
- Observability stack runs from main (`docker compose -p warcraftlogs-agent --profile
  observability up -d`), Grafana http://127.0.0.1:3000 with three dashboards: Claude Code:
  Overview, App: API and LLM, Agent Team: Improvement.
- Team history is now data: `uv run python .claude/team/teamstats.py` at every wrap-up
  (team-launch step 3). 1.17 M/pt, 7.5 min/pt (55-min unwatched question), Nils 268k
  context per call.
- Old Mimir series still carry user/account id labels (from before the Alloy restart);
  offered to wipe the volume, owner's call.
- The owner's `.env` SECRET_KEY is a placeholder: fine on localhost; tell the owner before
  any shared deploy.

## Open with the owner

1. Longer-lived Google credentials (service account) for live passes; offered to draft.
2. Wipe the pre-fix Mimir series? (local only)

## For the next sprint (mine)

- Telemetry 2 (epic 396, 23 pts) extends the starter dashboards (sc-408, sc-413 comments).
- Start the sprint session through `bin/claude-otel` so the team itself is observed.
- Render-check every report; restart config-reading services before live checks.
- Candidates: "Every chat request starts at about 23k prompt tokens" (sc-367), the chat
  input that stays locked after a drop (sc-376).

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
