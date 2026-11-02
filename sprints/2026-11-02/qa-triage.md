# QA triage, sprint 2026-11-02 (Maren)

Sweep: qa-reports/2026-11-02-sweep/ (0 C, 1 H, 8 M, 17 L) at c6303b6. P7 reviews: qa-reports/2026-11-02/p7-05x-security.md.

## Fixed in the QA fix round (board #63, split by author)
| Finding | Owner | Why now |
|---|---|---|
| PERF-001 High: whole table neutralised before projection | Nils | regression from this sprint |
| PERF-002 Medium: look-alike table built on the event loop | Nils | regression from this sprint |
| PERF-005 Low: search cap() quadratic re-neutralise | Nils | regression from this sprint |
| SPEC-006, SPEC-007 Low: 050/044 contract drift | Nils | docs of own code |
| BUG-001 / SPEC-003 Medium: pre-fetch counts key runs as bosses | Tomas | breaks the kickoff warm-up (sc-358 goal) |
| PERF-003 Medium: pre-fetch compacts tables it discards | Tomas | made costlier by this sprint |
| BUG-003 Low: pre-fetch ignores the workspace skip | Tomas | interaction of this sprint's code |
| SPEC-004 Low: ws.py turn scratch outside guarded setup | Tomas | own new code (sc-357) |
| BUG-004 Low: investigate 429 shows "Is the backend up?" | Tomas | new 429 from sc-352 |
| SPEC-001, SPEC-002, SPEC-005 Medium/Low: 052 spec/contract drift | Tomas | docs of own code |
| BUG-002 Low: own_summary never set on unchanged refetch | Ansel | own new code (sc-354) |
| PERF-008 Low: _stale parses every queued write after a floor | Ansel | own new code (sc-353) |
| SPEC-008 Low: task lists not reconciled | all | docs |

## Deferred (qa-deferred, Backlog)
| Finding(s) | Ticket |
|---|---|
| sweep SEC-001 Medium + board #40: uploader text raw in other tools | new sc-368 |
| sweep SEC-002, SEC-003 Low: breaker identity gaps | new sc-369 |
| P7-051 Lows 1, 2 + sweep SEC-004 + PERF-007: tombstone floor, null batch, salvage | new sc-370 |
| sweep PERF-004 Medium (low confidence) + P7-051 Low 5: lookup cost / staleness | new sc-371 |
| board #49 + sweep hardening: M+ investigate per-user limit | new sc-372 |
| sweep BUG-005 Low: neutralised text in tracked-raid labels | new sc-373 |
| SPEC-009 + PERF-006 Low: kickoff prompt target / fights output size | breadcrumb on existing sc-367 (team-lead's) |
| Kickoff pre-fetch key runs (050 P7 side note) | fixed in QA round (BUG-001) |

No duplicates found among existing QA tickets: the nearest (sc-351, sc-353, sc-354, sc-355, sc-352) are this sprint's own stories, now Under Review; the new tickets name them as "Follow-up to". No "Not reported" comments: the sweep was scoped to this sprint's diff.
