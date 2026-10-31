# Session ledger

Claude Code session ids for team and meta work. The raw transcripts live in
`~/.claude/projects/-home-rudolf-dev-warcraftlogs-agent/<id>.jsonl` (plus `<id>/subagents/`),
but they're deleted after `cleanupPeriodDays` (30 days by default). The derived numbers
are archived in `meta/sprints/<date>/usage.txt` so they outlive the transcripts.

| Date | Session id | What |
|---|---|---|
| 2026-10-25 | 276b1986-87b3-4ee2-99ff-9c16b4e10bfa | First agent-team sprint (018–025). Also wrote the agent definitions. |
| 2026-10-26 | 01c58ede-43ca-4e4f-9bef-0845c4e59b3a | Sprint on epic 203, the self-aware agent (027–031) |
| 2026-10-31 | ecd2eba0-9ae8-417f-880a-0cc1c4c85b65 | Provider-switch sprint (032–035), then the meta redesign (board, tiers, persistence). Its `usage.txt` includes the meta discussion turns. |
