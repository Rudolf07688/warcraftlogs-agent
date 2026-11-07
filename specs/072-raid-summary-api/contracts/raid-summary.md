# Contract: raid-summary (board key `contract:raid-summary`)

`GET /api/raids/{report_code}/summary` (session cookie) → 200 `RaidSummary` (data-model.md):

```json
{"report_code":"a1B2c3D4e5F6g7H8","has_data":true,"duration_ms":9876000,
 "participants":[{"name":"Thrall","class_name":"Shaman","spec":"Enhancement","role":"dps"}],
 "my_characters":[{"name":"Thrall","class_name":"Shaman","spec":"Enhancement",
   "parses":[{"encounter":"Ulgrax the Devourer","difficulty":"Heroic","percentile":87.4}]}],
 "fetched_at":"2026-11-07T19:00:00Z"}
```

404 `{"detail":"not_found"}` for a code that is malformed or not a tracked raid of the caller's
workspace. `has_data:false` → `duration_ms:null`, empty lists, `fetched_at:null`.

Rework after the D18 review (board `review:072`): 429 `{"detail":{"code":"rate_limited",...}}`
with `Retry-After: 60` over 60 summaries per user per minute. A stale raid answers
`has_data:false` without a re-verify while its 10-minute cooldown runs or while two of the
workspace's re-verifies are in flight; the page should not retry in a tight loop. "My characters"
need name, realm and region in the stored data (no name-only match).
