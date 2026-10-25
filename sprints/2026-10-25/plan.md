# Sprint 2026-10-25 plan

Product owner: `product-owner`. Sprint branch: `sprint-2026-10-25` (base `4923785`).
Point target 21 (19–23). **Planned: 22 points** in 5 features, plus 1 stretch point.

> Revision 2 (2026-10-25): the owner's new QA rule (QA tickets get the `qa-deferred`
> label and rank below all non-QA work) took sc-156/157/158/159 out of the sprint. Their
> 7 points went to fetch persistence (sc-127/128) and the welcome M+ runs (sc-153).
> See decisions.md, entry 8.

## Sprint goal

Restructure `wcl_agent/` into sub-packages now, while it is still small. Every later
agent feature then lands in the new layout and doesn't have to be moved. Start epic 103
("every fetch stored in the DB"), so Warcraft Logs data builds up from today. Ship the
improvements the owner feels every day: pinned chats with generated names, a chat that
survives a rate-limited model, and a welcome page that shows recent M+ runs as well as
raids.

## Tracks at a glance (features numbered 018+ in plan order)

| Order | Track A (agent / data layer) | Track B (UI, conversations, welcome) |
|---|---|---|
| 1st | **F1 / 018** Restructure `wcl_agent` (5) | **F2 / 019** Sidebar & conversations (7) |
| 2nd | **F3 / 020** Fetch persistence foundation (4), after F1 | **F5 / 022** Welcome: 6 raids + 6 M+ (3), after F1 and F3 |
| 3rd | **F4 / 021** 429 fallback to the sibling model (3), after F1 | Stretch: sc-152 font size (1) |
| Total | 12 | 10 (+1) |

### Which stories go together, and the order (answers the scrum master's question)

- **F1 = sc-150 alone.** Merge it first, as soon as it's accepted. Every open branch then
  rebases on it.
- **F2 = sc-154, then sc-165, then sc-155, in that order.** The first two don't touch
  `wcl_agent`, so they can run alongside F1. **sc-155 starts only after F1 is merged**,
  because it imports the model helpers.
- **F3 = sc-127, then sc-128.** It starts after F1.
- **F4 = sc-164.** It starts after F1, ideally after F2's sc-155 has merged (shared agent
  loop files, see below).
- **F5 = sc-153.** It starts after F1. Its WCL client edits wait until F3 has merged.

### Same-file overlaps: run these in sequence, not in parallel

| Shared files | Features | Rule |
|---|---|---|
| All of `wcl_agent/**`, plus the `wcl_agent` import lines across `backend/**` | F1 vs everyone | F1 owns these until it merges. Nobody else edits `wcl_agent/**` before then. |
| **Agent loop**: `backend/app/agent_runner.py`, `backend/app/api/ws.py` | F2 (sc-155 turn-completion hook) vs F4 (sc-164 turn retry/fallback) | One owner at a time. F2's hook is small, so let it land first, then grant both files to F4. |
| `wcl_agent` model retry layer (`model_retry` and its new path) | F2 (sc-155) vs F4 | F4 owns it. F2 only imports it and may not edit it. If sc-155 needs a change there, ask first. |
| **WCL client**: `wcl_agent` `wcl_client`, `queries`, `cache` (new paths after F1) | F3 vs F5 | F3 first. F5 adds its M+ query only after F3 has merged, so the new query is persisted by the write-through as well. |
| `frontend/src/App.tsx` | F2 (chat header pin, title refresh) vs F5 (welcome wiring, if any) | Low risk. Sequence any F5 edit to `App.tsx` after F2. |
| `backend/app/db/models.py`, `backend/migrations/versions/*` | F2 (`0012`), F3 (`0013`), F5 (`0014`, only if M+ runs need storage) | Revisions are assigned in that order. Renumber `down_revision` if the merge order changes. |
| Chat UI message rendering, PDF renderer | none | No feature touches `MessageList.tsx`/`StreamMarkdown.tsx` or `pdf_report.py`. |

---

## F1 / 018 — Restructure `wcl_agent/*.py` into sub-packages (Track A, first)

- **Stories:** sc-150 (5) Restructure wcl_agent/*.py into sub-packages.
- **Complexity:** medium. The work is mechanical, but the blast radius is wide: 25
  modules (7 kLOC), 69 backend files import from `wcl_agent` (45 of them tests), and
  about 10 tests patch dotted `"wcl_agent.x.y"` strings.
- **Footprint:** `wcl_agent/**`, the import lines of `backend/**` (app and tests),
  `main.py`, `pyproject.toml` (the `wcl` script entry, if `cli` moves), and
  `documentation/ai_guide.md` (module map).
- **Depends on:** nothing. **Blocks:** F2's sc-155, F3, F4, F5, and every future agent
  story.
- **Acceptance criteria:**
  1. The modules are grouped into sub-packages along the story's lines (client, tools,
     guides, cache, models; the developer picks the final names and records the
     old-to-new mapping table in the spec). Package names must not shadow each other
     or the existing module names: for example, a `cache/` package can't sit next to
     `cache.py`.
  2. Files are moved with `git mv`, so `git log --follow` keeps their history.
  3. **No compatibility shims** are left at the old paths (constitution I, one
     authoritative implementation). Every importer is updated, including the dotted
     strings that `monkeypatch`/`mock.patch` use, and lazy imports inside functions.
  4. There is no behaviour change. The full backend test suite gives the same
     pass/fail/skip counts as at base `4923785` (record the baseline first).
  5. Every module imports cleanly. A smoke test (or a one-off script whose output goes
     in the PR notes) imports every `wcl_agent` submodule and `backend.app.main`, and
     reports no errors.
  6. `uv run wcl --help` (the console script) and `python main.py --help` still work.
     The backend container image builds, and the app boots locally to `ready` on
     `/api/health`.
  7. `documentation/ai_guide.md` and any other module map or path reference in
     docs/README match the new layout. Historical `specs/0xx` files are left alone.
  8. The diff contains moves and import edits only, with no opportunistic refactors.
     Anything worth changing gets noted for the backlog instead.

## F2 / 019 — Sidebar & conversations: order, pinning, generated names (Track B, first)

- **Stories, in order:** sc-154 (1) Sidebar: previous conversations above Raids; sc-165
  (3) Pinnable chats in chat window and sidebar; sc-155 (3) Auto-generate conversation
  names.
- **Why bundled:** all three change `Sidebar.tsx` and the conversations API and model.
- **Complexity:** medium.
- **Footprint:** `frontend/src/components/Sidebar.tsx`, `frontend/src/App.tsx` (chat
  header), `frontend/src/types.ts`, `frontend/src/api/restClient.ts`,
  `backend/app/api/conversations.py`, `backend/app/db/models.py` (`Conversation`),
  `backend/app/db/repository.py` (the title logic around line 130), migration `0012_*`,
  a small title service under `backend/app/services/`, and (sc-155 only) a
  turn-completion hook in `backend/app/api/ws.py` or `agent_runner.py`.
- **Depends on:** sc-155 waits until F1 is merged.
- **Acceptance criteria:**
  1. *(sc-154)* The Conversations section is above the Raids section in the sidebar.
     Both keep their collapse toggles and counts.
  2. *(sc-165)* The user can pin and unpin a chat from its sidebar entry and from the
     open chat's header. Pinned chats appear in a "Pinned" group at the top of the
     conversation list, and the state survives a reload and a re-login.
  3. *(sc-165)* Pinning is stored server side (`pinned_at` nullable column, migration
     `0012`, upgrade and downgrade both work). It goes through a tenant-scoped API
     (for example `PATCH /api/conversations/{id}`) that respects tenancy/RLS: pinning
     another tenant's conversation returns 404. Backend tests cover this.
  4. *(sc-155)* After the first complete assistant reply in a conversation that still
     has the default name (the first-message excerpt or "New chat"), the server
     generates a short title (at most 60 characters, plain text, no quotes or
     markdown) from the first exchange, with a lightweight model through the existing
     retry and rate-limit helpers. It imports them and doesn't edit them.
  5. *(sc-155)* Title generation runs off the chat path. It never delays or blocks the
     reply stream, and it happens at most once per conversation. If it fails or hits a
     429, the current first-message title stays. Nothing errors to the user.
  6. *(sc-155)* A conversation created with an explicit title (raid investigations,
     recent-raid kickoffs) keeps it.
  7. *(sc-155)* The sidebar shows the new title without a manual reload (WS event or
     list refetch).
  8. Backend tests cover generation, the once-only rule, the explicit-title rule and
     the failure fallback, with the model faked.

## F3 / 020 — Fetch persistence foundation (Track A, second)

- **Stories, in order:** sc-127 (2) Raw WCL fetch schema; sc-128 (2) Write-through
  persistence of every WCL fetch.
- **Why now:** these open epic 103 ("Every fetch stored in the DB"), which is the
  foundation for sc-129..132, epic 100 (semantic search) and epic 106 (Raids page
  data). Stored data starts building up the day this ships.
- **Complexity:** medium.
- **Footprint:** the `wcl_agent` WCL client and cache (new paths after F1),
  `backend/app/db/models.py`, migration `0013`, `backend/app/db/repository.py` (or a
  new small repository module).
- **Depends on:** F1.
- **Acceptance criteria:**
  1. Migration `0013` creates a raw-fetch table (query key, operation name, params
     JSONB, report code (nullable, indexed), fetched_at, payload JSONB), and upgrade
     and downgrade both work.
  2. Every successful GraphQL response through the single WCL client is persisted,
     including cache-miss fetches from tools, guides, the welcome/recent-raids
     service and background jobs.
  3. Persisting never blocks or slows the tool call: it runs off the event loop and is
     bounded (for example a bounded queue or task set, with overflow dropped and
     logged). A persistence error is logged, never raised to the agent or the user.
  4. Repeated identical fetches of a finished report upsert one row instead of piling
     up duplicates. Live, still-changing data may be stored again, with its new
     `fetched_at`.
  5. The table is global, not tenant-scoped, matching the shared Redis WCL cache from
     feature 014 (Warcraft Logs data is public).
  6. Tests cover the write-through, the error isolation (the DB is down and the fetch
     still succeeds), and the upsert. Nothing reads from the table yet; DB-first reads
     are sc-129, next sprint.

## F4 / 021 — 429 fallback to the sibling model in the same class (Track A, third)

- **Stories:** sc-164 (3) Fall back to the second model in the same class on 429s.
- **Complexity:** high (switching model mid-turn with ADK and Anthropic).
- **Footprint:** `wcl_agent` `model_retry` and `models` (new paths), `backend/app/agent_runner.py`,
  `backend/app/api/ws.py`, `backend/app/model_state.py`, plus a small frontend notice
  (`frontend/src/App.tsx` or `StatusAlert.tsx`, `types.ts`) if a new event type is
  added.
- **Depends on:** F1. Takes the agent-loop files after F2's sc-155 hook has merged.
- **Acceptance criteria:**
  1. When a chat turn's model is still rate limited after the existing retry policy,
     the turn retries on the other discovered model of the same class. Gemini classes
     offer two versions (feature 016). If the turn is already on the second model, it
     switches back to the first.
  2. If both models of the class are rate limited, or the class has only one model
     (Claude classes today), the user gets a clear in-chat message to try again
     shortly. The agent loop and the socket survive, and the next message works.
  3. The user can see which model answered when a switch happened (a notice in the
     chat). There is at most one switch per attempt, so the fallback can't loop.
  4. The developer may implement the fallback at the turn level (re-run the turn on the
     sibling model) instead of per request, as long as 1–3 hold. A half-streamed reply
     must not be duplicated in the stored history.
  5. Tests cover these paths with fake 429 errors, for both the Gemini and the
     Anthropic call paths. No live Vertex call is needed in CI.

## F5 / 022 — Welcome chat: at most 6 raids + 6 M+ runs (Track B, second)

- **Stories:** sc-153 (3) Welcome chat: max 6 raids + 6 M+ runs.
- **Complexity:** medium (a new WCL query for the character's recent Mythic+ runs).
- **Footprint:** `backend/app/services/recent_raids.py`,
  `backend/app/services/recent_raid_types.py`, `backend/app/api/recent_raids.py`, the
  `wcl_agent` client/queries (new paths; after F3 has merged),
  `frontend/src/components/WelcomePanel.tsx`, and possibly migration `0014` if the
  runs are stored alongside the raids (feature 013 stores recent raids because they
  don't change).
- **Depends on:** F1. Its WCL client edits wait for F3.
- **Acceptance criteria:**
  1. The welcome panel shows at most 6 recent raids and at most 6 recent Mythic+ runs
     for the user's characters, each list most recent first. With no M+ runs, only the
     raids show, with no empty section or error.
  2. Each M+ run shows at least the dungeon, key level, date and whether it was timed,
     in the same visual style as the raid entries.
  3. Clicking an M+ run opens a new chat with an M+ review kickoff prompt, the same way
     clicking a raid does today (feature 013 flow).
  4. M+ data is fetched through the single WCL client and its cache, so it gets the
     Redis cache and F3's write-through. It follows feature 013's async/background
     pattern, so the welcome page never waits on Warcraft Logs.
  5. Tests cover the 6+6 caps, the ordering, the no-M+ case and the kickoff prompt,
     with WCL responses faked.

## Stretch (pull in only if both tracks are on schedule)

- **sc-152 (1) Slightly increase default font size.** Track B filler. The base font
  size goes up one step in `frontend/src/index.css` or `styles.css`, with no layout
  overflow in the sidebar, composer or welcome panel at 1280px and 390px widths.

---

## Risks, and what to drop first

| Risk | Mitigation |
|---|---|
| F1 conflicts with every other branch | Merge F1 first. Until it merges, F2's sc-154/165 are the only parallel work, and they don't touch `wcl_agent`. Open branches rebase on F1 right after it lands. |
| F1 breaks imports the tests don't reach (lazy imports, dotted patch strings, ADK/Alembic config, Dockerfile) | F1 AC 3–6: import smoke test, boot to ready, console script, image build. |
| The GitNexus index (built from the owner's checkout) goes stale for `wcl_agent` paths after F1 | After F1 merges, developers re-run `node .gitnexus/run.cjs analyze --index-only` in their worktree, or confirm `wcl_agent` paths by text search. |
| sc-164: ADK binds the model to the agent | F4 AC 4 allows a turn-level fallback. |
| The write-through adds load to Postgres on every cache miss | F3 AC 3: bounded and off the loop, overflow dropped. Only misses reach the client; Redis hits don't. |
| Vertex credentials may be expired on this host, so there are no live model calls | All model behaviour is tested with fakes. The owner tests sc-155 and sc-164 live. |
| The QA security findings (sc-157 remote images, sc-158 login limit behind a proxy) now wait at the bottom of the backlog, per the owner's rule | Acceptable while the app runs locally. **Pull sc-158 forward before any shared deployment (sc-146).** Noted in that story's rationale below. |

**Drop order if the sprint runs late:** (1) the stretch sc-152; (2) sc-155 from F2 (3
points; sc-154 and sc-165 still ship); (3) F5 / sc-153 (3); (4) F4 / sc-164 (3). F1 and
F3 are not dropped: they are the foundations.

---

## Full ranked backlog (all 49 open stories)

The 4 PDF stories already Under Review (sc-108/109/110/169) are excluded; they're
waiting for the owner's live test. Shortcut Priority mirrors this ranking: Highest =
sprint, High = next up, Medium = next sprints, Low = later, Lowest = long term **and
all `qa-deferred` tickets**. Per the owner's rule, the QA tickets rank below all non-QA
work.

| # | Story | Pts | Priority | Rationale |
|---|---|---|---|---|
| 1 | sc-150 Restructure wcl_agent into sub-packages | 5 | Highest | Foundation: every later agent story lands in the new layout, and moving 7 kLOC only gets dearer. |
| 2 | sc-154 Sidebar: conversations above Raids | 1 | Highest | Same component as sc-165, nearly free inside F2. Runs alongside F1. |
| 3 | sc-165 Pinnable chats | 3 | Highest | Daily-use value; shares sidebar, API and model with sc-155. |
| 4 | sc-155 Auto-generate conversation names | 3 | Highest | Makes old chats findable; pairs with pinning. |
| 5 | sc-127 Raw WCL fetch schema | 2 | Highest | Epic 103 foundation; stored data compounds from the day it ships. |
| 6 | sc-128 Write-through persistence | 2 | Highest | With sc-127. Epics 100 and 106 and sc-129..132 all build on it. |
| 7 | sc-164 429 fallback to the sibling model | 3 | Highest | Daily pain (stalled chats). Builds on the discovered model classes. |
| 8 | sc-153 Welcome: 6 raids + 6 M+ runs | 3 | Highest | Owner-visible. Runs after sc-128, so the new M+ fetches get stored too. |
| 9 | sc-152 Larger default font | 1 | High | Stretch filler, trivial and isolated. |
| 10 | sc-129 DB-first reads with freshness rules | 5 | High | First user-visible payoff of epic 103. Reads what sc-127/128 store. Heads the next sprint. |
| 11 | sc-163 Agent research playbooks | 5 | High | Big quota and latency win. Lands in the restructured agent and can use sc-129 reads. |
| 12 | sc-146 Deployment / hosting plan | 5 | High | Owner's first todo item. Doc-only, so it fits anywhere. Any shared deployment should first pull in qa-deferred sc-158 (#49). |
| 13 | sc-130 Normalize key WCL entities | 5 | Medium | Needs the raw fetches (127/128). The Raids page and the query tools read from it. |
| 14 | sc-141 Raids page: tabs | 2 | Medium | Do epic 106 as one feature (141/142/143), after sc-130. |
| 15 | sc-142 Raids page: previously pulled data | 5 | Medium | Built before sc-130 it would be rewritten against the normalized tables. |
| 16 | sc-143 Raids page: "Analyze this raid" button | 1 | Medium | Same component as sc-141/142. |
| 17 | sc-131 Agent tools to query stored data | 5 | Medium | After sc-130, in the restructured tools package. |
| 18 | sc-132 Local-answer hit-rate metric | 2 | Medium | Measures sc-129/131, so it comes after them. |
| 19 | sc-149 Agent skills for judging WoW numbers | 5 | Medium | Complements sc-163 (fetching vs judging). Prompt/skill work in the new layout. |
| 20 | sc-137 Design single-lane chat layout | 2 | Medium | Must precede sc-138 and needs the owner's review of the mockup. |
| 21 | sc-138 Implement single-lane chat layout | 5 | Medium | Rebuilds the chat window, so chat-window features (139, 140, 144, 118) come after it. |
| 22 | sc-139 Message actions in the new layout | 2 | Medium | Part of the redesign. |
| 23 | sc-140 Scroll to question on completion | 1 | Medium | Do it in the new layout, or it gets written twice. |
| 24 | sc-144 Character filter checkboxes | 5 | Medium | Lives in the chat header, so after the redesign. |
| 25 | sc-145 (Stretch) Agent sets the character filter | 5 | Low | Needs sc-144. |
| 26 | sc-166 Onboarding: new accounts to profile | 2 | Low | Epic 162 as one feature. It matters once other people sign up (after sc-146). |
| 27 | sc-167 Onboarding: main class/spec + content | 3 | Low | Same epic; sc-168 depends on it. |
| 28 | sc-168 Onboarding: background guide generation | 2 | Low | Reuses feature 015's background pipeline. Needs sc-167. |
| 29 | sc-147 Confirm browser cache usage | 2 | Low | Investigation. Worth more once sc-129 settles the server-side cache layers. |
| 30 | sc-111 pgvector setup | 2 | Low | Epic 100 embeds stored data, so it needs epic 103 first. |
| 31 | sc-112 Embed fetched data on write | 3 | Low | Hooks into sc-128's write path. |
| 32 | sc-113 Backfill embeddings | 2 | Low | After sc-112. |
| 33 | sc-114 Parallel semantic search tool | 3 | Low | After sc-111..113. |
| 34 | sc-115 Search-first prompting + eval | 2 | Low | After sc-114; overlaps the sc-163 playbooks. |
| 35 | sc-116 Spin up sub-agent tool | 5 | Low | Needs the restructured agent; otherwise independent. |
| 36 | sc-117 Sub-agent guardrails | 2 | Low | Ships with sc-116, sharing the rate limiter that sc-164 touches. |
| 37 | sc-118 Sub-agent progress in the UI | 2 | Low | Chat UI, so after the redesign (sc-138). |
| 38 | sc-123 Spike: define log upload scope | 2 | Low | Gates the rest of epic 102. |
| 39 | sc-124 Log upload endpoint and storage | 2 | Low | After the spike. |
| 40 | sc-125 Log upload UI with progress | 2 | Low | After sc-124. |
| 41 | sc-126 Ingest uploaded logs for the agent | 5 | Low | Ingests into the stored-fetch shape (127/130), so after them. |
| 41a | sc-171 wcl_agent follow-ups: de-stutter module names, move load_world_zones | 2 | Low | Raised during 018. Cheap while the new layout is fresh, but no feature waits on it. |
| 41b | sc-173 Add ruff with isort rules | 2 | Low | Raised during 018. Mechanical lint guard; 28 existing findings. |
| 41c | sc-172 ai_guide.md stale facts | 1 | Low | Raised during 018. Docs only. |
| 41d | sc-174 Perf test test_wcl_loop_lag fails under -m perf | 1 | Low | Raised during 018. Fails at base too; the perf suite is opt-in. |
| 42 | sc-119 (Long term) Sandboxed execution service | 5 | Lowest | Long term; only needed for the REPL. |
| 43 | sc-120 (Long term) REPL tool for sub-agents | 5 | Lowest | Needs sc-116 and sc-119. |
| 44 | sc-121 (Long term) Load log data into the REPL | 2 | Lowest | Needs sc-120 and the stored data. |
| 45 | sc-122 (Long term) Sandbox security review | 2 | Lowest | Gates shipping sc-119/120. |
| 46 | sc-158 QA SEC-004 per-client login limit (`qa-deferred`) | 2 | Lowest | QA tier. Top of the QA tier: needed before any shared deployment. |
| 47 | sc-157 QA SEC-003 block remote images (`qa-deferred`) | 2 | Lowest | QA tier. Security, small and isolated in the frontend. |
| 48 | sc-156 QA PERF-001 don't block on discovery (`qa-deferred`) | 2 | Lowest | QA tier. Do it with sc-159, which touches the same files (`_load_models`, readiness gate). |
| 49 | sc-159 QA SPEC-002/004 log line + empty catalog (`qa-deferred`) | 1 | Lowest | QA tier. Pair with sc-156. |
