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
| Language | Python `>=3.10` | Pinned to `3.13` via `.python-version`. |
| Dependency mgmt | **uv** | `uv sync` to install; `uv run …` to execute. |
| Agent framework | **Google ADK** (`google-adk`, installed 2.10.0) | Docs: <https://adk.dev> |
| LLM | **Gemini** (`gemini-3.6-flash`) via **Vertex AI** | Auth = gcloud **ADC**, global endpoint. |
| Data source | **Warcraft Logs v2 GraphQL API** | OAuth2 client-credentials. |
| Analysis | **pandas** (3.x) | Percentile/quantile math + groupby. |
| Packaging | hatchling; console script `wcl` | `uv run wcl` or activate venv then `wcl`. |

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
     GOOGLE_CLOUD_LOCATION=global
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
  wcl_client.py            # WCLClient (OAuth + GraphQL) singleton + check_rate_limit
  queries.py               # GraphQL strings for the menu + leaderboard
  constants.py             # class/spec PascalCase filter map + METRICS + normalizer
  tools.py                 # LEADERBOARD tools (rankings distribution / spec compare)
  report_tools.py          # DEEP-DIVE tools (report tables/events/graph, characters, raw GraphQL)
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

1. Add a plain Python function in `tools.py` or `report_tools.py`:
   - **Primitive args** (`str`/`int`), sensible defaults for optionals.
   - **A thorough docstring** — ADK turns the docstring + type hints into the tool
     schema the LLM sees. Describe purpose, each arg, and the return shape.
   - **Return a dict** with `"status"`; wrap the WCL call in `try/except` and
     return `{"status":"error","error_message":…}`.
   - For GraphQL, reuse `_report_field(...)` (report fields) or `get_client().query(...)`.
     **Inline enum-valued args after whitelist validation**; keep scalars as `$vars`.
   - Wrap potentially large JSON in `_cap(...)`.
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
uv run python -c "from dotenv import load_dotenv; load_dotenv(); \
from wcl_agent.wcl_client import check_rate_limit; print(check_rate_limit())"

# menu discovery (no LLM)
uv run python -c "from dotenv import load_dotenv; load_dotenv(); \
from wcl_agent.wcl_client import get_client; from wcl_agent.queries import MENU_DISCOVERY; \
print([z['name'] for z in get_client().query(MENU_DISCOVERY)['data']['worldData']['zones']])"
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
- **Model discovery**: `wcl_agent/models.py` probes `WCL_GEMINI_MODELS` /
  `WCL_ANTHROPIC_MODELS` at startup; result lives on `app.state` and is read via
  `backend/app/model_state.py` (single source of truth for the default). Claude is
  registered with ADK's `LLMRegistry`.
- **PDF export**: `captured_graphs` table + `services/graphs.py` capture graph JSON
  during chat; `services/pdf_report.py` renders analysis + matplotlib charts;
  `api/reports.py` streams it.
- **Testing note**: ORM uses portable column types (`Uuid`, `JSON`/`JSONB`
  variant) so `backend/tests/` run on in-memory SQLite (`conftest.py`); live
  Postgres/Vertex flows are covered by the quickstart.
