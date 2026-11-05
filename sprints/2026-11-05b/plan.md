# Sprint 2026-11-05b plan (Maren, PO)

Goal: back to the app. Semantic search works again, its failures show on D8, the service graph shows real averages, dashboard ratios can't go NaN, chat requests carry a smaller fixed prompt, and the chat input unlocks after a dropped connection.
Iteration: Sprint 2026-11-05b (back to the app), id 510. Branch sprint-2026-11-05b from 0678ea7. 10 pts.

| Feature | Stories (pts) | Tier | Dev | Model |
|---|---|---|---|---|
| 061 kb-embedding | semantic search always down sc-428 (2), embed queries concurrently sc-319 (1), D8 misses cancelled embeddings sc-503 (1) | S | Nils dev-3, dev-a | opus high |
| 062 dashboard-ratios | service-graph average sc-504 (1), ratio guards + panel bounds sc-508 (1) | S | Ansel dev-1, dev-b | opus medium |
| 063 chat-reconnect | chat input locked after a drop sc-376 (2) | S | Tomas dev-2, dev-c | sonnet high |
| 064 prompt-budget | 23k prompt tokens per chat sc-367 (2) | S | dev-4 (new), dev-d | opus high |

ACs: verbatim in briefs/. Order: all four in parallel (disjoint footprints, no dependencies). No migrations. None security-core.
Drop first if needed: 064 (largest risk to answer quality), then 063.
