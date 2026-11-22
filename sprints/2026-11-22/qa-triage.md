# QA triage, sprint 2026-11-22

Sources: QA sweep over 4fc12a3...f1835c4 (`qa-reports/2026-11-22/`: spec-conformance, bugs,
performance, security; local, gitignored), the two D18 reviews (085, 087) and team-lead's
live pass at f1835c4 (board #91: Claude 11/11 answered, Gemini 8 turns with 1 FAIL).
Full suite at f1835c4: PASS (2886 pytest with Postgres, 223 vitest, build).

Fix bar: a broken acceptance criterion, a security hole or data loss; Medium and above in new
code. Lows only when they sit in a hunk the fix round touches anyway.

## Fix round (088, three tier-S briefs, fresh runs on the authors' seats)

| Brief | Seat | Findings |
|---|---|---|
| 088a runner fixes | dev-4 Vera | BUG-001 (180 s cut after answer text saved as complete, Medium), BUG-003 (Gemini empty re-run after the turn answered, Medium), PERF-001 (heavy turns miss the history breakpoint: measure, fix if simple, Medium); in-hunk Lows BUG-007, BUG-008, PERF-007 |
| 088b status UI fixes | dev-5 Edda | SPEC-001 + PERF-003 (drop rechecks: window shorter than the server's drop detection; whole-chat re-render per recheck, Medium), SPEC-002 (retry notice hidden once answer text shows, Medium); in-hunk Lows BUG-004, BUG-005, BUG-006, PERF-004, SPEC-004 |
| 088c data fixes | dev-1 Ansel | BUG-002 (Raids page misses whole-report parses when the fight list moved, Medium), live F1 (mechanic miss on the wrong boss not said to the user: Gemini FAIL), live F2 (compare_player_to_cohort rejects the owner's own character by server: pre-existing, taken in, see decision:f2-cohort-server); in-hunk Low SEC-002 (URLs in note prose) |

## Not fixed (backlog, label qa-deferred)

| Group | Findings | Why not now |
|---|---|---|
| Claude call cost after a cut | PERF-002 (a cut discards billed thinking; the low-effort re-run rewrites the cache), SEC-003 (no per-turn wall-time bound; Gemini and non-streamed calls unbounded), PERF-006 (wrap-up request rewrites history) | Design trade-offs accepted in 084/087; need measurement on live data |
| Cache layout hardening | D18-087 SEC-001 (fake time block in user/preamble text), D18-087 SEC-002 + SPEC-003 (layout applies to greeting/guide/eval turns), D18-087 hardening (.get on head cache_control, shared turn-start helper test) | Low; no leak; accepted in scope:087:time-authority |
| Mechanic notes lint depth | SEC-001 (instruction lint is a denylist) | Low; notes are reviewed like code |
| Retraction residual | Vera's backlog:retraction-short-answer (short answer, then a lookup, then a closing line loses the answer) | No structural signal; options (a)-(c) |
| Rankings latency | PERF-005 (cold summary read before rankings) | Low; replaces a call that always failed |
| Status/socket pre-existing | D18-085 outside diff: meta frame sent with the setup session open (ws.py:455); live text shows in another open chat (MessageList.tsx:308); 085 SEC-001 residual (drop noticed after the last recheck) folded into 088b | Pre-existing |
| Flaky test | backlog:flaky-raw-store-races (test_raw_store_races same-tenant join, 1 in 4 runs) | Pre-existing, untouched code |

Docs: SPEC-005 (architecture docs stale) is the close-out docs pass; SPEC-006 (plan wording on
"nekzali gravebound") fixed by the PO in plan.md.

## Tickets (created 2026-11-22, Backlog, label qa-deferred)
- Claude call cost after a cut: QA 1122-A (sc-603)
- Cache layout hardening: QA 1122-B (sc-604)
- Notes lint depth: QA 1122-C (sc-605)
- Retraction residual: sc-606
- Status/socket pre-existing + rankings cold read (PERF-005): QA 1122-D (sc-607)
- Flaky raw-store test: merged into the existing flaky raw-store ticket sc-436 (renamed, description extended)
- Live re-check at 78d5c5a: all PASS except Claude wrong-boss wording (soft) -> sc-608, no second fix round.
