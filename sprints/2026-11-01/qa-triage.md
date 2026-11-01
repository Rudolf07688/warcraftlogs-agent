# QA triage, sprint 2026-11-01

Maren (PO). Sweep: `qa-reports/2026-11-01-1258/` (sprint worktree, gitignored) at 7bfc119.
The four P7 reports in `qa-reports/2026-11-01/p7-*.md` count as known. Their deferred items are ticketed here too.
Totals: 0 Critical, 5 High, 9 Medium, 20 Low (34 findings).

## Fixed in the QA fix round (board #124)
| Finding | Severity | Who |
|---|---|---|
| SEC-001 = BUG-007 = SPEC-003: cache single-flight shares a grant-only store hit across workspaces | Medium | Tomas |
| BUG-001: ability-filtered tables chunked as full tables | High | Ansel |
| BUG-004: long guide heading loops forever on the event loop | Medium | Ansel |
| SPEC-006: 0019 message and research name the rejected `pg17` tag | Low | Ansel |
| SPEC-001 / BUG-003 (wording only): docs claim the backfill recovers dropped jobs | Medium | Ansel |
| BUG-002: a relaxation-pass timeout drops the hits already found | Medium | Nils |
| SEC-006: the eval DB guard compares URL strings | Low | Nils |

## Deferred: new tickets (Backlog, `qa-deferred`)
| Ticket | Findings | Pts |
|---|---|---|
| sc-318 | PERF-001/002/003/006/008 + P7 044 SEC-002 (kb-search-fair-pool): search cost grows with the corpus | 5 |
| sc-319 | PERF-004: query embeddings sent one after another | 1 |
| sc-320 | BUG-003/SPEC-001 (recovery), SPEC-008, PERF-011 + P7 043 SEC-002b/003/004 (kb-backfill-hardening, kb-dropped-jobs) | 3 |
| sc-321 | PERF-005/009: indexer throughput | 2 |
| sc-322 | SEC-002/SPEC-004: tombstone gaps, in-memory only | 2 |
| sc-323 | SEC-003: one slow probe opens the shared breaker | 1 |
| sc-324 | SEC-004/SEC-005/PERF-007: character lookup tool | 2 |
| sc-325 | BUG-005/006/008 + P7 044 SEC-003 (kb-character-realm): chunk identity and robustness | 3 |
| sc-326 | BUG-009: local-answer attribution | 1 |
| sc-327 | SPEC-005/007: docs for 044/045, task checkboxes | 1 |
| sc-328 | P7 044 SEC-004 (kb-hit-delimiters): delimit hit text, cap titles | 1 |
| sc-329 | P7 043 SEC-003 (pg-public-schema-create) + db-hide-parameters | 1 |

## Matches with existing tickets
- sc-270 (one set_config round trip): breadcrumb added for board `backlog:set-scope-one-statement` and PERF-010.
- No duplicates found among the open `qa-deferred` tickets (36 read), so nothing was merged or archived.
- In-scope existing tickets: sc-295 and sc-296 were delivered this sprint (Under Review). This sweep reports no regression of them; their follow-ups are sc-322 and sc-323. No "Not reported" comments were added, because the other open QA tickets are outside this sweep's scope.

## Not ticketed
- SPEC-002: the eval hasn't run on real vectors. Team-lead's live check 044(6) records the embeddings and runs it. A ticket follows only if that check fails.

## Board backlog notices that aren't QA (Backlog tickets, no `qa-deferred`)
- sc-330: one difficulty map (`backlog:difficulty-names`)
- sc-331: `find_encounter` through the shared matcher (`backlog:find-encounter-resolver`)
- sc-332: store counters per operation (`backlog:store-counters-per-op`)
