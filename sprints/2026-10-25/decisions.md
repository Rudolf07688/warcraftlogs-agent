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

3. **Q: Track B order?**
   A: F4 (security) first, then F2 (sidebar).
   Why: F4 doesn't touch `wcl_agent`, so it runs safely alongside the restructure. F2
   imports the model helpers, so starting it later means less rebasing.

4. **Q: Bundle sc-156 and sc-159 with sc-164?**
   A: Yes, as F3.
   Why: the same files (model discovery, model state, retry layer). One owner avoids
   two developers editing `_load_models` and `model_retry` at the same time.

5. **Q: Migration numbering when two features add migrations?**
   A: F2 owns `0012`, F5 (stretch) owns `0013`.

6. **Q (F5, if pulled in): is the raw-fetch table tenant-scoped?**
   A: No, it's global.
   Why: Warcraft Logs data is public, and the shared Redis WCL cache (feature 014) is
   already cross-tenant. Per-tenant copies would duplicate storage and defeat the
   "80% of questions answered locally" goal.

7. **Q: sc-164 for Claude classes, which have only one model each?**
   A: No sibling to switch to, so go straight to the "try again shortly" message.
