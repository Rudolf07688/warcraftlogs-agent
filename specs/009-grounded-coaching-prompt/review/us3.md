# US3 review — percentiles and data with explicit context (quickstart "US3" steps 1–3)

Automated: `backend/tests/test_report_rankings.py` (compare/timeframe sent and echoed,
raw `rankings` kept, flattened `percentiles`, invalid enums rejected, defaults) and
`backend/tests/test_provenance.py` (`sample_scope`, `has_more`, `truncated`) — **pass**.
`test_raids.py` (consumer of the `rankings` key) still green.

Manual steps need the running app. Reference pulls from `baseline.md`.

| Step | Check | Result | Notes |
|---|---|---|---|
| 1 | "what did Hrslkks parse on cFHpyKdLWAajwZCM fight 9?" → overall **and** bracket percentile, labelled; rankings-vs-parses / timeframe stated when relevant | _pending_ | |
| 2 | "how are Fire Mages doing on Nek'zali heroic?" → metric, difficulty, partition, and "computed over the top N of the leaderboard" | _pending_ | |
| 3 | "did anyone die to <ability> on fight 47?" with a large events page → all pages fetched or "based on partial data" stated | _pending_ | |
