# QA triage, sprint 2026-10-31b (Maren, PO)

The sweep covered `7989d61..bedc273`, i.e. the merged features 036 and 037. Reports are in
`qa-reports/2026-10-31b/`. Totals: 0 Critical, 2 High, 4 Medium, 18 Low. SPEC-002 and BUG-001
are the same finding.

## Fixed in 038 (one round, Tomas; all in 037 code apart from SEC-001)

| Finding | Severity | Why it's crucial |
|---|---|---|
| BUG-001 / SPEC-002 picture/srcset bypass of the remote-image block | High | It breaks sc-157's AC, and it's an exfiltration path |
| PERF-001 web-search sub-agent waits through the full schedule and never remembers the 429 | High | A latency regression introduced by sc-184 |
| BUG-002 a retry=False call (the greeting) poisons the 5-minute 429 memory | Medium | A correctness bug in new sc-176 code |
| BUG-003 + SEC-002 (code part) XFF ports and IPv4-mapped addresses; all-trusted chain falls back to the client-chosen `hops[0]` | Low | sc-158 silently fails, and the key can be spoofed |
| SEC-003 nested closing tags get through the title prompt delimiting | Low | It bypasses sc-179 AC2; the fix is a few lines |
| SPEC-003 admin invite limiter still keys on the direct peer | Low | A gap in sc-158's coverage; a one-line fix |
| SEC-001 `ws.py` sends `str(exc)` to the client | Medium | Pre-existing, but it's hardening (an information leak) and cheap |

## Deferred (new Backlog tickets, all labelled `qa-deferred`)

I compared each finding by meaning (paths, symptoms, IDs) against every open Team 1 QA
ticket (21, read during planning). Nothing matched an open ticket. The related tickets are the
sprint's own stories, now Under Review, so each residual gets a new ticket that links back to its
story instead of reopening it.

| Ticket | Findings | Pts | Related |
|---|---|---|---|
| sc-267 | SPEC-001 (Medium), SEC-004: realm and raid-label short directives; needs a known-realm check | 3 | sc-221 |
| sc-268 | PERF-002 (Medium): one wait budget per turn when both models are limited (also Tomas's backlog note #28) | 2 | sc-176 |
| sc-269 | PERF-003/005/006: roster scan, process-wide guide semaphore, one-query profile load | 2 | sc-225 |
| sc-270 | PERF-004/007: one `set_config` round trip; cache the parsed TRUSTED_PROXIES | 1 | — |
| sc-271 | SEC-005: guild summary inlined into the preamble unmarked | 2 | sc-221 |
| sc-272 | SEC-006: same-origin images can fire authenticated GETs | 1 | sc-157 |
| sc-273 | BUG-004: title lost after a symbol-only first line | 1 | sc-179 |
| sc-274 | BUG-005: same-role legacy rows collapse in proposal checks | 1 | sc-223 |
| sc-275 | SPEC-004/005/006: docs drift (approve write path, 15 cache families, fallback docs); also board #22 and #36 | 1 | sc-244 |
| sc-276 | Ansel's #36 follow-up: reset the refresh-actor contextvar per turn | 1 | sc-222 |
| sc-277 | SEC-002 (compose part): the backend port is published directly | 1 | sc-158, sc-146 |

There were no duplicates to merge and nothing was archived.

## "Not reported" comments

The sweep was scoped to the sprint diff, so it says nothing about the open QA tickets outside the
sprint. Those got no "Not reported" comment, because that would claim a check that never
happened. The 11 sprint stories each get a comment with the sweep result and a link to their
residual ticket.
