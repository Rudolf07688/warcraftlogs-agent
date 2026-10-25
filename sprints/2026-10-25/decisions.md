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

## 2026-10-25: Feature 021 (429 sibling fallback) clarify answers

23. **Q1: Where does the "switched model" notice live?** A: A notice line under the
    reply that answered ("Answered by <model>; <model> was rate limited"), plus a status
    line while switching. Live session only: not stored, so no DB change.
    Why: it meets AC 3 within 3 points. Keeping it across reloads isn't worth a
    migration.
24. **Q2: Which model does the next turn start on after a switch?** A: The user's
    chosen model again. The selector never changes by itself, and each turn gets its
    own single switch.
    Why: the user's choice is authoritative, and quotas recover quickly.
25. **Q3: What does the user see when no fallback works?** A: Split by case.
    - No sibling (Claude today): feature 011's message, unchanged.
    - Both siblings rate limited after a switch was tried: a distinct message, "Both
      <class> models are rate-limited right now. Please try again in about a minute."
    Why: when a fallback was attempted, saying so tells the user that switching models
    by hand won't help either. It's one extra string, a negligible cost.
26. **Q4: May 021 touch `MessageList.tsx` for the notice line?** A: Yes.
    Why: the plan's "no feature touches it" described the planned footprint and was
    never a prohibition. No other feature holds the file this sprint.
27. **Noted (scrum master's technical call, accepted):** a 429 that arrives mid-stream
    after text has started doesn't switch models (it would duplicate text). The
    behaviour stays as today and is out of scope for sc-164.

## 2026-10-25: Feature 022 acceptance

28. **Q: Accept 022 (sc-153)?** A: ACCEPT. The merge condition is met: the 0014
    Postgres up/down/up and RLS isolation check passed (6649abb).
    Checked myself: pytest gives 1022 passed / 3 skipped / 1 deselected. I read the
    refresh step, `extract_mplus_runs` (kill and level > 0, timed = bonus ≥ 1), the
    tenant-scoped investigate endpoint with its explicit title, the kickoff phrases,
    and the migration RLS that mirrors 0010. The agent's `get_report_fights` output is
    unchanged (an explicit dict), so raid tool calls carry no extra tokens.
    Live risk for the owner: if WCL reports a depleted key as `kill=false`, depleted
    runs would be missing, not shown as "Depleted". Check this on a known depleted key.
    Follow-up idea for later, not filed now: expose keystone level/bonus/time in
    `get_report_fights`, so an M+ review can quote the timer without an extra fetch. It
    fits sc-163 (playbooks).

## 2026-10-25: Stretch pull-in

29. **Q: Track B is idle after 022. Do we pull in the stretch sc-152 (larger default
    font, 1 pt)?** A: Yes. It moves to Shortlist with iteration 161, Priority Highest.
    The sprint becomes 23 points, still inside the 19–23 range.
    Why: it's isolated CSS with no overlap with 021. Acceptance: the base size goes up
    one step; no horizontal overflow or clipped text at 1280px and 390px in the sidebar,
    composer, welcome panel (raid and M+ cards) and chat messages; the frontend build
    is green.
30. **Q (023, raised ahead of clarify): `styles.css` hard-codes about 20 px font sizes, so
    a root change alone won't reach them. How do we meet AC 1 ("one place")?**
    A: Two steps, in two commits:
    1. A mechanical px→rem pass over the font sizes, which renders identically at the
       current root. Check by comparing before and after at the old root.
    2. One root bump.
    After that, every future size change is one line, which is the intent of AC 1.
    Font sizes only; spacing and layout px stay as they are. The estimate stays at 1
    point.
31. **Q (023): AC 2 at 390px can't hold. Do we accept 023 anyway, or hold it until a
    mobile layout lands?**
    A: Accept 023, but only on AC 2 as amended: no new overflow at 1280px, and no
    regression beyond the existing 390px overflow. This is a ruling on the AC, not the
    feature acceptance itself, which waits for the hand-off.
    Why: the 390px overflow is pre-existing. I looked at the base screenshot myself:
    the sidebar doesn't collapse, so the main column is crushed at any font size. 023
    adds only about 25–30px to it. Holding a 1-point CSS change for a 3-point layout
    story would gain nothing.
    Filed sc-175, "Mobile layout: collapsible sidebar on narrow screens": 3 points,
    ui/ux, epic 105, Priority Medium. It's ranked next to the chat redesign (sc-137/138)
    so the layout shell is rebuilt once.
32. **Q: Accept 023 at 8cd7d2f?** A: REJECT, with one fix.
    `html { font-size: 17px }` is an absolute root. It overrides the user's browser or
    OS default font-size preference, which the app respected until now (the root was
    unset). That is an accessibility regression. Fix: `html { font-size: 106.25% }`.
    That is 17px at the 16px default, so it renders identically to 8cd7d2f, but it
    still scales with the user's setting. Everything else is accepted as is (the 36
    exact px→rem conversions, the single Sidebar line, AC 2 per decision 31).
33. **Q: Accept 023 at 8a8ce50?** A: ACCEPT. The root is now `106.25%` (one line plus a comment), which fixes the decision 32 point. sc-152 is done for this sprint.

## 2026-10-25: Feature 021 acceptance

34. **Q: Accept 021 (sc-164)?** A: ACCEPT, at e55f382, rebased on the sprint tip ef7dbbf.
    Checked myself: pytest gives 1060 passed / 3 skipped / 1 deselected, and the build
    is green. The tests diff holds only the 3 new files, so the 019 title, guide,
    retry and rate-limit tests are untouched and pass. I read `generate_with_fallback`:
    it acts only on the turn's own model and only on a `ModelRateLimited` with nothing
    streamed; it switches at most once and keeps later requests on the sibling. The
    Gemini signature bypass copies parts instead of mutating stored events.
    `sibling_model` uses served order and the same publisher and class. The split
    message (decision 25) is in ws.py. The history-once check (my check 1) runs on a
    real ADK Runner.
    Live risks for the owner (need Vertex): a Gemini 400 after a switch that follows
    tool calls (the thought-signature bypass is unverified), and the notice is
    live-only by design. Claude signatures aren't handled, which is moot while no
    Claude class has a sibling.

## 2026-10-25: QA fix acceptance

35. **Q: Accept fix 025 (FN-3 BUG-001, FN-4 docs)?** A: ACCEPT at 21c928d.
    The 0012 fix wraps the Postgres backfill in NO FORCE … FORCE, inside Alembic's one
    transaction (env.py `begin_transaction`). It was verified on Postgres 17 with a
    NOSUPERUSER NOBYPASSRLS owner: the old code left the rows at `auto`, the fixed code
    sets them to `legacy` with FORCE restored, and an injected failure rolls everything
    back. The migration tests pass 3/3. The docs cover SPEC-003, 004, 005, 007 and 009.
    SPEC-008 and the 022 checkpoint wording belong to 024.
36. **Q: Accept fix 024 (FN-1, FN-2, SPEC-006, SPEC-008, the SPEC-004 remainder)?**
    A: ACCEPT at 47281b5. Checked myself: pytest gives 1064 passed / 3 skipped / 1
    deselected. I read the service diff: the raid step and the M+ step have separate
    `timeout_at` scopes under one deadline, only the raid step can fail the refresh,
    M+ errors are logged (an outer cancellation still propagates), and a report whose
    fetch failed isn't marked final. WelcomePanel shows stored runs in the running,
    idle, failed and empty states, with the skeleton only when there's nothing to
    show. Characters are matched per fight by name, falling back to the report-level
    set.
    The accepted behaviour change: an M+-only failure records `succeeded` and goes
    only to the server log. Owner live test: the raid-less view in a browser.
37. **Q (QA re-check BUG-R03): after an M+-only failure the refresh reads `succeeded`, so
    there's no user retry until the next due refresh (≥15 min). Is that acceptable?**
    A: Yes, for this sprint. It's the consequence of decision 36, which is a better
    trade-off than hiding stored runs. The options for a user-triggered M+ retry are
    recorded on sc-183.
38. **Q: Does the QA re-check gate need FN-5?** A: No, by the owner's ruling ("don't be perfectionistic"). The gate is FN-1 to FN-4 fixed plus green tests and build: PASS. The FN-5 doc edits went to qa-deferred sc-193.
39. **Correction to 38:** FN-5 was in the end done directly by the scrum master in 9636d39, as a final touch with no gate (team-lead instruction). sc-193 is covered by that commit and moved to Under Review in iteration 161.
