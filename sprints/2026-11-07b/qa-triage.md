# QA triage, sprint 2026-11-07b (PO Maren)

Sweep: `qa-reports/2026-11-07b-sweep/` (spec, bugs, perf, security; gitignored) over
516aa0d...0f91900. D18 reviews at hand-off: `qa-reports/2026-11-07b-d18/` (072, 074, 075, 076).
Live pass at 539d21a (team-lead, board #156): 38 PASS, 3 FAIL.

## Fix round (one round, fresh developers, base 0f91900)

| Fix | Finding(s) | Owner seat | Files |
|---|---|---|---|
| 072-fix | Live F1 = BUG-001 = SPEC-002 (High): participants include every Player actor; filter by the fights' friendlyPlayers. Live F2 backend = BUG-002 (Medium): class ignores the stored ranking's class. | dev-3 Nils (fresh) | backend/app/services/raid_summary.py, test_072_* |
| 073-fix | Live F2 frontend = SPEC-001/BUG-002 (High): null class printed as "null"; contract types (class_name, encounter nullable). PERF-001 (Medium, same files): tab switch refetches, can trip the 60/min limit; small cache + in-flight dedupe. Lows in the same hunks: 429 message (SPEC Low), Analyze enabled while offline (BUG-L4). | dev-2 Tomas (fresh) | frontend/src/api/raidSummary.ts, components/raids/**, pages/RaidsPage.tsx, App.tsx (L4 only) |
| 075-fix | Live F3: welcome page renders no portrait img while /profile renders 8 (sweep suspects a harness artefact: browse.py blocks external images and ClassAvatar drops a failed img). Reproduce first with live-shaped data; fix if real, else record the finding. | dev-1 Ansel (fresh) | WelcomePanel.tsx(+test), hooks/usePortraits.ts(+test), ClassAvatar.tsx(+test) |

## Below the bar: deferred (tickets, label qa-deferred)

Grouped by root cause; see the ticket list in the sprint review.
- **Raid summary hardening (072):** D18 SEC-003 (grant from store answer in a race), SEC-004
  (stored_summary_exists reveals other workspaces' summaries via timing), SEC-006 (GET triggers WCL
  call + writes, SameSite=Lax); sweep PERF-002 (payload decompressed 4x), PERF-003 (re-verify per
  older raid, false "Nothing stored" during cooldown), PERF-004 (newest-summary read serialises
  all candidates); BUG-L6 (batch-stored summary can't become visible in-request); SPEC Lows (FR-007
  and plan out of date; fetched_at hidden without duration).
- **Portraits hardening (075):** D18 SEC-003 (no in-process memo without Redis; per-request
  semaphore), SEC-004 = sweep SEC-003 = BUG-L5 (usePortraits cache survives logout); BUG-L2 (cancel
  counted as token failure); perf Lows (new HTTP client per lookup).
- **Turn serialization follow-ups (076):** D18 SEC-005 (ADK producer cleanup unbounded), SEC-006
  (same-workspace member can cancel another's turn), backlog capture-link-by-turn = SPEC-004;
  BUG-L3 (old turn keeps the claim while sending Done); unconfirmed: aclosing on the stream,
  cancel mid-DB-work on pooled asyncpg connection.
- **Onboarding follow-ups (074):** D18 SEC-001 = SPEC-003 (founder never sees the prompt; live
  step 6), SEC-002 (down/up loses selections), SEC-003 (no-workspace session gets 500), SEC-004
  (unquoted role in GRANT); backlog onboarding-live-close; sc-168 consumer main-settings-use.
- **Team tools (077):** sweep SEC-001 Medium but OLDER code (check.py verify trusts receipt
  fields; indiff: 465-479 older, proves() in diff), SEC-002 (npm ci runs new install scripts
  unreviewed), BUG-L1 (`facts.py brief W --runs A B` exits 2, contrary to scope:077:facts-runs).
- **Raids page leftovers (073):** SPEC Low (URL stays /app/raids), SEC-004 (`..` not encoded,
  unreachable), SPEC-005 = backlog app-shell-mobile (existing sc-175).
- **Portrait on the raids page:** the follow-up promised on sc-364.
