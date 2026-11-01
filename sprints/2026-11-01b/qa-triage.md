# QA triage, sprint 2026-11-01b

Sources: P7 scoped reviews `qa-reports/2026-11-01b/p7-046-security.md`, `p7-047-security.md`;
final sweep `qa-reports/2026-11-01b-1615/` (README + 4 reports) at 22c7798. Totals of the sweep:
0 Critical, 1 High, 6 Medium, 14 Low. All reports are gitignored, in the sprint worktree.

## Fixed in the sprint
| Finding | Where fixed |
|---|---|
| P7-046 SEC-001 (Med) pre-fetch in interactive lane, no cooldown | 046 rework d118159 |
| P7-046 SEC-002 (Low) pre-fetch gated on writer, not store reads | 046 rework d118159 |
| P7-047 SEC-001 (Med) stale batch summary drops a private finding | 047 rework 462a9f3 |
| P7-047 SEC-005 (Low, regression) ws final save vs approve/cancel deadlock | 047 rework 635f0a7 |
| PERF-001 (High) = BUG-001 = SEC-001 kickoff turn stuck in background lane | 048 cf60bf8 |
| BUG-002 (Med) empty-answer message indexed / titled / suggestions | 048 cf60bf8 |
| BUG-003 (Med) compact tables drop nested lists silently | 048 cf60bf8 |
| SPEC-002, SPEC-006 (Low) 046 docs, outcome comment | 048 cf60bf8 |
| PERF-002 (Med) stored-reports scan unbounded (sc-324 AC2) | 049 5fba612 |
| SPEC-001 (Low) 045 breaker docs | 049 5fba612 |
| Board #73 probe-count timing flake | 049 5fba612 |
| Board #58 live-window flake | 047 dec7dec (cherry-picked on 046) |

## Deferred (all labelled `qa-deferred`, grouped by root cause)
| New ticket | Findings |
|---|---|
| sc-351 untrusted text outside the data block | P7-046 SEC-003, SEC-004; SPEC-005; hardening: uncapped names in report tools (related sc-267, sc-271) |
| sc-352 investigate rate limit, pre-fetch while breaker open | sweep SEC-002; PERF Low; P7-046 residual; hardening (schedule before commit) |
| sc-353 tombstone flooding, queue drops gone signals | P7-047 SEC-002; P7-047 hardening (queue full, null batch entries) |
| sc-354 stored-reports lookup: own-summary flag, grants-driven scan | P7-047 SEC-003; PERF Low (24 ms key re-check); 049 residual (#81) |
| sc-355 breaker counts one turn's parallel timeouts | P7-047 SEC-004; PERF Low (never opens when partly slow) |
| sc-356 dev secret default without env | P7-047 SEC-006 |
| sc-357 local-answer edge cases, ws setup reset | BUG Low; SPEC-004; P7-047 + sweep hardening (actor reset finally, final save outside error handling) |
| sc-358 kickoff request still ~55k tokens | PERF-003 (Med); PERF Low (playbook tokens) |
| sc-359 migration 0020 without CONCURRENTLY | BUG Low = PERF Low = P7-047 note |

## Matched to existing tickets
- sc-185 (composite tenant FKs): breadcrumb for `messages.conversation_id` plain FK (Ansel, board #57). Last seen 2026-11-01.

## Decided, no ticket
- SPEC-003 (pre-fetch dedupe per workspace+report, not per report): accepted as built (safer for per-workspace grants); comment on sc-339.
- Ansel #54 (check.py's .env refusal can be relaxed now): team tooling, passed to team-lead.

No duplicates found among existing QA tickets; nothing archived. "Not reported" comments skipped: the sweep was scoped to this sprint's diff.
