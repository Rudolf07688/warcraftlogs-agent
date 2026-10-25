# Sprint 2026-10-25 decisions

Each entry gives the date, the question, the answer and the reason.

## 2026-10-25: Planning decisions (product owner)

1. **Q: Do we do the `wcl_agent` restructure (sc-150) this sprint, or later?**
   A: This sprint, as the first feature on Track A.
   Why: every upcoming agent story lands in `wcl_agent`, so each sprint of delay adds
   more code to move, and more half-finished branches to move it under. Doing it first
   costs the least.

2. **Q: Do we leave compatibility shims at the old `wcl_agent.<module>` paths?**
   A: No. Update every importer, tests included.
   Why: constitution I (one authoritative implementation). Shims would become a second
   path that drifts.

3. **Q: Track B order?** *(Superseded by entry 8.)*
   A: F4 (security) first, then F2 (sidebar).
   Why: F4 doesn't touch `wcl_agent`, so it runs safely alongside the restructure. F2
   imports the model helpers, so starting it later means less rebasing.

4. **Q: Bundle sc-156 and sc-159 with sc-164?** *(Superseded by entry 8: both are now
   qa-deferred.)*
   A: Yes, as F3.
   Why: the same files (model discovery, model state, retry layer). One owner avoids
   two developers editing `_load_models` and `model_retry` at the same time.

5. **Q: Migration numbering when two features add migrations?**
   A: F2 owns `0012`, F3 (fetch persistence) owns `0013`, and F5 (welcome M+) owns
   `0014` if it needs one. *(Revised under entry 8.)*

6. **Q (F3, fetch persistence): is the raw-fetch table tenant-scoped?**
   A: No, it's global.
   Why: Warcraft Logs data is public, and the shared Redis WCL cache (feature 014) is
   already cross-tenant. Per-tenant copies would duplicate storage and defeat the
   "80% of questions answered locally" goal.

7. **Q: sc-164 for Claude classes, which have only one model each?**
   A: No sibling to switch to, so go straight to the "try again shortly" message.

## 2026-10-25: Replan after the owner's QA rule (product owner)

8. **Q: The owner's new rule says QA tickets get the `qa-deferred` label and rank below
   all non-QA work. What happens to sc-156/157/158/159, which were in the sprint?**
   A: All four leave the sprint: they go back to Backlog with no iteration, get the
   `qa-deferred` label (new label id 170) and Priority Lowest, and sit at the bottom of
   the ranked backlog. Their 7 points go to the next non-QA stories in cost-of-change
   order: sc-127 and sc-128 (4, the epic 103 foundation, already the stretch) and
   sc-153 (3, welcome M+ runs, which should come after the write-through). The sprint
   stays at 22 points.
   Why: the owner's rule is explicit and newer than the plan. Track B no longer has a
   F1-disjoint security feature to start with, so F2 starts with sc-154/165 (they
   don't touch `wcl_agent`) and sc-155 waits until F1 is merged.
   Caveat: sc-158 (login limit behind a proxy) should be pulled forward before any
   shared deployment (sc-146). This is recorded in the plan's risks and the sc-146
   rationale, not escalated: nothing is being deployed this sprint.
