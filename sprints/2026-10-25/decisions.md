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

## 2026-10-25: Feature 019 (sidebar & conversations) clarify answers

9. **Q1: What order do pinned chats appear in?** A: Most recently pinned first.
   Why: the group stays stable while you chat. Drag-to-order is extra scope with no
   request behind it.
10. **Q2: Is a pin per tenant or per user?** A: Per tenant (workspace), like
    conversations today.
    Why: conversations have no owner-user column. Per-user pins would need a join
    table for a case (a shared workspace with several users) that doesn't happen in
    practice yet. Revisit if multi-user workspaces become real.
11. **Q3: Where does the Pinned group go?** A: A "Pinned" sub-group at the top of the
    Conversations section. It collapses with the section, the count stays the total,
    and it is hidden when nothing is pinned.
    Why: one list, no extra toggle, and a minimal change to the sidebar.
12. **Q4: What does the pin control look like?** A: A pin icon button next to the
    delete ✕. It shows on hover or focus, and stays visible (filled) while the chat is
    pinned. It uses the existing shadcn Button and a react-icons icon, with no new
    dependency. The open chat's header also gets a pin toggle next to "PDF".
    Why: no dependency or lockfile change, and it matches the existing delete
    affordance. It must be keyboard reachable with an aria-label ("Pin chat" /
    "Unpin chat").
13. **Q5: Are chats that predate this feature renamed?** A: No. Generation fires only
    on a chat's first complete reply, so old chats keep their names.
    Why: no heuristic, so there's no risk of renaming an old raid investigation.

## 2026-10-25: Feature 018 acceptance

14. **Q: F1 AC 6 asks for `wcl --help` and `python main.py --help`, but neither has a
    --help flag at base. Is that a failure?**
    A: No. The AC's intent is that the entry points still work. The output is
    byte-identical to base (it reports the missing env vars and exits 1), and the image
    builds and boots to ready. AC 6 is met.
15. **Q: Are the restructure follow-ups the developer noted filed?**
    A: Yes, as Backlog stories at Low priority: sc-171 (de-stutter `cache/cache.py` and
    `tools/tools.py`, move `load_world_zones`), sc-172 (stale facts in ai_guide), sc-173
    (ruff and isort), sc-174 (the perf test that fails at base). They aren't QA
    findings, so they don't get the qa-deferred label.

## 2026-10-25: Feature 020 (fetch persistence) clarify answers

16. **Q1: Do we keep the history of live (unfinished) report data?** A: No. Exactly one
    row per query key, upserted on every fetch, which refreshes the payload and
    fetched_at.
    Why: the goal of epic 103 is to answer from local data, not to audit how a live
    report changed. sc-129 reads the latest row, and judges finality from the report's
    summary row (endTime vs fetched_at, the cache's existing 2-hour rule). A
    finality lookup at write time would add cost and complexity for nothing anyone
    reads. This meets F3 AC 4: a finished report never duplicates, and live data is
    stored again by refreshing its row.
17. **Q2: How are batched GraphQL calls (up to 10 reports) stored?** A: One row per
    network call, as received. report_code is NULL when the call covers several
    reports, and all the codes stay in params.
    Why: rows mirror real queries, so sc-129 can serve the identical batch call by its
    query key. Splitting into per-report rows is sc-130's job (normalized entities),
    which will parse batch payloads. The params must hold the report codes in a
    queryable form (for example a JSONB array) so sc-130 can find them.

## 2026-10-25: Feature 019 acceptance

18. **Q: Accept 019 (sc-154, sc-165, sc-155)?** A: ACCEPT.
    Checked myself: backend tests 981 passed / 3 skipped / 1 deselected, frontend build
    green. Read the diff: the migration and its legacy backfill, the conditional
    once-only claim, the tenant-scoped PATCH, the hook after `done`, and the Toggle
    a11y. A non-blocking note goes to the QA sweep: `conversation_titles` uses the
    private `suggestions._get_client` / `_SUGGEST_MODEL`. A public accessor would be
    cleaner. Live tests for the owner: the pin UI in a browser, and a real generated
    title (needs model credentials).

## 2026-10-25: Feature 022 (welcome M+ runs) clarify answers

19. **Q1: What counts as one M+ run?** A: One keystone fight (report code + fight id),
    not one report. Runs are de-duplicated across the user's own characters, and each
    entry names the character(s) in it.
    Why: one report often holds several keys, so "6 runs" should mean 6 keys.
20. **Q2: Which runs are listed, and what counts as "timed"?** A: Only finished keys
    (keystoneLevel > 0, with a result) are listed. "Timed" means keystoneBonus ≥ 1.
    Depleted but finished runs are listed as not timed. Abandoned or incomplete runs
    are not listed.
    Why: abandoned keys are noise on a welcome page, and there's little to review in
    them.
21. **Q3: What does clicking a run do?** A: Open a new chat with a separate
    server-owned M+ kickoff prompt, built the same way as `kickoff_prompt_for` (report
    code, fight, dungeon, key level). The chat gets the explicit title
    "M+ <dungeon> +<level>", which marks it as explicit (019).
    Content: a bounded review, mirroring the raid kickoff's feature 011 scope rule,
    covering:
    - the result against the timer (timed, depleted, by how much)
    - per pull or boss segment, the single biggest time loss
    - deaths (who, to what, and whether avoidable)
    - interrupt/kick coverage
    - one headline improvement for the user's character
    Stay at the run and segment level; go into cast-level detail only where a segment
    clearly warrants it.

## 2026-10-25: Feature 020 acceptance

22. **Q: Accept 020 (sc-127, sc-128)?** A: ACCEPT.
    Checked myself: pytest gives 1008 passed / 3 skipped / 1 deselected, and the 0013
    migration sits on 0012. I read the client sink, the writer and the upsert. The sink
    is offered only after the success and error checks, and it's O(1) with a no-op when
    unset. The queue is bounded by items and bytes, dropping the newest. Writes time
    out and errors are logged. The upsert keeps the newer fetched_at, and the payload
    is decoded in the database.
    Design change approved: the report codes live in their own `report_codes` JSONB
    column with a GIN index, not inside params. This meets the condition of entry 17
    better, because params stays exactly the variables sent and can be replayed.
    Notes for the QA sweep, non-blocking: `raw_fetches.py` imports the private
    `repository._insert`. A report_code literal over 32 characters fails only that
    row's write (logged).
