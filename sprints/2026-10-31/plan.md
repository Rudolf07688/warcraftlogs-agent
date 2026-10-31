# Sprint 2026-10-31 plan

Product owner: `product-owner`. Sprint branch: `sprint-2026-10-31` (base `b963463`).
Shortcut iteration: **Sprint 2026-10-31** (id 254, 2026-10-31 → 2026-11-13).
Point target 21 (19–23). **Planned: 21 points** in 4 features (032–035).
Next Alembic revision: `0017` (down_revision `0016_profile_proposals`). No feature is
expected to need a migration this sprint.

**Owner gate: passed.** The owner replied "go" on 2026-10-31 (decisions D10), with all
recommendations (D1–D3) accepted. Implementation proceeds after each feature's Spec Kit
gates. There are no more owner gates.

## Sprint goal

**One setting switches every LLM call between Vertex AI and the Anthropic API** (new
epic 248, owner's first priority). The second goal is to fix the three crucial QA findings
from the self-aware-agent sprint (sc-241, sc-242, sc-243) before the owner relies on
Barnaby's profile changes live.

### User flow: switching providers (owner-approved, decisions D1–D3, D9)

1. The owner sets `WCL_LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=…` in `.env` and
   restarts (`01_start_app.sh` / compose).
2. At startup the backend lists the Claude models the key can use, probes them, and serves
   the newest per class (haiku/sonnet/opus). The model picker now shows only Claude, with
   an "Anthropic API" label.
3. Chat, the greeting, follow-up suggestions, chat titles, PDF findings reports and class
   guides all run on Claude through the Anthropic API. An old chat whose stored model is
   no longer served continues on the new default model.
4. To switch back, set `WCL_LLM_PROVIDER=vertex` (or delete the line) and restart. That is
   exactly today's behaviour.

### Why this shape (cost of change)

- **The provider layer comes first (032).** Every other provider story calls it. Built
  later, each call site would branch on the provider by itself and then be rewritten.
- **One feature owns all non-agent call sites (035)**, so the provider-neutral
  text-generation entry point is written once, by one developer, for suggestions, titles,
  reports and guides together.
- **sc-159 rides with discovery (033).** It lives in the same discovery function that 033
  rewrites for the Anthropic Models API. Fixing it later would mean touching the new code
  twice.
- **The epic-203 fixes are one feature (034).** sc-241 and sc-242 share the proposal
  service and the API, and sc-243 is the matching chat-side guard. They don't overlap with
  any provider file, so they make a clean parallel track.

## Tracks at a glance

| Order | Track A (provider core) | Track B (epic-203 fixes, then call sites) |
|---|---|---|
| 1st (parallel) | **032** Provider switch + Anthropic client for the agent (sc-249, 5) | **034** Crucial epic-203 QA fixes (sc-241 + sc-242 + sc-243, 6) |
| 2nd | **033** Discovery on the Anthropic API + provider label + sc-159 (sc-250 + sc-251 + sc-159, 5), after 032 merges | **035** Suggestions, titles, reports and guides on the active provider (sc-252 + sc-253, 5), after 032's contract is shared (implementation after 032 merges) |
| Total | 10 | 11 |

The critical path is 032 → 033 and 032 → 035. **032 must share its provider-layer contract
early** (the module, the function names, the model-role names and the per-provider
defaults), through the scrum master at its `/speckit-plan` stage, so 035 can specify
against it while 034 is still in progress.

### Same-file overlaps: one owner at a time

| Shared files | Features | Rule |
|---|---|---|
| `wcl_agent/llm/vertex.py` and the new provider module (location set by 032's plan) | 032 vs 033 / 035 | 032 owns them. 033 and 035 only call them. Any change they need is a scrum-master grant after 032 merges. |
| `backend/app/config.py` | 032 vs 033 | 032 adds the provider, the key and the model-role defaults. 033 may add discovery settings after 032 merges (same track, so sequential). 035 only reads. |
| `backend/app/main.py` (`_load_models`, lifespan) | 032 vs 033 | 032 adds the startup provider/key check. 033 owns `_load_models` (cache key, sc-159 log line). Same track, so sequential. |
| `wcl_agent/llm/model_retry.py` | 032 vs 033 | 032 changes the `RetryingClaude` client source. 033 makes the 429 → sibling path work for API ids. Same track, so sequential. 035 only calls `generate_with_retry`. |
| `wcl_agent/llm/models.py` | 033 only | |
| `wcl_agent/agent.py` | 032 only | The model factory. No other feature edits it. |
| `backend/app/schemas.py` | 033 (`ModelsResponse.provider`) vs 034 (`ProfileChangeIn`) | Different classes. Both may edit them; the scrum master merges 034 first if both land together. |
| `frontend/src/App.tsx` | 034 only | sc-243's conversation guard. 033's provider label goes in the picker component or `api/restClient.ts`. If it needs `App.tsx`, it waits for 034 to merge or asks for a grant. |
| `backend/app/suggestions.py`, `services/conversation_titles.py`, `services/report_synthesis.py`, `services/guide_pipeline/*` | 035 only | |
| `backend/app/services/profile_proposals.py`, `agent_tools/profile_tools.py`, `api/proposals.py`, `db/repository.py`, `frontend/src/toolLabels.ts`, `lib/spells.ts` | 034 only | |
| `.env.example`, `README.md` | 032 vs 033 / 035 | 032 writes the provider section. 033 and 035 add their own lines to it after 032 merges. |

---

## 032 — Provider switch and Anthropic API client for the chat agent (Track A)

- **Stories:** sc-249 (5) LLM provider switch (`WCL_LLM_PROVIDER`) and Anthropic API client
  for the chat agent.
- **Complexity:** high (a foundation every other provider story builds on; secrets).
- **Footprint:** `wcl_agent/llm/vertex.py`, a new provider module under `wcl_agent/llm/`,
  `wcl_agent/llm/model_retry.py` (`RetryingClaude._anthropic_client`, `is_anthropic_model`),
  `wcl_agent/agent.py` (model factory), `backend/app/config.py`, `backend/app/main.py`
  (startup check), `backend/app/model_state.py` / the WS model resolution (stale chat
  model), `.env.example`, `README.md`, `docker-compose.yml` (only if the ADC mount must
  become optional), tests.
- **Depends on:** nothing. **Blocks:** 033 and 035 (contract shared early).
- **Developers:** load the `claude-api` skill for Anthropic SDK facts and model ids.
- **Acceptance criteria:**
  1. `WCL_LLM_PROVIDER` accepts `vertex` (default, today's behaviour unchanged) or
     `anthropic`. Any other value logs a warning and uses `vertex`. Switching takes one
     `.env` line and a restart.
  2. One provider layer (one module) is the only place that knows the active provider and
     builds model clients. Call sites never branch on the provider (constitution I).
  3. With `anthropic`, the chat agent's Claude models call the Anthropic API
     (`AsyncAnthropic`), not `AsyncAnthropicVertex`. Agent turns with tools, the greeting
     and the other ADK runs (`stream_response`) work through the existing retry wrapper.
  4. `ANTHROPIC_API_KEY` is a secret (`SecretStr` or equivalent). It never appears in
     logs, error frames, `/api/*` responses or exception text (a test asserts this). With
     `anthropic` and no key, startup logs one clear error and serves the degraded model
     state; it does not crash.
  5. API-form ids (`claude-sonnet-4-20250514`, aliases) and Vertex-form ids
     (`claude-sonnet-4@20250514`) are told apart in one place, never by ad-hoc string
     edits at call sites.
  6. A chat whose stored model isn't served by the active provider continues on the
     default model, with no error.
  7. Per-provider defaults for the fixed model roles (default chat, report, guide, guide
     review, suggest/fast, greeting): an unset role uses the active provider's default
     (current Claude ids per the `claude-api` skill), and an explicit env value still wins.
  8. `.env.example` and README explain the switch and the key, and say that Google ADC
     isn't needed for LLM calls under `anthropic` (compose must still start without an ADC
     file). The key reaches the container through the existing `env_file: .env`. Agents
     never read the owner's `.env`.
  9. Tests use fakes or mocks only. They cover client selection for both providers, the
     missing key, the secret-not-logged check and the stale chat model. The full backend
     suite passes, with no new failures against base `b963463`.

## 033 — Model discovery on the Anthropic API, provider label, discovery log fix (Track A)

- **Stories:** sc-250 (3) Model discovery, catalog and 429 sibling fallback on the
  Anthropic API; sc-251 (1) Model picker shows which LLM provider is live; sc-159 (1,
  `qa-deferred`) QA SPEC-002/004: startup log line and empty-catalog handling.
- **Why bundled:** all three live in the discovery path (`models.py`, `_load_models`,
  `/api/models`). sc-159's fix sits in the exact function sc-250 rewrites.
- **Complexity:** medium.
- **Footprint:** `wcl_agent/llm/models.py`, a provider-side listing function (by grant in
  032's module, or a new one 033 owns), `wcl_agent/llm/model_retry.py` (sibling with API
  ids), `backend/app/main.py::_load_models`, `wcl_agent/cache` model-catalog key,
  `backend/app/schemas.py::ModelsResponse`, `backend/app/api/models.py`, the frontend
  model picker component and `frontend/src/api/restClient.ts`, tests.
- **Depends on:** 032 merged.
- **Acceptance criteria:**
  1. *(sc-250)* With `anthropic`, catalog mode lists the Anthropic Models API, sorts API
     ids and aliases into the haiku/sonnet/opus classes (`WCL_ANTHROPIC_CLASSES`), probes
     each with the tool-carrying one-token call and keeps the newest `count` per class
     that answer. No Gemini models are offered. Static mode probes `WCL_ANTHROPIC_MODELS`
     in API form and is the fallback if listing fails.
  2. *(sc-250)* The cached catalog key includes the provider. A Vertex catalog is never
     served under `anthropic`, or the reverse, and cached ids are validated in the active
     provider's id shape.
  3. *(sc-250)* On a 429 or 529 from the Anthropic API, the turn retries (honouring
     `retry-after`), then switches to the same-class sibling. When both are busy it shows
     the same friendly message as on Vertex.
  4. *(sc-251)* `GET /api/models` also returns `provider` (additive field). The picker
     shows a small read-only "Vertex AI" / "Anthropic API" label (shadcn via the MCP where
     one fits), readable at 390px, and never shows a key, project id or secret.
  5. *(sc-159)* The specified model-discovery startup log line is emitted (feature 016
     spec), and a listing response with no models is treated as a listing failure (so
     the fallback runs), not as an empty catalog. This applies to both providers.
  6. `vertex` behaviour is otherwise unchanged and the existing discovery tests pass.
     New tests use fakes: paged listing, API id classification, not-enabled and no-quota
     probes, the cache-key split, 429 → sibling, the response field, the label, and both
     sc-159 cases. Frontend build, typecheck and tests pass.

## 034 — Crucial epic-203 QA fixes (Track B)

- **Stories:** sc-241 (2) one invalid proposal item crashes the profile tool and the turn;
  sc-242 (2) overlapping approvals post the follow-up twice or return 500; sc-243 (2)
  proposal card shows in the wrong chat after a mid-turn switch, plus the misleading tool
  status. All are `qa-deferred` and marked crucial in the 2026-10-26 triage.
- **Why bundled:** they are the same flow (propose → card → approve) and share the
  proposal service and its tests. None of the files overlap with the provider epic.
- **Complexity:** medium.
- **Footprint:** `backend/app/agent_tools/profile_tools.py`,
  `backend/app/services/profile_proposals.py`, `backend/app/schemas.py`
  (`ProfileChangeIn`), `backend/app/api/proposals.py`, `backend/app/db/repository.py`
  (only if the follow-up insert moves into the locked transaction), `frontend/src/App.tsx`,
  `frontend/src/toolLabels.ts`, `frontend/src/lib/spells.ts`, tests. The fix suggestions in
  each ticket are the starting point.
- **Depends on:** nothing.
- **Acceptance criteria:**
  1. *(sc-241)* Raw item dicts through the real ADK argument path
     (`FunctionTool.run_async`): realm `None`, `played_role` "Healer" and one valid item
     produce a stored proposal with 2 skipped rows (with the right codes:
     `invalid_realm` / `invalid_region` for blank or missing realm/region) and 1 valid row.
     Roles compare case-insensitively. No `agent_error` with raw Python text.
  2. *(sc-241)* An unexpected exception inside the tool returns `{"status": "error"}`
     with a plain message, and the turn continues.
  3. *(sc-242)* Two overlapping approvals (simulated in a test) apply the change once,
     save exactly one follow-up line and return no 500. Only the call that made the
     transition (decided under `FOR UPDATE`) saves the follow-up, in the same
     transaction. The same holds for cancel.
  4. *(sc-243)* A proposal card (or loose card) attaches only to the chat whose turn
     produced it, keyed by the turn's conversation id from the `meta` frame. Switching
     chats or starting a new chat mid-turn never shows it in the wrong chat, and reopening
     the original chat shows it.
  5. *(sc-243)* While `propose_profile_changes` runs, the status reads "Preparing profile
     changes" (or similar) with a matching spell entry, not "Searching Warcraft Logs".
  6. The existing proposal, card and WS tests pass. Backend suite: no new failures.
     Frontend build, typecheck and tests pass.

## 035 — Suggestions, titles, reports and class guides on the active provider (Track B)

- **Stories:** sc-252 (2) follow-up suggestions, chat titles and report synthesis run on the
  active LLM provider; sc-253 (3) grounded class-guide pipeline runs on the Anthropic API
  (structured output and web search).
- **Why bundled:** both replace direct `google.genai` calls with the one provider-neutral
  generation entry point. One owner writes it once.
- **Complexity:** medium–high (web-search grounding and structured output differ between
  providers).
- **Footprint:** `backend/app/suggestions.py`, `backend/app/services/conversation_titles.py`,
  `backend/app/services/report_synthesis.py`, `backend/app/services/guide_pipeline/llm.py`
  (and `research.py` only if the sources shape needs it), a new provider-neutral
  generation module (location per 032's contract, owned by 035), README lines, tests.
- **Depends on:** 032's contract (specify and plan), then 032 merged (implement).
- **Developers:** load the `claude-api` skill (web search tool, structured output).
- **Acceptance criteria:**
  1. *(sc-252)* One provider-neutral text-generation entry point (prompt, model role, max
     tokens, temperature) serves suggestions, titles and report synthesis on either
     provider, through the shared retry loop. No `google.genai` types or provider
     branches remain in those three modules.
  2. *(sc-252)* With `anthropic`, suggestions and titles use the fast-role model and
     reports use the report-role model. Fail-closed behaviour is unchanged (no
     suggestions; the first-message title is kept; a clean 500 with no partial PDF), and
     the existing timeouts still hold.
  3. *(sc-253)* `generate_structured` works on both providers: output is validated against
     the same Pydantic schema, with the same one-retry rule and `GuideModelError`.
  4. *(sc-253)* `generate_grounded` works on both providers. Under `anthropic` it uses
     Anthropic's server-side web search tool and returns `GroundedText` with
     `{title, uri}` sources from the results. URL context maps to web fetch or is
     documented as unavailable, and `WCL_GUIDE_RESEARCH_FETCH_ENABLED` is never bypassed.
  5. *(sc-253)* Under `anthropic`, guide author and reviewer default to two different
     Claude models, and the startup check that they differ still runs. If web search isn't
     enabled for the Anthropic organisation, research fails as a clear `GuideModelError`
     (the run is held as today), and README says how to enable it.
  6. `vertex` behaviour is unchanged and the existing suggestion, title, report and
     guide-pipeline tests pass. New tests use faked Anthropic and genai clients (including
     web-search result blocks and a validation retry). No live calls.

### End-to-end acceptance (sprint level, on the merged sprint branch)

- With fakes: `WCL_LLM_PROVIDER=anthropic` makes the agent, suggestions, titles, report
  synthesis and the guide pipeline all reach the faked Anthropic client, and none reaches
  genai. `vertex` reaches only Vertex clients. One parametrised test proves this.
- A grep check: outside the provider layer, nothing imports `google.genai` clients or
  `anthropic` clients directly for model calls (types for the ADK agent excepted).
- Live (owner, Under Review): one chat, one PDF report and one class guide on each
  provider. Anthropic web search must be enabled in the Anthropic Console first.

---

## Risks, and what to drop first

| Risk | Mitigation |
|---|---|
| ADK's `Claude` model class is built around `AnthropicVertex`. A plain `AsyncAnthropic` client may need more than a client swap. | 032 checks this first in its plan (`RetryingClaude` already overrides `_anthropic_client`). If ADK needs more, it's still inside 032, which has the largest estimate. |
| Anthropic web search may not be enabled for the owner's organisation, and searches cost extra. | sc-253 AC 5: a clean, held run plus a README note. The owner confirms in the live check. |
| Structured output and grounding sources differ between providers. | One owner (035) and the `claude-api` skill. Tests with faked result blocks. |
| Without live keys on this host, behaviour is checked only with fakes. | All ACs are fake-based. The live checks go to the owner (Under Review). |
| The secret could leak through exception text (SDK errors can echo headers). | sc-249 AC 4 has an explicit test. The QA security sweep checks it again. |
| 23 points of provider work was tempting. The plan holds at 21. | sc-221 (security hardening of the agent write path) heads the next sprint (Priority High). |

**Drop order if the sprint runs late:** (1) sc-159 out of 033 (back to Backlog);
(2) sc-251, the provider label (the switch still works; the log shows the provider);
(3) sc-243 out of 034 (frontend-only; sc-241/242 are the data-safety fixes). 032, 033's
sc-250, and 035 are not dropped: without them, switching provider breaks part of the app.

---

## Full ranked backlog (85 open Team 1 stories at planning plus sc-249..253 created today = 90; the 9 Under Review are excluded, 81 ranked)

Shortcut Priority mirrors this ranking: **Highest** = this sprint, **High** = next up,
**Medium** = next sprints, **Low** = later, **Lowest** = long term and the `qa-deferred`
tier (owner rule: QA ranks below non-QA work, except crucial findings, which the owner set
High/Medium). Under Review stories (sc-204..212) wait for the owner and are not ranked.

| # | Story | Pts | Priority | Rationale |
|---|---|---|---|---|
| 1 | sc-249 Provider switch + Anthropic client for the agent | 5 | Highest | Foundation of epic 248; every other provider story calls it. |
| 2 | sc-250 Discovery, catalog and 429 fallback on the Anthropic API | 3 | Highest | Without it the picker can't offer API models. |
| 3 | sc-252 Suggestions, titles, reports on the active provider | 2 | Highest | Otherwise these silently stay on Gemini (or break) after a switch. |
| 4 | sc-253 Guide pipeline on the Anthropic API | 3 | Highest | Guides are a major feature; same entry point as sc-252. |
| 5 | sc-251 Provider label in the model picker | 1 | Highest | Makes the switch visible; same files as sc-250. |
| 6 | sc-241 QA invalid proposal item crashes the turn (`qa-deferred`, crucial) | 2 | Highest | Can break the owner's example request live. |
| 7 | sc-242 QA overlapping approvals (`qa-deferred`, crucial) | 2 | Highest | Same proposal service as sc-241. |
| 8 | sc-243 QA card in the wrong chat (`qa-deferred`, crucial) | 2 | Highest | The chat side of the same flow. |
| 9 | sc-159 QA SPEC-002/004 discovery log line + empty catalog (`qa-deferred`) | 1 | Highest | Same function 033 rewrites; later would mean touching it twice. |
| 10 | sc-221 QA harden the agent write path against injected log text (`qa-deferred`) | 3 | High | Top deferred security item; heads the next sprint. Same files as sc-241, now stable. |
| 11 | sc-176 QA switch to the sibling model sooner on 429s (`qa-deferred`) | 2 | Lowest | Next-sprint candidate. Same retry code epic 248 touches. Cheaper once 033 has settled the sibling logic for both providers. |
| 12 | sc-156 QA don't block startup on model discovery (`qa-deferred`) | 2 | Lowest | The lifespan code 032/033 touch. Do it right after, with sc-176. |
| 13 | sc-244 QA architecture docs stale for the self-aware agent (`qa-deferred`) | 1 | Low | Do it after epic 248 so the docs are updated once, covering both. |
| 14 | sc-178 QA raw_fetches cross-tenant guard (`qa-deferred`) | 2 | High | The design gate for sc-129 (exception to the QA tier). |
| 15 | sc-129 DB-first reads with freshness rules | 5 | High | First user-visible payoff of epic 103. |
| 16 | sc-163 Agent research playbooks | 5 | High | Big quota and latency win; uses sc-129 reads. Matters more with per-token API billing. |
| 17 | sc-197 Spec the worker server | 3 | High | Settles background-job architecture before more jobs pile onto `background.py`. |
| 18 | sc-146 Deployment / hosting plan | 5 | High | Doc only. Needs sc-158 before any shared deployment. |
| 19 | sc-213 Charts not restored when a chat is reopened (bug) | 2 | Medium | Small frontend fix. |
| 20 | sc-130 Normalize key WCL entities | 5 | Medium | Needs the raw fetches; the Raids page and query tools read from it. |
| 21 | sc-141 Raids page: tabs | 2 | Medium | Epic 106 as one feature, after sc-130. |
| 22 | sc-142 Raids page: previously pulled data | 5 | Medium | Built before sc-130 it would be rewritten. |
| 23 | sc-143 Raids page: "Analyze this raid" button | 1 | Medium | Same component as sc-141/142. |
| 24 | sc-131 Agent tools to query stored data | 5 | Medium | After sc-130. |
| 25 | sc-132 Local-answer hit-rate metric | 2 | Medium | Measures sc-129/131. |
| 26 | sc-149 Agent skills for judging WoW numbers | 5 | Medium | Complements sc-163. |
| 27 | sc-198 Worker container with NATS (JetStream) | 3 | Medium | After sc-197. |
| 28 | sc-199 Worker task state + audit trail | 3 | Medium | After sc-198. |
| 29 | sc-200 Worker retry and dead-letter | 3 | Medium | Completes the worker platform. |
| 30 | sc-137 Design single-lane chat layout | 2 | Medium | Before sc-138; needs the owner's review. |
| 31 | sc-138 Implement single-lane chat layout | 5 | Medium | Chat-window features come after. |
| 32 | sc-139 Message actions in the new layout | 2 | Medium | Part of the redesign. |
| 33 | sc-175 Mobile layout: collapsible sidebar | 3 | Medium | With sc-138, so the shell is rebuilt once. |
| 34 | sc-140 Scroll to question on completion | 1 | Medium | In the new layout. |
| 35 | sc-144 Character filter checkboxes | 5 | Medium | Chat header, after the redesign. |
| 36 | sc-145 (Stretch) Agent sets the character filter | 5 | Low | Needs sc-144. |
| 37 | sc-215 Bubble width caps in rem | 1 | Low | Small CSS follow-up. |
| 38 | sc-214 Per-item selection on the profile-change card | 2 | Low | Epic 203 follow-up. |
| 39 | sc-201 Background job: raid and dungeon guides | 5 | Low | First job on the worker. |
| 40 | sc-202 Background job: offline character profile | 5 | Low | Worker job. |
| 41 | sc-166 Onboarding: new accounts to profile | 2 | Low | Epic 162 as one feature. |
| 42 | sc-167 Onboarding: main class/spec + content | 3 | Low | Same epic. |
| 43 | sc-168 Onboarding: background guide generation | 2 | Low | Best on the worker. |
| 44 | sc-147 Confirm browser cache usage | 2 | Low | After sc-129. |
| 45 | sc-111 pgvector setup | 2 | Low | Epic 100, after epic 103; note that embeddings need a provider decision too (Anthropic has no embeddings API). |
| 46 | sc-112 Embed fetched data on write | 3 | Low | After sc-111. |
| 47 | sc-113 Backfill embeddings | 2 | Low | After sc-112. |
| 48 | sc-114 Parallel semantic search tool | 3 | Low | After sc-111..113. |
| 49 | sc-115 Search-first prompting + eval | 2 | Low | After sc-114. |
| 50 | sc-116 Spin up sub-agent tool | 5 | Low | Independent; runs on whichever provider is live. |
| 51 | sc-117 Sub-agent guardrails | 2 | Low | Ships with sc-116. |
| 52 | sc-118 Sub-agent progress in the UI | 2 | Low | After sc-138. |
| 53 | sc-123 Spike: define log upload scope | 2 | Low | Gates epic 102. |
| 54 | sc-124 Log upload endpoint and storage | 2 | Low | After the spike. |
| 55 | sc-125 Log upload UI with progress | 2 | Low | After sc-124. |
| 56 | sc-126 Ingest uploaded logs | 5 | Low | After sc-130. |
| 57 | sc-216 One shared naive-timestamp-as-UTC helper | 1 | Low | Constitution I cleanup. |
| 58 | sc-171 wcl_agent: de-stutter module names | 2 | Low | Cheap; best between sprints. |
| 59 | sc-173 Add ruff with isort rules | 2 | Low | Touches many files; between sprints. |
| 60 | sc-172 ai_guide.md stale facts | 1 | Low | Docs; do with sc-244. |
| 61 | sc-174 Perf test test_wcl_loop_lag fails under -m perf | 1 | Low | Opt-in suite. |
| 62 | sc-119 (Long term) Sandboxed execution service | 5 | Lowest | Only for the REPL. |
| 63 | sc-120 (Long term) REPL tool | 5 | Lowest | Needs sc-116, sc-119. |
| 64 | sc-121 (Long term) Load log data into the REPL | 2 | Lowest | Needs sc-120. |
| 65 | sc-122 (Long term) Sandbox security review | 2 | Lowest | Gates sc-119/120. |
| 66 | sc-184 QA web search after fallback (`qa-deferred`) | 2 | Lowest | Gemini-only path; needs a live check first. |
| 67 | sc-177 QA raw_fetches write amplification (`qa-deferred`) | 3 | Lowest | With sc-178/sc-129. |
| 68 | sc-158 QA per-client login limit (`qa-deferred`) | 2 | Lowest | Before any shared deployment. |
| 69 | sc-157 QA block remote images (`qa-deferred`) | 2 | Lowest | Small, frontend. |
| 70 | sc-185 QA Postgres tenant-isolation tests in CI (`qa-deferred`) | 3 | Lowest | Defence in depth. |
| 71 | sc-222 QA identity context reset + user-level RLS (`qa-deferred`) | 2 | Lowest | With sc-185. |
| 72 | sc-220 QA preamble budgets with many friends (`qa-deferred`) | 3 | Lowest | Matters more with per-token billing on the API. |
| 73 | sc-219 QA confirmation card state edge cases (`qa-deferred`) | 3 | Lowest | Rare multi-tab cases. |
| 74 | sc-225 QA proposal approve/read round trips (`qa-deferred`) | 2 | Lowest | Related to sc-242. |
| 75 | sc-223 QA profile cap race + legacy slugs (`qa-deferred`) | 2 | Lowest | |
| 76 | sc-224 QA cache participants lookups (`qa-deferred`) | 1 | Lowest | |
| 77 | sc-179 QA generated-title cleaning (`qa-deferred`) | 2 | Lowest | |
| 78 | sc-180 QA conversation-list state (`qa-deferred`) | 2 | Lowest | |
| 79 | sc-183 QA welcome M+ edge cases (`qa-deferred`) | 2 | Lowest | Live data first. |
| 80 | sc-182 QA M+ refresh efficiency (`qa-deferred`) | 2 | Lowest | |
| 81 | sc-181 QA sidebar activity order (`qa-deferred`) | 1 | Lowest | |
