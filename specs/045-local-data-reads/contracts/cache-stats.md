# GET /api/admin/cache-stats (additions)

```json
"store": {"hits": 0, "misses": 0, "not_visible": 0, "timeouts": 0, "hit_rate": null},
"local_answers": {"turns": 0, "local_turns": 0, "rate": null}
```
`hit_rate` = hits / (hits + misses + not_visible), null with no probes; `rate` = local_turns /
turns, null with no turns. Degraded shape (Redis down/disabled): zeros and nulls.
