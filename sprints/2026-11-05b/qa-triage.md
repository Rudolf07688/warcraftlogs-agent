# QA triage, sprint 2026-11-05b (Maren)

Sources: end sweep `qa-reports/2026-11-05b-sweep/` (bugs + security, 0 C / 0 H / 3 M / 6 L) and team-lead's live pass at 8ffe755 (board #51: no FAILs, 4/4 PASS).

## Fixed in the one fix round
| Finding | Severity | Fix | Who |
|---|---|---|---|
| BUG-002 = SEC-001 partial answer into the wrong chat (+ same flaw in the done handler) | Medium | 063-fix | Tomas |
| BUG-004 stale drop replayed at a later reconnect | Low (regression from 063) | 063-fix | Tomas |
| BUG-007 idle error frame swallowed by the stray-frame guard | Low (latent, new code) | 063-fix | Tomas |
| BUG-003 gather siblings run past the budget | Medium | 061-fix | Nils |
| BUG-005 per-call semaphore never limits | Low (same hunk) | 061-fix | Nils |
| BUG-006 rate limit recorded as CancelledError; shutdown-cancelled documents recorded as failures | Low (regression from 061) | 061-fix | Nils |

## Deferred (all labelled qa-deferred unless noted; deduped against open tickets, no matches)
| Ticket | Finding |
|---|---|
| sc-511 | BUG-001: a new turn can run alongside a dropped turn on the same chat (pre-existing race, now reachable faster; backend design) |
| sc-512 | SEC-002: embeddings default to europe-west1 even when the model location is pinned (residency) |
| sc-513 | NaN-prone rules outside runtime ratios (quantile clamps, datastores/build divisions; Ansel #35 + bugs.md note) |
| sc-514 | Profile change schema sends developer notes to the model (Vera #33; backlog chore, not qa-deferred) |
| sc-515 | Inline coaching briefs add up to 3k tokens per request (Vera #34; backlog feature, relates to sc-220) |
| sc-516 | Live: "Failed to detach context" when the backend stops mid-turn (board #51) |
