# WCL Agent App — Handoff Guide for Coding Agents

This document is the single source of truth for a new coding agent picking up this
project with zero prior context. Read it fully before making changes.

---

## 1. Vision

An **interactive terminal app** where a user picks a raid encounter + difficulty
from a live menu (e.g. *The Venomous Abyss → Ula'tek → Heroic*) and then **chats**
with an AI agent that pulls and analyzes [Warcraft Logs](https://www.warcraftlogs.com)
data on demand.

The guiding requirement: **the agent must be able to answer ANY question that
Warcraft Logs data can support** — from high-level ("how are hunters performing
this season?") down to fine-grained ("which spells make up this player's damage on
this specific pull?"). If a question is answerable from WCL, the agent should be
able to get there, using a raw-GraphQL escape hatch as a last resort rather than
refusing.

Example interaction:
```
Selected: The Venomous Abyss > Ula'tek > Heroic
You: How well are hunters performing?
  [calling get_selected_encounter...]
  [calling compare_specs...]
Agent: On Heroic Ula'tek this season, Marksmanship leads (median ~306k dps, p95 ~344k) ...
```

---

## 2. Tech stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python `>=3.10` | Pinned to `3.14` via `.python-version`. |
| Dependency mgmt | **uv** | `uv sync` to install; `uv run …` to execute. |
| Agent framework | **Google ADK** (`google-adk`, installed 2.10.0) | Docs: <https://adk.dev> |
| LLM | **Gemini** (`gemini-3.6-flash`) via **Vertex AI** | Auth = gcloud **ADC**, global endpoint. |
| Data source | **Warcraft Logs v2 GraphQL API** | OAuth2 client-credentials. |
| Cache | **Redis** (`redis.asyncio`), optional | Shared WCL cache, feature 014 (§19). Tests use `fakeredis`. |
| Analysis | **pandas** (3.x) | Percentile/quantile math + groupby. |
| Packaging | hatchling; console script `wcl` | `uv run wcl` or activate venv then `wcl`. |
| Frontend | **React** + **Tailwind CSS v4** + **shadcn/ui** | Build UI from shadcn registry items found via the shadcn MCP; hand-built only when none fits (constitution Principle VII). Generated files in `frontend/src/components/ui/`. |

---

## 3. How to run

1. **Install:** `uv sync`
2. **Credentials** — copy `.env.example` to `.env` and fill in:
   - `WCL_CLIENT_ID` / `WCL_CLIENT_SECRET` — create a client at
     <https://www.warcraftlogs.com/api/clients/>. **The client ID is a UUID
     (36 chars)**; a short value means you grabbed the wrong thing (this actually
     tripped us up once — a v1 token instead of a v2 client). The v2 client form
     requires a redirect URL; the client-credentials flow never uses it, so any
     placeholder (e.g. `http://localhost:8000/callback`) is fine.
   - Gemini auth via **Vertex + ADC** (no API key in the repo):
     ```
     GOOGLE_GENAI_USE_VERTEXAI=TRUE
     GOOGLE_CLOUD_PROJECT=<your-gcp-project>
     GOOGLE_CLOUD_LOCATION=europe-west1   # general region; not used for model calls
     WCL_MODEL_LOCATION=global            # where every model call runs (feature 016)
     ```
     Then run once: `gcloud auth application-default login` (and ensure the
     Vertex AI API is enabled on the project).
   - Fallback (AI Studio API key instead of Vertex): set
     `GOOGLE_GENAI_USE_VERTEXAI=FALSE` and `GOOGLE_API_KEY=…`.
3. **Run:** `uv run wcl` (or `uv run python main.py`). With the venv activated,
   plain `wcl` works because `.venv/bin` is on `PATH`.

> `.env` is loaded from the **current working directory** via `load_dotenv()`.
> Run from the project root (or a dir containing a `.env`), or export the vars.

---

## 4. Architecture & file map

```
main.py                    # thin launcher -> wcl_agent.cli.run()
pyproject.toml             # uv deps + [project.scripts] wcl = "wcl_agent.cli:run"
.python-version            # 3.13
.env.example               # required env vars (copy to .env)
documentation/ai_guide.md  # this file
wcl_agent/
  __init__.py              # `from . import agent` (ADK convention)
  cli.py                   # env check -> menu -> asyncio chat REPL (the `wcl` entry point)
  menu.py                  # interactive zone/encounter/difficulty selection
  agent.py                 # root_agent: Gemini model + instruction + all 15 tools
  client/                  # Warcraft Logs API access
    wcl_client.py          # AsyncWCLClient (httpx, OAuth + GraphQL) per loop, lanes, acheck_rate_limit
    aio.py                 # gather_settled / unwrap: async fan-out inside a tool
    queries.py             # GraphQL strings for the menu + leaderboard
  cache/                   # shared Redis WCL cache (feature 014)
    cache.py               # get_or_load, key families, stats
    cache_models.py        # Pydantic value models, one per family
    normalize.py           # server_slug, FINAL_AFTER, is_finished
  tools/                   # ADK function tools
    tools.py               # LEADERBOARD tools (rankings distribution / spec compare)
    report_tools.py        # DEEP-DIVE tools (report tables/events/graph, characters, raw GraphQL)
    benchmark.py           # compare_player_to_cohort, report_link
    cooldowns.py           # get_cooldown_usage
    fight_time.py          # player resolution, dead windows, eligible time
    provenance.py          # provenance + completeness envelope on tool results
  guides/                  # coaching briefs (feature 015)
    guide_meta.py          # injected brief loader (set_brief_loader / get_brief)
    guides_tool.py         # get_coaching_brief
  llm/                     # chat models
    models.py              # startup model discovery + validation
    model_retry.py         # rate-limit retry loop, RetryingGemini / RetryingClaude, 429 fallback to the same-class sibling (021)
    vertex.py              # model location, client kwargs, Model Garden catalog
    genai_compat.py        # force-build google-genai serializers
    context_trim.py        # stub old tool results in the model context
  game/                    # WoW reference data
    constants.py           # class/spec PascalCase filter map + METRICS + normalizer
    roster.py              # live class/spec roster from WCL game data
    patch.py               # current patch, M+ season, guide freshness
```

### Control flow
1. `cli.run()` → `asyncio.run(_main())`.
2. `_check_env()` validates WCL creds + (Vertex project **or** API key).
3. `menu.select_encounter()` runs one GraphQL discovery call, presents numbered
   menus, and returns a **context dict**:
   `{zoneID, zoneName, encounterID, encounterName, difficultyID, difficultyName, partition}`.
4. An `InMemorySessionService` session is created **with `state=context`**. This is
   how tools know what encounter to analyze — they read it via `ToolContext.state`.
5. A `Runner` drives `root_agent`; the REPL loops `input()` → `runner.run_async()`,
   printing `[calling <tool>...]` for each function call and the final text.

---

## 5. Warcraft Logs v2 API — the facts that matter

- **Endpoints:** token `https://www.warcraftlogs.com/oauth/token` (HTTP Basic
  `client_id:client_secret`, body `grant_type=client_credentials`), GraphQL
  `https://www.warcraftlogs.com/api/v2/client`. Tokens are ~1-year lived and
  cached in-process by the `WCLClient` singleton.
- **Rate limit:** points-per-hour (this client: **720/hr**). Query
  `rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }`. Deep paging
  and `events` are the expensive calls.
- **Menu discovery:** `worldData.zones { id name frozen difficulties{id name}
  partitions{id name default} encounters{id name} }`. The menu shows non-frozen
  zones with encounters, sorted by id desc (newest first).
- **Leaderboard:** `worldData.encounter(id:).characterRankings(difficulty,
  metric, className, specName, page, partition)` returns a **JSON scalar** (no
  sub-selection). Shape: `{ page, hasMorePages, count, rankings:[ {name, class,
  spec, amount, bracketData(=item level), startTime, report{code,fightID},
  server{name,region}, ... } ] }`, **sorted by `amount` descending**.
  - **Gotcha:** entries have **no `rankPercent`** field (contrary to some docs);
    percentiles are computed **client-side** from the `amount` distribution.
  - **Gotcha:** the top-level `count` is the **per-page** count (100), NOT the
    population total. We expose `more_pages_available` instead.
  - There is **no server-side "last 7 days"** filter. Product decision: we analyze
    the **current-season leaderboard** (default partition), i.e. top-of-distribution.
- **Difficulty IDs (retail):** Mythic 5, Heroic 4, Normal 3, LFR 1. Always read
  `zone.difficulties` at runtime; do not hardcode.
- **Class/spec filters:** PascalCase, space-free (`Hunter`, `Marksmanship`,
  `DeathKnight`, `BeastMastery`). Display names have spaces — different thing. See
  `constants.CLASS_SPECS`.
- **Report deep-dive:** `reportData.report(code:)` exposes:
  - `fights` — pulls with `id, name, encounterID, difficulty, kill,
    averageItemLevel, friendlyPlayers(actor ids), ...`
  - `masterData { actors(type:"Player"){id name subType(=class)} abilities{gameID name type} }`
  - `table(dataType, hostilityType, fightIDs, sourceID, abilityID)` → **JSON scalar**.
    Shape `{ data: { entries: [ {name, guid, total, ...} ] } }`. Setting `sourceID`
    to a player scopes entries to **that player's abilities** (this is how the
    spell-breakdown question is answered).
  - `graph(...)` → JSON scalar.
  - `events(...) { data nextPageTimestamp }` — **NOT a scalar**; it's a paginator
    object and MUST have a sub-selection. `data` is the JSON list.
  - `rankings(fightIDs)`, `playerDetails(fightIDs)` → JSON scalars.
- **Character history:** `characterData.character(name, serverSlug, serverRegion)`
  with `zoneRankings(zoneID, metric, difficulty)` / `encounterRankings(encounterID,
  metric, difficulty)` → JSON scalars.
  - **Gotcha:** `zoneRankings.metric` and `encounterRankings.metric` expect
    **different enum types**. We sidestep this by **inlining the metric as a
    validated enum literal** rather than a typed `$variable`.
  - `serverSlug` is lowercase-hyphenated (`Stormrage` → `stormrage`); handled by
    `_server_slug()`.

### Enum-inlining pattern (important)
For arguments whose GraphQL **enum type name** is fiddly or inconsistent
(`dataType`, `hostilityType`, `metric` on character queries), we **validate the
value against a whitelist and inline it directly into the query string** (enum
literals are unquoted, so no `$var` type declaration is needed). Scalar args
(`code`, `fightIDs`, `sourceID`, `abilityID`, ...) stay as typed GraphQL variables.
This is deliberate — it makes the tools robust to schema type-name quirks. Keep
using it when adding tools.

---

## 6. The tools (agent capabilities)

Registered in `agent.py`, 15 total. Every tool returns a `dict` with a
`"status"` key (`"success"`/`"error"`, with `error_message`) so the model can
recover. The agent instruction teaches the **chaining method**: leaderboard parse
→ its `report_code` + `fight_id` → `get_report_table(source_id=…)` for detail.

**Leaderboard / population (`tools.py`):**
- `get_selected_encounter(tool_context)` — echoes the menu selection from session state.
- `get_spec_options(class_name)` — valid PascalCase spec filters for a class.
- `get_rankings_distribution(class_name, spec_name, metric, num_pages, tool_context)`
  — pages the leaderboard, computes `amount` percentiles (min/p25/median/p75/p90/
  p95/p99/max), per-spec breakdown, and top parses (each with `report_code` +
  `fight_id`). `num_pages` capped at 10.
- `compare_specs(class_name, metric, num_pages, tool_context)` — all specs side-by-side.

**Report deep-dive (`report_tools.py`):**
- `get_report_fights(report_code)` — fights + `players{id:{name,class}}` map.
- `get_report_table(report_code, data_type, fight_id, source_id, ability_id, hostility_type)`
  — **the workhorse** (damage/healing/casts/buffs/debuffs/deaths/etc.).
- `get_report_events(report_code, data_type, fight_id, source_id, ability_id, hostility_type, limit, start_time)`
- `get_report_graph(report_code, data_type, fight_id, source_id, hostility_type)`
- `get_report_rankings(report_code, fight_id)`
- `get_report_player_details(report_code, fight_id)` — gear/talents/specs.
- `get_report_master_data(report_code)` — actor/ability id maps.

**Individual characters (`report_tools.py`):**
- `get_character_zone_rankings(name, server, region, zone_id, metric, difficulty)`
- `get_character_encounter_rankings(name, server, region, encounter_id, metric, difficulty)`

**Utility / escape hatch:**
- `check_rate_limit()` — remaining API points.
- `run_wcl_graphql(query, variables_json)` — **write any read-only GraphQL**.
  Roots: `worldData, reportData, characterData, guildData, gameData, rateLimitData`.
  This is the "answer anything" backstop; the instruction tells the agent to use
  it rather than say it can't.

Convention for `fight_id`/`source_id`/`ability_id` args: **`0` means "all/none"**
(translated to a `None` GraphQL variable). This keeps tool schemas simple for the LLM.

Large results are size-capped by `_cap()` (`MAX_JSON_CHARS = 60000`); over the cap
it returns a truncation note + preview telling the model to narrow filters.

---

## 7. How to add a new tool (recipe)

1. Add an `async def` function in `tools.py` or `report_tools.py` (every tool is a coroutine):
   - **Primitive args** (`str`/`int`), sensible defaults for optionals.
   - **A thorough docstring** — ADK turns the docstring + type hints into the tool
     schema the LLM sees. Describe purpose, each arg, and the return shape.
   - **Return a dict** with `"status"`; wrap the WCL call in `try/except` and
     return `{"status":"error","error_message":…}`.
   - For GraphQL, reuse `await _report_field(...)` (report fields) or
     `await wcl_client.get_async_client().query(...)`. Fan out with `aio.gather_settled`.
     **Inline enum-valued args after whitelist validation**; keep scalars as `$vars`.
   - Wrap potentially large JSON in `await _acap(...)` (sizes it off the loop).
2. Register the function in `agent.py`'s `tools=[…]` list (and import it).
3. Update the agent `instruction` if it introduces a new capability/workflow.
4. **Smoke-test it live** against a real report/character before trusting it (see §8).
   GraphQL type/shape errors only surface at call time.

---

## 8. Testing & verification

There are no automated tests yet; verification is live smoke-testing with `uv run`.
Known-good fixtures (current season as of handoff):
- Zone **53** = *The Venomous Abyss*; encounter **3492** = *Ula'tek*; Heroic = **4**;
  default partition **1**. Character example: `Innerhunt` / `Stormrage` / `US`.
- A report code seen from a top parse: `a72VmgW3QnNhXz9H` (has an Ula'tek fight id 7).
  Report codes rotate; pull a fresh one from `get_rankings_distribution` top parses.

Useful checks:
```bash
# imports + agent builds with all tools
uv run python -c "from wcl_agent.agent import root_agent; print(len(root_agent.tools))"

# WCL auth/GraphQL smoke (no LLM) — prints points budget
uv run python -c "import asyncio; from dotenv import load_dotenv; load_dotenv(); \
from wcl_agent.client.wcl_client import acheck_rate_limit; print(asyncio.run(acheck_rate_limit()))"

# menu discovery (no LLM)
uv run python -c "import asyncio; from dotenv import load_dotenv; load_dotenv(); \
from wcl_agent.client.wcl_client import get_async_client; from wcl_agent.client.queries import MENU_DISCOVERY; \
q = lambda: get_async_client().query(MENU_DISCOVERY); \
print([z['name'] for z in asyncio.run(q())['data']['worldData']['zones']])"
```
To test a tool, construct a stub context: `class Ctx: state = {…}` and call the tool
with `Ctx()`. To test the whole agent non-interactively, build a `Runner` +
`InMemorySessionService` (state = a context dict) and feed a `types.Content`
message — see the git history / this session's transcript for the exact snippet.

Harmless noise: `UserWarning: [EXPERIMENTAL] JSON_SCHEMA_FOR_FUNC_DECL` from ADK.

---

## 9. Gotchas already discovered (don't re-learn these)

1. WCL v2 needs a **v2 API client** (UUID id), not a v1 token; redirect URL is
   required by the form but unused by client-credentials.
2. Leaderboard entries have **no `rankPercent`**; compute percentiles from `amount`.
3. Leaderboard `count` is per-page, not the population total.
4. `events` is a **paginator object** — needs `{ data nextPageTimestamp }`.
5. Character `zoneRankings.metric` ≠ `encounterRankings.metric` enum type — inline
   the metric literal.
6. There is **no rolling-week** filter on rankings — we use the current-season
   leaderboard by design.
7. pandas 3.x: guard against missing columns before `pd.to_numeric(...).dropna()`
   (a missing column makes `df.get(col)` return `None`, and `pd.to_numeric(None)`
   yields a scalar that has no `.dropna()`).

---

## 10. Current status

**Working and live-verified:** WCL OAuth + GraphQL; menu discovery; all 15 tools
(leaderboard, report deep-dive, character, rate-limit, raw GraphQL); Gemini via
Vertex + ADC; the `wcl` console entry point; and the flagship end-to-end chain —
the agent answers "which spells make up a top Marksmanship hunter's damage?" by
going leaderboard → report → per-ability table.

**Not done / ideas for next steps:**
- Automated test suite (pytest) with recorded/mock GraphQL responses.
- Guild-centric tools (`guildData.guild`, roster/progression) — currently only
  reachable via `run_wcl_graphql`.
- Report search (`reportData.reports(...)`) as a first-class tool.
- Streaming token-by-token output in the REPL (currently prints on final event).
- Points-budget guard before deep paging / large `events` pulls.
- Optionally surface the partition **name** (e.g. "12.1") into session state; the
  agent currently sees only the partition id and may label it "Season 1".

## 11. Feature 002 — agent enhancements (web app)

Implemented in `specs/002-agent-enhancements/` (see its plan/spec/tasks). Summary
for future agents:

- **Tracked raids** (`tracked_raids` table, `backend/app/services/raids.py`,
  `api/raids.py`): the agent-runner backbone (`agent_runner.stream_response`) now
  yields tool `args` + `result`; the WS layer upserts a raid on any successful
  report-scoped tool call and exposes list + one-click investigate endpoints.
- **Durable sessions**: `InMemorySessionService` → ADK `DatabaseSessionService`
  (async-native in ADK 2.10; reuses the app's async engine — no sync psycopg
  driver needed). Installed in the lifespan via `agent_runner.set_session_service`.
  Interrupted replies persist as `messages.status = "partial"`.
- **Web grounding**: `build_agent` adds a `web_search` grounding sub-agent tool for
  Gemini models only; the runner emits a `grounding` frame.
- **Model discovery**: `wcl_agent/llm/models.py` lists the Vertex Model Garden catalog
  (`wcl_agent/llm/vertex.py`), probes the newest versions per class and keeps the newest
  that answer (feature 016; `WCL_MODEL_DISCOVERY=static` probes `WCL_GEMINI_MODELS` /
  `WCL_ANTHROPIC_MODELS` instead). The result is cached 6 h (`model_catalog` family),
  lives on `app.state` and is read via `backend/app/model_state.py` (single source of
  truth for the default). Claude is registered with ADK's `LLMRegistry`. Every model
  client is built at `vertex.model_location()` (`WCL_MODEL_LOCATION`, default `global`),
  never at `GOOGLE_CLOUD_LOCATION`.
- **PDF export**: `captured_graphs` table + `services/graphs.py` capture graph JSON
  during chat; `services/pdf_report.py` renders analysis + charts (WeasyPrint since
  feature 017, §22); `api/reports.py` streams it. (Feature 007 inserts a findings-synthesis step before
  the render — the PDF body is now an analytic findings document, not the transcript.)
- **Testing note**: ORM uses portable column types (`Uuid`, `JSON`/`JSONB`
  variant) so `backend/tests/` run on in-memory SQLite (`conftest.py`); live
  Postgres/Vertex flows are covered by the quickstart.

## 12. Feature 005 — guild context, interactive artifacts & faster analysis

Implemented in `specs/005-guild-context-artifacts/`. Summary for future agents:

- **Global profile** (`user_characters`, `guild_profile` tables,
  `api/profile.py`, `db/repository.py`): a single default-tenant profile (self +
  friends + one main guild). `services/profile_context.build_preamble` turns it into
  a non-persisted "KNOWN PLAYER CONTEXT" preamble that `agent_runner.stream_response`
  prepends to the model input only (via the new `context_preamble` arg); the stored
  user message is unchanged. Empty profile → empty preamble → behavior unchanged.
- **Interactive charts** (`artifacts` table): the agent calls the dependency-light
  `create_chart` tool (`wcl_agent/tools/tools.py`) which returns a validated `ChartSpec`.
  `ws._handle_tool_end` persists it, derives a Plotly figure
  (`services/charts.chart_spec_to_plotly`), and emits an `artifact` frame; the
  frontend renders it via a lazy-loaded `PlotlyArtifact`. The same spec renders to
  matplotlib SVG for the PDF (`chart_spec_to_svg`, feature 017) — one spec, two renderers.
  Captures are linked to their agent message at turn end via
  `repo.assign_message_seq_to_turn_captures` and re-render on reload.
- **Math/LaTeX**: `StreamMarkdown` enables Streamdown's first-class `plugins.math`
  slot (remark-math + rehype-katex); KaTeX CSS imported in `main.tsx`. The PDF
  typesets inline and block maths as matplotlib-mathtext SVG, falling back to plain
  text (`services/pdf_report.py`, §22). Currency like "$5" is never treated as math.
- **WCL query cache**: *superseded by feature 014* — the in-process cache behind
  `query()` is gone; see §19 for the shared Redis cache.
- **Per-message PDF**: `GET /api/conversations/{id}/messages/{message_id}/report.pdf`
  (`api/reports.py`) renders one agent reply + its originating question + that
  message's charts/graphs, excluding other messages.
- **Auto spec guides** (`services/guide.py`): locking a character/guild schedules a
  non-blocking `asyncio` task that resolves the active spec from WCL and generates a
  guide via the **web-search-capable guide model** (`WCL_GUIDE_MODEL`), reusing
  `stream_response` over a disposable session. Status flows `pending → ready|failed`;
  a bogus name still saves (status `failed`) and the agent answers without a guide.

New env vars (also in `.env.example`):

```
WCL_GUIDE_MODEL=gemini-3.6-flash   # web-search-capable model for background guides
```

## 13. Feature 006 — multi-tenancy (invite-only accounts & private workspaces)

Implemented in `specs/006-multi-tenancy/`. Summary for future agents:

- **Identity/tenancy tables** (`db/models.py`): `users` (global, Argon2id `password_hash`,
  `is_platform_admin`), `tenants` (a workspace), `tenant_memberships`, `invitations`,
  `auth_sessions` (named to avoid ADK's `sessions` table), `password_reset_tokens`,
  `auth_audit_events`. v1 is **one tenant per user**, auto-provisioned at invite acceptance;
  the membership tables are retained so multi-member workspaces can land later without rework.
- **Schema is Alembic now** (`backend/migrations/`, `alembic.ini`) — `main.lifespan` no
  longer creates/alters tables (`create_all` survives only in SQLite test fixtures). Four
  migrations: `0001_baseline`, `0002_auth_tenancy`, `0003_tenant_columns` (adds `tenant_id`
  to the 7 owned tables, backfills to the founder, per-tenant uniqueness), `0004_rls`
  (ENABLE+FORCE RLS + policies + runtime-role grants, Postgres only).
- **Auth building blocks** (`app/auth/`): `passwords` (Argon2id off the loop, bounded),
  `tokens` (CSPRNG + sha256 digest), `sessions` (opaque, `__Host-` cookie, idle+absolute
  expiry), `csrf` (**HMAC-derived, stateless** — `/me` recomputes it so a reload recovers
  it), `dependencies` (`require_session`/`require_platform_admin`/`require_csrf`/
  `get_tenant_db`), `rate_limit`, `redaction`.
- **Tenant scoping** (`app/tenancy/context.py`): `RequestIdentity` (the only authority;
  never from client input), `tenant_session`/`tenant_scope` set transaction-local
  `app.tenant_id` so RLS agrees with the app predicate; `commit_and_rescope` re-sets it
  after a mid-handler commit. Every `repository.py` function takes keyword-only `tenant_id`;
  no row is fetched by id alone (foreign/absent → `None` → 404).
- **WS** (`api/ws.py`): the handshake authenticates (cookie + Origin) before `accept()`,
  re-validates each turn (mid-session disable takes effect), scopes captures + ADK
  `user_id = str(tenant_id)`. (The WCL cache key used to be tenant-scoped too; feature 014
  made WCL data a shared, cross-tenant cache — see §19.)
- **Founder bootstrap**: `backend/cli/bootstrap_admin.py` (no HTTP path) creates the first
  platform admin; it must run between `alembic upgrade 0002_auth_tenancy` and `upgrade head`
  (the `0003` backfill needs the founder). **`backend/cli/init_db.py` orchestrates the whole
  thing** — `upgrade 0002 → bootstrap (iff no admin) → upgrade head` — idempotently, reading
  `BOOTSTRAP_ADMIN_EMAIL`/`BOOTSTRAP_ADMIN_PASSWORD`; this is the one command to run for a
  fresh/reset DB or any later upgrade.
- **Link delivery seam** (`services/link_delivery.py`): v1 returns invite/reset links to the
  admin to copy & share (no email); the raw token rides in the URL **fragment**, shown once.

New env vars (also in `.env.example`): `APP_DB_USER`/`APP_DB_PASSWORD` (runtime role),
`DATABASE_OWNER_URL` (Alembic owner), `SITE_URL`, `SESSION_COOKIE_SECURE`, `SECRET_KEY`.

## 14. Feature 007 — captured-metadata reuse, findings reports & role-aware profiles

Implemented in `specs/007-metadata-reports-profiles/`. All three slices are additive —
empty metadata store + unset roles reproduce feature-006 behavior byte-for-byte.

- **Captured-metadata reuse (US1)**: new per-tenant tables `known_players` /
  `known_encounters` (`db/models.py`, migration `0005_known_entities` — RLS mirrors
  `0004_rls`). `services/known_entities.py` extracts + best-effort upserts them off the
  existing tool-success hub (`ws._handle_tool_end`) — players from
  `get_character_{zone,encounter}_rankings` (identity from args; `get_report_master_data`
  actors are **not** captured, no server/region), encounters from `find_encounter` matches
  with a numeric id. Captures use a savepoint so a conflict never poisons sibling captures.
  `profile_context.build_preamble` gained `known_raids/known_players/known_encounters/
  known_guilds` kwargs and appends a bounded `RECENTLY SEEN (this account)` block (known
  guilds are **derived** from `tracked_raids.guild` — no table). `ws._handle_turn` fetches
  the recency-capped lists and passes them in.
- **Findings reports (US2/US3)**: `services/report_synthesis.synthesize_findings` runs a
  one-shot, non-web-search `genai` call off the event loop (`to_thread` + `wait_for`
  timeout, `WCL_REPORT_MODEL`) that turns the in-scope messages into a findings document.
  `api/reports._synthesize_and_render` is the shared pipeline for both scopes; the result
  becomes `ReportDocument.body_markdown` for `render_report_pdf` (§22). Fail-closed:
  synthesis error/timeout/empty output → `500`, no partial file (the model emits its own
  "no substantive findings" doc for chit-chat).
- **Role-aware profile (US4)**: nullable `user_characters.raid_role` override column
  (migration `0006_raid_role`). `wcl_agent/game/constants.SPEC_ROLES` + `role_for_spec()` are the
  spec→Tank/Healer/DPS SSOT; `effective_role = raid_role or role_for_spec(active_spec)` is a
  computed field on `CharacterOut`. New `PATCH /api/profile/friends/{id}` (`FriendPatchIn`)
  edits a friend's role in place; `PUT /self`/`POST /friends` accept `raid_role`.
  `profile_context._ident` appends the effective role (unset ⇒ byte-identical). Frontend:
  a per-character role select (inferred vs set) and a friendly duplicate-friend message.

New env var (also in `.env.example`):

```
WCL_REPORT_MODEL=gemini-3.6-flash  # non-web-search model for findings-report synthesis
```

## 15. Feature 008 — profile & class-guide pages (dedicated page + shared guide library)

Implemented in `specs/008-profile-class-pages/`. Three additive slices; empty library +
unresolved specs reproduce feature-007 agent-context behavior byte-for-byte.

- **Dedicated profile page (US1)**: the former in-chat `ProfilePanel` modal is promoted to a
  guarded route `/profile` (`frontend/src/pages/ProfilePage.tsx`, mirrors `/admin/users`) with
  two Warcraft-themed tabs. **Characters** (`components/profile/CharactersTab.tsx`) is the old
  profile behavior verbatim (self/friends/roles/guild, friendly duplicate message). Both tabs
  stay mounted (toggled with `hidden`) so switching preserves in-progress input. `App.tsx` now
  navigates to `/profile` instead of opening a modal; `ProfilePanel.tsx` is deleted.
- **Shared spec-guide library (US2)**: a new **GLOBAL** table `spec_guides` (`db/models.py`,
  migration `0007_spec_guides`) keyed by `(class_name, spec)` — **no `tenant_id`, no RLS**
  (deliberate deviation, plan Complexity Tracking: generic content, no user data; runtime role
  granted DML like `0004`). `services/guide.ensure_spec_guide(class, spec, *, force=False)` is
  the single lifecycle: `ready`&!force or `pending` → no-op (dedup); absent|`failed`|`force` →
  upsert `pending` + spawn the existing off-loop `_generate_text`/`_GUIDE_PROMPT` path (reuses
  `_spawn`, re-keyed to `(class, spec)`; `IntegrityError`-safe). This makes `failed` always
  **retryable** (fixes the stuck-guide defect). New `api/guides.py` (`GET /api/guides` roster+
  status merge via `build_guide_roster`, `GET /api/guides/{class}/{spec}`, `POST …/generate`)
  uses the **non-tenant** `db/session.get_session`, `require_session`/`require_csrf`, validates
  against `CLASS_SPECS` (404), and rate-limits generate per user via `auth/rate_limit.guide_limiter`
  (`WCL_GUIDE_GENERATE_PER_MINUTE`, default 10 → `429 rate_limited` + `Retry-After`). Frontend
  `components/profile/ClassGuidesTab.tsx`: full roster grouped by class, status chips, Generate/
  Retry/Refresh, View (renders markdown via existing `StreamMarkdown`), polls while any pending.
- **Reconcile + migrate-drop (US3)**: `run_character_guide` now resolves `(class, spec)`,
  persists it on the character (`repo.set_character_spec`), then calls `ensure_spec_guide` — no
  per-character markdown (auto-fetch on add reuses a ready guide → zero regeneration). Character
  guide columns (`guide_markdown/guide_status/guide_updated_at`) are **dropped** by migration
  `0008_drop_guide_columns` (revision id kept short for `alembic_version varchar(32)`).
  `CharacterOut.guide_status`/`guide_updated_at` are now **derived** from the matching
  `spec_guides` row (`CharacterOut.from_character`; `api/profile.py` batch-loads via
  `repo.get_spec_guides_for`). `build_preamble` takes a `spec_guides: {(class,spec)->markdown}`
  map (empty ⇒ byte-identical); `ws._handle_turn` fetches the ready guides for the profile's
  specs and passes them in.

New env var (also in `.env.example`):

```
WCL_GUIDE_GENERATE_PER_MINUTE=10   # per-user cap on manual spec-guide generation (feature 008)
```

## 16. Feature 012 — multiple own characters

Implemented in `specs/012-multi-character-profile/`. Summary for future agents:

- **Storage**: own characters are `user_characters` rows with `role="self"`, at most
  `repo.MAX_OWN_CHARACTERS` (10) per tenant. No migration: the unique key already includes `role`.
  The old single self row is simply the first own character.
- **Repository**: `add_character(role=…)`, `update_character_role(role=…)`, `delete_character(role=…)`
  serve both own characters and friends. `find_character_identity` does a case-insensitive lookup
  across both roles, and `add_character` raises `CharacterConflict(code)` with one of
  `duplicate_character`, `duplicate_friend`, `already_friend`, `already_own` or `character_limit`.
  `get_profile` returns `(own: list, friends, guild)`. `upsert_self` and `get_self_character` are gone.
- **API**: `POST /api/profile/self`, `PATCH /api/profile/self/{id}` and `DELETE /api/profile/self/{id}`
  mirror the friends endpoints. A conflict returns 409 with the code as `detail`. `PUT /self` was removed.
  `ProfileOut` is `{own, own_limit, friends, guild}`.
- **Prompt**: `build_preamble(own_characters, friends, guild, …)`. With 0 or 1 own character the
  output is byte-identical to before. With 2 or more, the "You (self)" line lists them all and says
  "I/me/my" can mean any of them. Spec guides are grouped per `(class, spec)`, with a heading that
  names every character on that spec. The `<CONTEXT_RESOLUTION>` bullet in `wcl_agent/agent.py`
  tells the model to:
  - check which own characters appear in a report;
  - when several appear, cover each one or ask which is meant, and "never silently pick one";
  - when none appear, say so.
- **UI**: `CharactersTab.tsx` renders "Your characters" and "Friends" with one `CharacterList`.
  The Add button is disabled at `own_limit`, and the 409 codes map to friendly messages.

## 17. Performance fixes (QA sweep 2026-10-14)

Source: `qa-reports/2026-10-14/performance.md` (PERF-001…016). What future agents must know:

- **Tools are coroutines (feature 013, superseding the PERF-001 threads).** `build_agent`
  registers `TOOLS` directly; ADK awaits them on the loop. There are no WCL worker threads:
  never call WCL from a thread, and use `aio.gather_settled` for fan-out inside a tool
  (ordered results, per-item errors; cancelling the caller cancels the children; the tenant
  cache scope ContextVar travels with `await`).
- **WCL client** (`wcl_client.py`): one `AsyncWCLClient` (httpx) per event loop via
  `get_async_client()`; every module calls it as `wcl_client.get_async_client()` so tests
  patch one name (`backend/tests/wcl_fakes.install`, or `mock_async_client` over an
  `httpx.MockTransport` for client tests). Single-flight per cache key with
  cancel-on-last-waiter, a `LaneLimiter` (`WCL_MAX_CONCURRENCY` slots, background capped at
  `WCL_BACKGROUND_CONCURRENCY` and yielding to waiting chat lookups), and a 75 s per-query
  timeout. Wrap background work in `with background_lane():`. The cache stores raw response
  bytes; each hit parses a fresh object. Large tool results are sized with `_acap` off the
  loop, and the backend `gc.freeze()`s its startup heap (a GC walk of it stalled the loop
  ~80 ms).
- **Chat turn** (`api/ws.py`): the setup transaction closes before streaming. Captures,
  partial replies and the final save open their own `tenant_scope`. Never hold a session
  across `stream_response`. `DoneFrame` precedes `SuggestionsFrame(message_id=…)`.
- **Preamble**: it rides on `TurnStats.preamble` and `model_retry.inject_preamble` adds it to
  each `LlmRequest` (never stored in ADK history). The turn stats line logs
  `prompt_tokens` / `max_prompt_tokens` / `cached_tokens` / `trimmed`.
- **Old tool results** (`wcl_agent/llm/context_trim.py`): the before-model callback replaces
  large results older than `WCL_CONTEXT_KEEP_TURNS` turns with deterministic `_elided` stubs
  in the request only (new Content/Part objects; ADK's request copy shares nested objects with
  stored events, so never mutate in place). The prompt tells the model to re-fetch elided data.
- **Suggestions** (`api/ws.py`): `_handle_turn` returns the suggestions task; `_TurnSocket`
  serializes sends and the next turn cancels it.
- **Generated titles** (feature 019): after `done`, a chat with `title_source == "auto"` gets `services/conversation_titles.schedule_title` (claim `auto→generated` in the DB, cheap model, 15 s cap, then a `ConversationTitleFrame`); explicit/legacy names are never touched, and tests stub it in conftest.
- **Pinning** (feature 019): `PATCH /api/conversations/{id}` `{pinned: bool}` sets `conversations.pinned_at` (tenant-scoped, 404 for foreign ids, `updated_at` untouched); the sidebar groups pinned chats on top.
- **Guides/boot**: `_generate_text` is capped by `WCL_GUIDE_MAX_CONCURRENCY`; roster and
  profile reads use `with_text=False`; model probes run concurrently with a 10 s timeout;
  the greeting session id is per process.
- **Frontend**: streaming text lives in `lib/streamStore.ts` (only `LiveMessage` subscribes);
  `Sidebar`, `Composer`, `ModelSelect`, `MessageList` and `Ambient` are memoized with stable
  callbacks; `useSmoothText` commits at ~30 Hz; KaTeX (`lib/mathPlugin.ts`), the particle
  engine and non-chat pages are lazy chunks. `frontend/Dockerfile` has `dev` and `prod`
  (nginx) targets.
- **Deliberately not changed**: per-tenant WCL cache scoping (FR-019) and the raw `rankings`
  blob in `get_report_rankings` (feature 009 contract; trimmed from older turns anyway).
  Explicit context caching waits on the `cached_tokens` measurements.


## 18. Feature 013 — welcome page with my recent raids

Spec: `specs/013-welcome-recent-raids/`. What future agents must know:

- **Storage** (migration `0010_recent_raids`, RLS like `0005`): `recent_raids` (one row per
  report an own character was in, `UNIQUE(tenant_id, report_code)`), `recent_raid_characters`
  (links, cascade on character delete, so the list only shows raids a current own character
  attended), and `recent_raid_refresh` (one row per tenant: state + the claim lock).
- **Refresh** (`services/recent_raids.py`): `maybe_start_refresh` runs one conditional
  `UPDATE … RETURNING` claim (`repo.claim_refresh`; gate: not running or stale > 5 min, and
  never finished / > 15 min ago / own-character set changed / forced after a failure),
  commits, then `background.spawn`s `run_recent_raid_refresh`. That run: each own
  character's `recentReports` (feature 014: `char_id` + `char_reports` families, run
  concurrently), upsert, then details for new or non-final raids (and, for the M+ step, the newest 10 non-raid reports), from the shared
  `report_summary` entry, 10 at a time. Final = log ended > 2 h before the fetch. Errors become short codes
  (`wcl_unavailable`, `rate_limited`, `timeout`, `unknown`). All WCL calls are in
  `background_lane()`; no DB session is held across a WCL await.
- **API**: `GET /api/recent-raids` never waits for WCL. `POST /api/recent-raids/refresh`
  (CSRF) is Retry: 202 when it started a run, 200 with the current state otherwise, 409
  `no_characters`. `POST /api/raids/{code}/investigate` also accepts a code that is only a
  recent raid of this tenant, and turns it into a tracked raid first.
- **Feature 022 (Mythic+ on the welcome page)**: migration `0014_recent_mplus_runs` adds
  `recent_mplus_runs` and `recent_mplus_run_characters` (RLS). `_refresh_mplus_runs`
  (`services/recent_raids.py`) examines the newest 10 non-raid reports (`MPLUS_REPORT_BATCH`)
  with the same shared summaries as raids and keeps finished keys only (`keystoneLevel > 0`
  with a result). Caps: `RECENT_RAIDS_SHOWN=6`, `RECENT_MPLUS_SHOWN=6`.
  `POST /api/recent-raids/mplus/{report_code}/{fight_id}/investigate` starts the chat. The
  summary cache key is `wcl:v1:report:{code}:summary:keystone` (the suffix, not a `v2`,
  retired summaries cached before the keystone fields). Only the raid step can fail a
  refresh: an M+-only failure (a WCL error or timeout in the M+ step) is logged and the
  refresh still records `succeeded`, so stored raids and runs stay visible (decisions 36
  and 37). This is intentional; don't surface it as a refresh failure without a separate
  retry path.
- **UI**: `WelcomePanel.tsx` renders in a new chat under Barnaby's greeting, through
  `MessageList`'s `footer` slot. It polls every 3 s while a refresh runs (paused when the
  tab is hidden, gives up after 3 minutes).
- **Tests**: the SQLite test engine is one shared connection, so `test_recent_raids.py`
  queues spawned refreshes and runs them in `drain()` instead of concurrently with requests.

## 19. Feature 014 — shared Redis cache for Warcraft Logs data

Implemented in `specs/014-redis-wcl-cache/` (design: `documentation/redis_cache_spec.md`).

- **One way in**: `wcl_agent.cache.cache.get_or_load(family, key, model, loader, ttl=, force_refresh=)`.
  Values are Pydantic models from `wcl_agent/cache/cache_models.py`; keys only from `cache.keys`
  (never a user/tenant/conversation id — WCL data is public and shared by all tenants,
  superseding feature 006 FR-019). `loader()` returning `None` = "not found", cached 60 s.
- **Families**: `char_id`, `char_overview`, `char_reports`, `report_summary`
  (key `…:summary:keystone`), `report_player`, `oauth_token`, `world_zones` (README table). Call sites:
  `report_tools.resolve_character` / the two character-ranking tools /
  `load_report_summary` (also behind `get_report_metadata` and recent-raid details) /
  per-player `get_report_table`; `menu.load_world_zones` (patch, `find_encounter`, menu);
  `recent_raids._character_reports`; `AsyncWCLClient._token` (process memo in front).
  Adding an eighth family needs logged evidence (the `wcl_cost` lines).
- **Behaviour**: TTL × U(1, 1.1) jitter (none on the token); `SET lock:{key} NX PX` so N
  concurrent misses load once (losers poll ≤ 2 s, then load without writing:
  `lock_timeout`); corrupt values are deleted and reloaded; any `RedisError` → loader
  directly, `redis_error` counted (flushed later) and a 5 s per-loop circuit. One Redis
  client per event loop (like the WCL client), closed by `aclose_clients()`.
- **Client** (`wcl_client.py`): no result caching any more (single-flight stays); 429/5xx
  retried twice with backoff + `Retry-After`; every query carries
  `_cost: rateLimitData { pointsSpentThisHour }` (stripped before callers see it) and logs
  `wcl_cost`.
- **Metrics/stats**: `wcl:metrics:v1:{family}:{YYYYMMDD}` hashes (35 days);
  `GET /api/admin/cache-stats?days=N` (`api/cache_stats.py`, platform admin) via
  `cache.read_stats` / pure `cache.summarize`. INFO-less Redis → `redis: null`.
- **Performance (QA 2026-10-18)**: `char_id` (1 h) and `world_zones` (5 min) are memoised
  in-process in front of Redis; same-process lookups of one key share one load; outcomes are
  counted in memory and flushed every 2 s; values > 256 KB decode off the loop;
  `get_many_or_load` batches the recent-raids refresh (aliased queries, ~3 requests);
  leaderboard pages 2..N run concurrently; a 429 with a long `Retry-After` fails fast and
  blocks further calls until then; `acheck_rate_limit` answers from the budget every
  response now carries (≤ 30 s old).
- **Forced refresh**: `force_refresh=True` on the character tools; limited by
  `chat:refresh:{user}:{char}` (60 s). `ws.py` sets the turn's user with `set_refresh_actor`.
- **Tests**: Redis is off unless a test takes the `fake_redis` fixture (conftest); use
  `DeadRedis` (test_wcl_cache.py) for outage paths.
- **Raw fetch store** (feature 020): every successful WCL network call (cache misses only) is offered by `AsyncWCLClient._fetch` to the process-wide sink `wcl_client.set_fetch_sink`; in the app it is `services/fetch_persistence.FetchWriter` (started/stopped in `lifespan`, 5 s drain), which upserts one row per query key into the global `raw_fetches` table (`report_codes` JSONB + GIN; the DB strips `data._cost`). Bounded by `WCL_FETCH_PERSIST_QUEUE_MAX`/`_QUEUE_MB` (drops are logged, never raised); `WCL_FETCH_PERSIST_ENABLED=false` turns it off. CLI, evals and tests leave the sink unset. Nothing reads the table yet (sc-129).

## 20. Feature 015 — grounded, patch-aware Raid and Mythic+ guides

Implemented in `specs/015-grounded-class-guides/` (grounding plan:
`documentation/wow_guide_grounding_plan_v2.md`). Guides are **agent context first**.

- **Storage**: `spec_guides` keyed `(class_name, spec, content_type)` (`raid` | `mplus`).
  Columns split into the **published** version (`guide_markdown`, `brief`, `claims`,
  `game_patch`, `season`, `sources`, `briefing`, `evidence`, …) and the **latest run**
  (`status` pending/ready/needs_review/failed, `draft`, `review_issues`, `failure_reason`).
  Only `repo.publish_spec_guide` writes published columns; `hold_spec_guide` /
  `fail_spec_guide` never touch them. `stale_reason` + `last_wanted_at` drive freshness.
  New global table `guide_inaccuracy_reports`.
- **Pipeline** (`services/guide_pipeline/`, plain async functions on google-genai, no ADK):
  `briefing.build_briefing` → `datasheet.build_data_sheet` (cached 12 h) →
  `research.build_fact_sheet` (two calls: grounded collect, structured extract; then
  `filter_evidence` = `hard_filter` + `rank_evidence`; cached 6 h) →
  `authoring.author_claims` (tool-less; `accept_claims` drops claims whose evidence ids do
  not resolve) → `review_loop` (render → `checks.run_checks` → `review.review_claims` with
  `wcl_guide_review_model` → remove unconfirmed / `revise_claims` contradicted; ≤ 3 rounds)
  → publish / hold / fail. Entry point `run_guide_generation`; `services.guide.ensure_guide`
  dedups and spawns it under the generation semaphore. Every run logs one
  `guide run class=… outcome=… rounds=… duration_s=…` line.
- **Claims → outputs**: `render.build_brief` (ability ids only from the data sheet),
  `render_brief_text` (the agent's text: `[O|B|G,H|M|L]` tags, `LOG:` checks, no braces,
  ≤ 6000 chars, never truncated), `render_guide_markdown` (one bullet per claim with a
  `<!-- cN -->` marker, stripped by the API).
- **Agent side**: `wcl_agent.guides.guide_meta` holds an injected loader (`set_brief_loader`,
  `get_brief(class, spec, content_type, mark_used=)`); the backend registers
  `services.guide.load_brief_record` (published brief only, 60 s cache). The preamble
  (`services.guide.briefs_for_turn` + `profile_context.build_preamble`) classifies the turn
  (`services.content_type.classify_content_type`, unknown ⇒ Raid with a note) and inlines
  whole briefs within 12 000 chars, plus an index line per spec. Tools: `get_coaching_brief`
  (`wcl_agent/guides/guides_tool.py`) and `get_cooldown_usage(content_type=)` (content type from
  the fight's difficulty / report zone; reads the player's own Casts table). The instruction
  is an ADK `InstructionProvider` (`agent.build_instruction`) so `<CURRENT_TIME>` is live;
  `<COACHING_BRIEFS>` replaced `<GUIDES>`.
- **Roster**: `wcl_agent/game/roster.py` (`load_roster` from `gameData.classes`, cached 24 h;
  `roster_snapshot()` for sync callers; `CLASS_SPECS` is the fallback and includes Devourer).
- **Freshness**: `services.guide.maybe_scan_stale_guides()` (throttled 10 min; called by
  `GET /api/guides`, the preamble and startup) → `compute_stale_reason` → in-use guides
  regenerate; `touch_guide_wanted` stamps use (≤ hourly). Opening a stale guide queues it.
- **API**: `GET /api/guides` (one row per spec, `raid`/`mplus` summaries),
  `GET|POST /api/guides/{class}/{spec}/{content_type}[/generate|/reports]`,
  `GET /api/admin/guide-reports`. UI: `ClassGuidesTab` (Raid/Mythic+ switch, other-type dot),
  `GuideViewerDialog` (tabs, draft warning), `ReportGuideDialog`, `GuideIndicators`.
- **Accuracy check**: `backend/evals/guides/` (`python -m backend.evals.guides run|datasheet`),
  fixtures under `facts/`, `adversarial/`, `coaching/`; the scorers are unit-tested in
  `test_eval_scoring.py`. The baseline must come from `main` (procedure in
  `specs/015-grounded-class-guides/checklists/progress.md`).
- **Tests**: fake the model calls with `monkeypatch.setattr(llm, "generate_structured", …)`
  (reviewer schema `_ReviewDraft`), fake whole runs with `backend/tests/guide_fakes.fake_pipeline`;
  conftest keeps the stale scan inside its throttle window.


## 21. Backlog: todo.md ⇄ Shortcut

Planned work is tracked on the Shortcut **"Team 1"** board (workspace FRL-Personal). The
owner jots ideas in `todo.md`, and the board is kept in sync with it (constitution
Principle VIII).

- **Columns**: Backlog → Shortlist (owner's picks; tickets get the active iteration) →
  In Progress (move here *before* starting) → Under Review (implementation complete,
  waiting for live human testing) → Done (owner only).
- **Sizing**: story estimates are 1, 2, 3 or 5 only. A bullet too big for one 5-point
  story becomes an epic named after the bullet. Stories carry area labels (`ai`, `ui`,
  `ux`, `backend`, `data`, `infra`, `reports`, `security`, `performance`, `refactor`).
- **Strikethrough**: when Done tickets fully cover a `todo.md` bullet, the line becomes
  `~~line~~`.
- **Sync**: `/shortcut-sync` (`.claude/skills/shortcut-sync/`) runs the `shortcut-sync`
  sub-agent (`.claude/agents/shortcut-sync.md`). Run it when committing a feature. Pass
  `dry-run` to preview.

## 22. Feature 017 — proper PDF generation

Implemented in `specs/017-proper-pdf-generation/`. Only the rendering changed; the findings
synthesis (feature 007), both endpoints, file names and fail-closed errors are as before.

- **Input**: `api/reports._synthesize_and_render` builds a frozen `ReportDocument` (title,
  scope, `generated_at`, `body_markdown`, `question`, `partial`, `figures`) and runs
  `render_report_pdf(doc)` in `asyncio.to_thread`. `partial` comes from the source message's
  status (single-answer scope). `_figures` turns captured graphs (first) and artifacts into
  `ReportFigure`s; a chart that fails to validate or draw becomes `svg=None` and prints
  "Chart unavailable".
- **Pipeline** (`services/pdf_report.py`): `findings_to_html` = markdown-it-py (CommonMark +
  table, strikethrough, `tasklists`, `dollarmath` with `allow_space/allow_digits=False`) →
  maths render rules (mathtext → SVG `data:` image, fallback `_unwrap_latex_text`) → task
  boxes as ☑/☐ → `nh3.clean` allow-list → remote `<img>` → alt text → `ol start` counter fix →
  zero-width break points in tokens of 30+ characters (text only, never attributes). Then a
  small HTML shell (title block, partial note, findings, Charts section) and `REPORT_CSS`
  (CSS Paged Media: running header via `string-set`, `counter(pages)`, `break-after: avoid`,
  repeated `thead`) go to WeasyPrint with `URLFetcher(allowed_protocols={"data"})` and no
  `base_url`, so no network or `file:` fetches can happen.
- **Charts** (`services/charts.py`): `chart_spec_to_svg` and `graph_to_svg` share one print
  style (colour + line style/marker or hatch per series, thousands separators, legend only
  for 2+ series, title in the HTML caption). All PDF figures use the object-oriented
  `matplotlib.figure.Figure` API, never pyplot, because renders run concurrently in threads.
  `chart_spec_to_plotly` is unchanged.
- **Render limits (QA follow-ups)**: only the renderer's own images reach WeasyPrint. Equations
  are swapped in from placeholders after nh3, and every `<img>` the model wrote (including
  `data:` SVG or PNG) becomes its alt text; `data` is not an allowed URL scheme. Caps: findings
  output 16 k tokens, body 60 k characters, 200 rows per table, equations 300 characters / 60
  per report. Tables get extra break points in 15+ character tokens and `class="wide"` at 7+
  columns. `api/reports` runs all CPU-bound report work on one dedicated thread
  (`_RENDER_POOL`, `ThreadPoolExecutor(max_workers=1)`), never on the default executor the chat
  path shares. `_figures` (plain `GraphSource`/`ChartSource` inputs) runs alongside the findings
  call and submits each chart as its own job, so a waiting render gets in after at most one
  chart; a report without charts never queues. At most 20 figures per report (the rest are
  noted as "N more charts not shown"); the chart step has a 60 s deadline, after which charts
  print "Chart unavailable"; the PDF render has a 90 s timeout (queue wait included), then
  `500`. Caption `source` links are only drawn for http(s) URLs. Bar hatches are line
  patterns only (dot hatches cost about 300 ms per chart in WeasyPrint).
- **Links**: `wcl_agent.tools.benchmark.report_link(code, fight_id=None)` is the one WCL report URL
  builder, used for graph source links and the benchmark tool.
- **Deps**: `weasyprint`, `markdown-it-py`, `mdit-py-plugins`, `nh3` (test: `pypdf`);
  `reportlab` and the unused `markdown` were removed. The Docker image adds Pango/HarfBuzz,
  Noto CJK and Noto Color Emoji (DejaVu was already there). Cinzel and Alegreya Sans ship in
  `backend/app/assets/fonts/` (OFL) and load through `@font-face`.
- **Look (2026-10-20)**: the PDF copies the chat's agent-message theme, dark page included.
  Colours live in `services/report_theme.py` (hex versions of the frontend's oklch tokens).
  Charts and equations draw in cream on transparent backgrounds. `_FETCHER` allows `data:` plus
  `file:` URLs inside the fonts directory only. No emoji font may be named in a CSS font stack
  (Pango 1.56 draws digits as keycaps).
- **Tests**: `backend/tests/fixtures/findings/*.md` (23 docs: one per element/edge case plus
  7 real agent answers) are rendered and checked with pypdf for leftover markup and
  clickable links; plus `findings_to_html` units, a fetch-lockdown test, title block, page
  numbers, running header, repeated table header, Charts section and chart style tests.
