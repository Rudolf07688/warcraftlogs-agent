# QA triage, sprint 2026-10-26

Sweep: `/qa-sweep` (all four agents) over the sprint diff `cf370e8..cec5e61`, run from
`/home/rudolf/dev/wcl-worktrees/sprint`. Reports: `qa-reports/2026-10-26/` (README.md is
the index). Totals: 0 Critical, 2 High, 7 Medium, 25 Low. On cec5e61 the tests stand at
1171 passed / 6 skipped / 1 deselected, and the frontend at 12 passed with a clean build.

I spot-checked FN-1 and FN-2 in the code myself: `ProfileChangeIn.realm` is a required `str`,
`_check` reads `change.name` before validation, ADK 2.10 leaves failed list items as dicts, and
`_decide` reads `before` outside the row lock.

## Crucial findings (owner decision 2026-10-26: no fix round; all deferred)

The owner was leaving and decided to wrap up: there's no QA fix round this sprint, and every
finding goes to the board for next time. The four items I'd have fixed now are filed as
`qa-deferred` tickets. Each is marked "Crucial, found in sprint 2026-10-26 QA", with file:line,
and has the priority the owner set. They were compared against sc-219..225 and the 14 older QA
tickets first: none duplicates them (sc-242 links to the related sc-225).

| # | Ticket | Findings | Why it's crucial | Priority | Est |
|---|---|---|---|---|---|
| FN-1 | **sc-241** QA BUG-001/SPEC-001/SPEC-002: one invalid proposal item crashes the profile tool and the chat turn | BUG-001 = SPEC-001 (High), SPEC-002 (Medium) | Correctness bug in new code on the owner's example path: a null realm (which the participants tool emits by design) or "Healer" crashes the tool and the turn. You get no card and a raw Python error, and the valid items are lost. It breaks 029 AC 3 / D4 / C12. | **High** | 2 |
| FN-2 | **sc-242** QA BUG-002/SPEC-003/SEC-006: overlapping approvals post the follow-up twice or return 500 after applying | BUG-002 = SPEC-003 = SEC-006 (Medium) | It can return 500 "Couldn't apply" after the profile changed, or post two lines. It breaks 031 FR-013 / SC-002. | Medium | 2 |
| FN-3 | **sc-243** QA BUG-003/SPEC-011: proposal card in the wrong chat after a mid-turn switch; misleading tool status | BUG-003 (Medium), SPEC-011 (Low) | A write-action card can show in the wrong chat, and the status says "Searching Warcraft Logs" during a profile proposal. | Medium | 2 |
| FN-4 | **sc-244** QA SPEC-006/007/009/010: architecture docs and contracts are stale for the self-aware agent | SPEC-006, 007, 009, 010 (Low, docs) | The architecture pages and the contracts don't describe the new write path (RLS table count, frame, tools, routes). SPEC-008 (ai_guide §6/§7) matched **sc-172** and was added there as a breadcrumb rather than duplicated. | Low | 1 |

Ranking (plan.md): sc-241, sc-242 and sc-243 sit at the top of the QA tier (#55a–c), above all the other QA tickets. sc-221 (SEC-001/002/003) is the top deferred security item and comes right after them. There's no re-check step this sprint.

Breadcrumb comments on the Under Review stories point the owner's live test at these: sc-205 → sc-241, and
sc-207 → sc-242, sc-243, sc-219.

## Deferred: board changes (owner rule 2026-10-25: no duplicates, `qa-deferred`, ranked below non-QA work)

I compared each deferred finding with the 14 existing QA tickets (sc-156, 157, 158, 159,
176–185: label `qa-deferred`, "QA" in the name, plus their IDs, paths and symptoms). **None
matched by meaning**: the sweep covered only epic-203 code, which no existing ticket is about.
There were no updates and no merges. Related findings from this sweep went into one ticket each.

### Created (Backlog, type bug, `qa-deferred`, Priority Lowest, First/Last seen 2026-10-26)

| Ticket | Findings | Est | Labels |
|---|---|---|---|
| sc-219 QA BUG-004/005/006, SPEC-004, PERF-007/008: confirmation card state edge cases | 409/cross-tab stale card, loose-card placement, client-clock expiry, re-renders, chunk size | 3 | ui |
| sc-220 QA BUG-007/SPEC-005, PERF-001/PERF-004: turn preamble budgets and cost with many friends | RECENT RUNS budget starves raids; codes push players out; brief lookups scale with friends | 3 | backend, ai, performance |
| sc-221 QA SEC-001/002/003: harden the agent profile write path against injected log text | untrusted titles in preamble; unbounded class/spec on the card; loose realm rule | 3 | security, ai |
| sc-222 QA SEC-004/005: reset the agent identity context and add user-level RLS on profile_proposals | ContextVar never reset; tenant-only RLS predicate | 2 | security, data |
| sc-223 QA SEC-007/BUG-008: profile cap race and legacy realm-spelling duplicates | check-then-insert caps; slug duplicates collapse | 2 | data, backend |
| sc-224 QA PERF-002: cache get_report_participants lookups | uncached playerDetails per call (design follow-up) | 1 | performance, ai |
| sc-225 QA PERF-003/005/006: proposal approve and read DB round trips, guide job fan-out | ~160 round trips per 30-item approve; extra read transactions; guide fan-out | 2 | performance, backend |

### Existing QA tickets not reported in this sweep (breadcrumb added, left open)

- sc-156, 157, 158, 159, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185 each got a
  breadcrumb "Not reported in QA sweep 2026-10-26", noting that the sweep was scoped to the
  sprint diff and didn't re-check them.
- Extra context in the breadcrumbs: sc-177 (participants fetches feed raw_fetches; see
  sc-224), sc-178 (still the gate for sc-129), sc-180 (the related chat-switch card bug is
  fixed in FN-3), sc-185 (profile_proposals' Postgres RLS tests also skip in CI; see sc-222).

### Merges

None. No duplicate QA tickets exist.

### Other board notes from this sprint (not QA)

- Filed earlier in the sprint: sc-213 (charts not restored on chat reopen, with a triage
  comment), sc-214 (per-item card selection), sc-215 (bubble caps in rem), sc-216 (shared
  naive-timestamp helper). sc-175 got the 390px measurements.
- SPEC-008 overlaps the ai_guide part of sc-172 (stale facts). It's recorded there as a breadcrumb
  (two comments: first seen, then the correction that it wasn't fixed this sprint).
