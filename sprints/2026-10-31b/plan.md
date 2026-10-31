# Sprint 2026-10-31b plan (Maren, PO)

Goal 1: pay down hardening and QA debt. 21 pts, 11 stories, iteration 266, sc-221 first.
Goal 2: the team learns to work with its autonomy. Each decision goes on the board with its reason.

| Feature | Dev | Tier | Model | Stories |
|---|---|---|---|---|
| 036 profile write-path hardening | Ansel (dev-1, dev-a) | M | opus/high | sc-221 (3), sc-222 (2), sc-223 (2), sc-225 (2), sc-244 (1) = 10 |
| 037 small independent hardening | Tomas (dev-2, dev-b) | S per ticket | opus/medium | sc-157 (2), sc-179 (2), sc-158 (2), sc-224 (1), sc-176 (2), sc-184 (2) = 11 |

- The two streams don't share files. 036 owns migration 0017 (down_revision 0016_profile_proposals).
- **Deferred:** sc-178 (no reader of raw_fetches yet; it gates sc-129); sc-177 and sc-185 (each needs its own migration, and 185 needs CI); sc-219, 220, 180–183 (UI and perf debt for the next hardening sprint).
- **Drop first:** sc-244 (docs), then sc-225 (perf), then sc-184.
- **Risks:**
  - background.spawn now runs each task in a fresh context (CRITICAL fan-out).
  - Advisory locks are tested on Postgres only.
  - A machine crash at 20:13Z killed every agent. They were resumed with their state intact.

Board decisions #2–#8. Briefs are in `briefs/`. Briefs and plan.html were written after launch; the plan doesn't block.
