# Brief: QA fix round, backend telemetry (054 follow-up)

- **Branch:** `qa-fix-nils`, created in your worktree from the sprint tip: `cd /home/rudolf/dev/wcl-worktrees/dev-b && git checkout -b qa-fix-nils sprint-2026-11-04` (tip `c212475`; your 054 branch is already merged).
- **Tier:** S (short plan, then implement; no Spec Kit). Seat `dev-3` (Nils). Ansel (dev-1) runs a parallel fix round on `observability/**`, compose, `bin/**` and `.env.example` only.
- **Security-core:** yes (content policy path); make each test bite (mutation).
- **Stories:** follow-ups to the bootstrap and content-policy stories (sc-402, sc-406; they stay Under Review). No ticket moves needed.
- **Sweep reports** (read only the sections named): `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-04-sweep/` performance.md PERF-001, bugs.md BUG-003.

## Fix these (and nothing else)
1. **PERF-001 (High): the dev content log event resends the whole conversation history on every LLM round.** Redacting it costs 13 ms at 5 turns, 146 ms at 50 turns, per round, holding the GIL on the export thread, and Loki rejects records over 64 KB (content lost). Bound it: the cost of redacting one content log record and its exported size must not grow with the conversation length (e.g. cap the record's total content before scrubbing, keeping the newest messages, and mark the truncation). Spans keep their existing per-attribute cap. Dev must still carry the current round's prompt, reply and tool I/O. Test: a 50-turn history record is exported under 64 KB, its redaction stays under a small fixed time bound, and the newest message is present.
2. **BUG-003 (Medium): shutdown with a slow or hung collector takes ~8–9 s and grows with the backlog.** Bound the whole telemetry shutdown (all providers together) to a fixed total of at most ~3 s, whatever the backlog; on timeout, drop the rest. Test with a hung exporter and a backlog.

Not in this round (tickets): PERF-002 regex prefilter, BUG-004 cancellations as errors, BUG-005 standalone health/session traces, the 054 review Lows, sweep SEC-007 residual.

## Footprint
`backend/app/telemetry/**`, `backend/tests/test_telemetry*.py`. Nothing else (no `main.py`, `ws.py`, `generation.py`, `pyproject.toml`, `.env.example` this round; ask on the board if you must).

## Proof and hand-off
Tests for both items, mutation-checked; `check.py run --as nils` on the committed tree for the receipt. Board `handoff` with key `status:qa-fix-nils`, and the final result: branch, commits, files, RESULT/RECEIPT lines, a finding-by-finding mapping.
