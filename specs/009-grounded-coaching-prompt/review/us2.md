# US2 review — fair benchmarks (quickstart "US2" steps 1–6)

Automated: `backend/tests/test_fight_time.py` (interval maths, dead windows, player
resolution incl. ambiguity) and `backend/tests/test_benchmark.py` (band pages,
clipping, duration window, labels, budget shrink, Casts reduction, aggregation; tool
runs for wipe → limited, unknown player, duplicate name ± `source_id`, early death →
alive-time rates, result shape + links, budget, band clipped, tool summary) — **pass**.

Manual steps need the running app. Reference pulls from `baseline.md`.
Record `check_rate_limit` → `pointsRemaining` before and after each benchmark.

| Step | Check | Result | Points spent | Notes |
|---|---|---|---|---|
| 1 | "how do I compare to similar players on cFHpyKdLWAajwZCM fight 9 (Hrslkks)?" → `compare_player_to_cohort` called; cohort size, label, duration window, unmet criteria, median + range stated | _pending_ | | expected ≈ 1 + 3 + 1 + 1 + deaths + 5 calls (≈10–11 points at size 5) |
| 2 | same for the wipe (fight 45) → comparison explicitly limited | _pending_ | | |
| 3 | "what does the #1 Fire Mage do differently?" → top parse used, called an elite outlier | _pending_ | | |
| 4 | budget exhausted / artificially low → smaller cohort, labelled (unit-tested: `test_low_budget_shrinks_cohort`) | _pending_ | | |
| 5 | early-death pull (fight 17, 동주술옥) → rates per minute **alive**, time dead stated, death is the headline | _pending_ | | |
| 6 | duplicate name → asks or picks by known server, never silently (no duplicate in the reference report; covered by `test_duplicate_name_needs_source_id` and `test_resolve_player_ambiguous_name_returns_candidates`) | covered by tests | | |
