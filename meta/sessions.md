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
| 2026-10-31 | 84278822-c396-4fc0-8dea-734725eec37e | Hardening sprint 2026-10-31b (037/038, pushed c614178) and local-first sprint 2026-10-31c (039, pushed 6f31f72); includes the crash recovery. Ids matched by commit times (2026-11-01). |
| 2026-11-01 | a6f10fe7-0fa2-4b01-9ffb-b9917cd504bd | Knowledge-base sprint 2026-11-01 (tier L, pushed ec58d90), retro, board close-out, session-boundary trial agreed |
| 2026-11-01 | 5f887f5b-3c0e-4240-8359-5507acf337d8 | First fresh meta session: tooling reflection, P9 "tools over rules" built (25fe6c1), sc-336 filed |
| 2026-11-01 | f6f1e132-ef58-44e1-9fd8-49f0643502f4 | Sprint 2026-11-01b (big-report turns + KB debt, 20 pts, tier M): planned with Maren in the room, owner preference 23 (ticket names); merged + pushed; retro → P10 (lighter PO admin) + P11 (live checks judge answers), pushed b8a6a54+ |
| 2026-11-02 | c88ddb6f-410c-4a10-ac79-a0cce79d1cd1 | Fully autonomous sprint 2026-11-02 (050–052, 20 pts, tier M, 3 devs); owner gave only the steer; merged 557e3b6 and pushed; team report + P10/P11 first trial readings; report shell CSS fixed after owner feedback; QA reports restored from transcripts |
| 2026-11-05 | 47e15afc-b142-40f2-9358-f15cbc9b75d1 | Meta session (owner asked for meta first after Telemetry 2) |
