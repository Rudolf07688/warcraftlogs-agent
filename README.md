# Warcraft Logs Agent App

An interactive terminal chat app that lets you pick a raid encounter and then ask
an AI agent to pull and analyze [Warcraft Logs](https://www.warcraftlogs.com)
ranking data for it.

Example session:

```
Selected: The Venomous Abyss > Ula'tek > Heroic

You: How well are hunters performing?
  [calling get_selected_encounter...]
  [calling get_spec_options...]
  [calling get_rankings_distribution...]
Agent: On Heroic Ula'tek this season, across 500 logged Hunter parses ...
```

## How it works

- **Frontend:** a terminal menu (`main.py`) that lists live zones/encounters/
  difficulties, then a chat REPL.
- **Agent:** built with [Google ADK](https://adk.dev) driven by **Gemini**
  (`wcl_agent/`). It calls tools that query the Warcraft Logs v2 GraphQL API,
  compute score percentiles / spec breakdowns, and report back.
- **Data:** the current-season ranking leaderboard for the selected fight
  (top-of-distribution; not a rolling last-7-days window).

## Setup

1. **Create a Warcraft Logs API client** at
   <https://www.warcraftlogs.com/api/clients/> and copy the `client_id` /
   `client_secret`.
2. **Set up Gemini via Vertex AI** using your gcloud Application Default
   Credentials (no API key stored in the repo):
   ```bash
   gcloud auth application-default login
   ```
   Make sure the Vertex AI API is enabled on your project.
3. **Configure env:**
   ```bash
   cp .env.example .env
   # edit .env: WCL keys + GOOGLE_CLOUD_PROJECT
   # (model calls run at WCL_MODEL_LOCATION=global; GOOGLE_CLOUD_LOCATION=europe-west1
   #  is the general region and is not used for models)
   ```
4. **Install deps with uv** (Python >= 3.10):
   ```bash
   uv sync
   ```
   PDF reports need Pango and a few fonts from the system (the Docker image has them).
   On Debian/Ubuntu: `sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0
   libharfbuzz-subset0 fonts-dejavu-core fonts-noto-cjk fonts-noto-color-emoji`.

> Prefer an AI Studio API key instead of Vertex? Set
> `GOOGLE_GENAI_USE_VERTEXAI=FALSE` and `GOOGLE_API_KEY=...` in `.env`.

## Run

```bash
uv run python main.py
```

Pick a zone → encounter → difficulty from the menu, then chat. Try:

- `How well are hunters performing?`
- `Which hunter spec is strongest here?`
- `What DPS do I need for a 95th percentile parse?`

Type `exit` to quit.

## Web app (streaming chat)

A browser frontend + FastAPI backend surface the same agent as a live, streaming
chat (incremental responses, model selector, dark UI, conversation history), with
state persisted in PostgreSQL. Everything runs locally via Docker Compose.

```bash
cp .env.example .env         # fill WCL keys, GOOGLE_CLOUD_PROJECT, POSTGRES_*
gcloud auth application-default login   # Vertex ADC (mounted into the backend)
docker compose up --build
```

- Frontend: <http://localhost:5173>  •  Backend API: <http://localhost:8000>
  (`/health`, `/api/models`, `/api/conversations`, `/api/raids`, WebSocket
  `/ws/chat`, PDF export `/api/conversations/{id}/report.pdf`)

Architecture:

- **Backend** (`backend/`): FastAPI + asyncio. WebSocket streams agent tokens;
  REST handles conversations/models/raids/reports. Reuses `wcl_agent/` and builds
  the agent per selected model. SQLAlchemy async + Postgres for state; ADK
  `DatabaseSessionService` persists agent session context in the same database.
- **Frontend** (`frontend/`): React 19 + Vite + **Tailwind v4 + shadcn/ui**, a
  single fixed high-fantasy theme (motion animations, streaming-safe markdown via
  Streamdown, ambient particles). Sidebar of past chats **and tracked raids**,
  model dropdown, chat box with tokens inscribing as they stream, and a
  per-conversation **Download PDF** button.

### Multi-tenancy — invite-only accounts & private workspaces (feature 006)

The app is invite-only: a single **founder** (platform admin) invites friends, and each
gets a **private workspace** (their own characters, friends, guild, conversations, raids,
reports) fully isolated from everyone else. See `specs/006-multi-tenancy/` for the spec.

**Two DB roles** (RLS defense-in-depth): a **migration-owner** (the compose superuser, owns
tables, runs Alembic) and a non-privileged **runtime** role the app connects as (no
`BYPASSRLS`, so row-level security constrains it). `.env` carries `DATABASE_URL` (runtime =
`APP_DB_USER`) and `DATABASE_OWNER_URL` (owner = `POSTGRES_USER`) — don't swap them. The
runtime role is created by **migration `0004_rls`** (from `APP_DB_USER`/`APP_DB_PASSWORD`,
run as the owner during `alembic upgrade head`; the owner needs `CREATEROLE`, which the
compose superuser has). So the flow is: start the DB, run the migrations/bootstrap below
(which create the role, schema, and RLS), **then** start the app.

**Schema is managed by Alembic** (not `create_all`). One command does first-time setup
**and** every later upgrade — migrate, create the founder if there isn't one, migrate the
rest of the way. It's idempotent, so it's safe to re-run on every deploy:

```bash
# Set the founder credentials once (e.g. in .env) so it runs non-interactively:
#   BOOTSTRAP_ADMIN_EMAIL=you@example.com
#   BOOTSTRAP_ADMIN_PASSWORD=<15+ chars>
uv run python -m backend.cli.init_db   # prompts for founder email/password if unset
```

Migration `0003` backfills existing rows to the founder tenant, so the founder must exist
before it runs — which is why setup can't be a single `alembic upgrade head`. `init_db`
runs the three steps in order; run them by hand if you prefer:

```bash
uv run alembic -c backend/alembic.ini upgrade 0002_auth_tenancy   # auth/tenant tables
uv run python -m backend.cli.bootstrap_admin                      # create the founder
uv run alembic -c backend/alembic.ini upgrade head               # tenant_id backfill + RLS
```

Then sign in at `/login`. Admins manage users + invitations at `/admin/users` and copy
the one-time invite/reset **links** to share (no email provider in v1). Auth uses Argon2id
password hashing, opaque server-side sessions in a `__Host-` cookie, and an HMAC-derived
CSRF token (sent as `X-CSRF-Token` on unsafe requests). Full verification steps are in
`specs/006-multi-tenancy/quickstart.md`.

### Enhancements (feature 002)

- **Tracked raids** — every report you successfully pull data for is recorded and
  listed in the sidebar (most-recent first). Click one to open a new chat that
  auto-investigates that raid. Stored in Postgres (`tracked_raids`).
- **Durable sessions** — the ADK agent session is persisted, so conversation
  *context* (not just the transcript) survives a backend restart. Interrupted
  replies are saved as `partial` rather than lost.
- **Web search** — Gemini models use native Google Search grounding (via a
  `web_search` sub-agent tool); the UI shows a "used web search" indicator.
  Anthropic/other models degrade gracefully with no web access.
- **Validated model list** — the model dropdown is discovered and probed at
  startup; only responsive models are offered, with a fallback + "degraded" notice
  if Vertex is unreachable. Since feature 016 the candidates come from Vertex's own
  catalog (see [Model discovery](#model-discovery-feature-016)).
- **PDF export** — download any conversation as a PDF with the written analysis
  plus the graphs the agent fetched (rendered with WeasyPrint since feature 017; see
  [Proper PDF reports](#proper-pdf-reports-feature-017)).

### Enhancements (feature 004 — Phase 3)

- **Cited source links** — when Barnaby uses Warcraft Logs data he now links the
  exact WCL page (report / `#fight=` / `&source=&type=`), built from identifiers the
  tools already return; links open in a new tab and are never fabricated for
  non-WCL content.
- **Accurate raid list** — each tracked raid shows its **own date/time** and the
  **boss(es)** pulled (kills marked ✓), de-duplicated by report code with a
  race-safe upsert so two near-simultaneous first references converge to one row.
- **Boss focus checkboxes** — after a report's fights are listed, its distinct
  bosses appear as a checkbox group; ticking some folds `(Focus on: …)` into your
  next question (selection resets per turn).
- **Fixed PDF export** — the markdown→PDF renderer now lays out GFM tables,
  numbered/intro-plus-bullet lists, and wraps long tokens; each answer sits under
  the question that prompted it.
- **Warm greeting** — a new chat shows a cached Barnaby greeting instantly (primed
  at startup, `GET /api/greeting`); the hidden kickoff is never shown and a failure
  just opens a clean chat.
- **High-fantasy UX polish (US6)** — one fixed theme (no switcher; the background
  toggle was removed), smooth "inscribed" streaming, tool calls rendered as
  **spellcasting cards** (summoning → casting → resolved/fizzled, with a `summary`
  and duration), ambient particles, and a reduced-motion path. Tool telemetry rides
  the existing WebSocket (`tool_end` gains optional `summary`/`ms`; a new
  `encounters` frame drives the picker). Icons are from game-icons.net (CC BY 3.0,
  credited in-app); no Blizzard assets.

### Grounded, evidence-based coaching (feature 009)

- **Evidence contract** — Barnaby's instruction is rewritten into tagged sections
  (`<EVIDENCE_CONTRACT>`, `<VALIDATION_BEFORE_ANALYSIS>`, `<BENCHMARK_POLICY>`,
  `<COACHING_POLICY>`, `<PERCENTILE_POLICY>`, `<OUTPUT>`, `<PERSONALITY>`, …): every
  number comes from a tool, inference is worded as inference, and when the log can't
  answer (positioning, intent) he says so and asks for the smallest missing input.
  Analytical answers lead with a verdict, then evidence, then ≤3 fixes each with
  evidence, expected change and confidence; the persona is applied last and may not
  bend a fact. `backend/tests/test_prompt_contract.py` guards the sections.
- **Provenance + completeness on every WCL tool result** — `provenance` (report,
  fight, encounter, difficulty, partition, metric, source, compare/timeframe,
  fetched_at) and `completeness` (`has_more`, `truncated`, `sample_size`,
  `sample_scope`), additive to the existing shapes. `get_report_rankings` takes
  `compare` (Rankings/Parses) and `timeframe` (Historical/Today) and returns a
  flattened `percentiles` list with overall **and** item-level-bracket percentiles.
- **`compare_player_to_cohort`** — replaces "compare to the top parse" with a
  matched cohort: ≤5 kill parses of the same encounter/difficulty/spec/metric/
  partition from the ~75th–95th percentile band, fight duration ±15%, medians and
  ranges of casts per minute per ability and throughput, labelled
  matched/directional/anecdotal; the player's rates are per minute **alive**.
  Budget-aware (shrinks below 100 / 40 remaining WCL points).
- **`get_cooldown_usage`** — "N of ~M opportunities" for major cooldowns over
  eligible time (fight minus time dead and intermissions), using the spec guide's
  machine-readable cooldowns; rates only (never "missed") when no guide is ready.
- **Guide freshness** — each shared spec guide now stores the patch it targets, when
  it was generated, its web sources and its major cooldowns (migration
  `0009_guide_provenance`; `alembic upgrade head` applies it). The Class Guides page
  shows "Patch 12.1 · date", a "May be out of date" badge for older/unknown patches,
  and the sources; the agent sees the same label on injected guides. Pre-existing
  guides show "Patch unknown" until regenerated.

See `specs/001-streaming-chat-frontend/quickstart.md`,
`specs/002-agent-enhancements/quickstart.md`,
`specs/004-raid-sourcing-ux/quickstart.md`, and
`specs/009-grounded-coaching-prompt/quickstart.md` for walkthroughs, and
`documentation/deployment.md` for the Cloud Run / Cloud SQL / Secret Manager plan.

Run the backend tests (pytest lives in the `test` extra):

```bash
uv run --extra test pytest -q
```

### Model rate-limit relief (feature 011)

Broad first questions and the one-click raid investigation make the agent do several
lookup rounds, each another model request, which can exhaust the provider's per-minute
allowance. The app now:

- **Retries rate-limited model calls** (HTTP 429 / 503 / 529, `RESOURCE_EXHAUSTED`) with
  exponential backoff inside one shared loop (`wcl_agent/model_retry.py`); the SDKs' own
  retries are disabled so waits never nest. While waiting, the chat status reads
  *"Model busy — retrying (n of N)…"*. When the budget is spent the turn ends with a
  plain-language `rate_limited` error and no partial reply is saved; just resend.
- **Needs fewer requests** for broad questions: the agent instruction's `<EVIDENCE_PLAN>`
  asks for staged, batched lookups, the raid kickoff asks for a bounded per-boss
  overview, and a per-turn **round cap** tells the model to wrap up with what it has.
- **Keeps helper calls out of it**: the greeting and follow-up suggestions fail fast and
  silently when rate-limited.

Tuning (env / `.env`; runners are cached per model, so restart the backend after a change):

| Variable | Default | Meaning |
|---|---|---|
| `WCL_MODEL_RETRY_ATTEMPTS` | `5` | attempts per model request, including the first |
| `WCL_MODEL_RETRY_INITIAL_S` | `2.0` | first retry delay (doubles each retry, plus jitter) |
| `WCL_MODEL_RETRY_MAX_S` | `30.0` | delay ceiling |
| `WCL_MODEL_RETRY_BUDGET_S` | `90.0` | total wait per model request before giving up |
| `WCL_TURN_ROUND_CAP` | `6` | lookup rounds before the wrap-up instruction |

Every turn logs one line you can grep to verify the effect, e.g.
`turn stats model=gemini-3.6-flash requests=4 rounds=3 retries=1 waited_s=4.3 outcome=answered prompt_tokens=18234 max_prompt_tokens=18234 cached_tokens=8120 trimmed=3`.

### Performance (QA sweep, 2026-10-14)

The fixes for `qa-reports/2026-10-14/performance.md` change a few behaviours worth knowing:

- **Tools run concurrently.** Every WCL tool is a coroutine (feature 013, below); the heavy
  tools fan out their independent requests.
- **One pooled WCL client** with timeouts, an in-flight request cap, identical-query dedupe
  and a byte-bounded result cache (still per tenant, FR-019).
- **No DB connection is held while the model streams**: each capture and the final save use
  short transactions.
- **`done` comes before follow-up suggestions**, so the composer unlocks as soon as the
  answer is saved; suggestions arrive as a separate frame keyed by `message_id`.
- **The KNOWN PLAYER CONTEXT is injected per model request** and no longer stored in the
  ADK history.
- **Old tool results are trimmed from each model request**: results from turns before the
  previous one are replaced by a compact stub (status, provenance, completeness, a preview).
  The stored history keeps the full data, and the model re-fetches (from cache) if needed.
- **Follow-up suggestions run in the background** and the next message cancels them.
- **Frontend:** a token re-renders only the live message; non-chat pages, KaTeX and the
  particle engine load as separate chunks.

| Variable | Default | Meaning |
|---|---|---|
| `WCL_MAX_CONCURRENCY` | `6` | WCL requests in flight at once, process-wide |
| `WCL_CONTEXT_KEEP_TURNS` | `2` | turns (current included) whose tool results reach the model in full |
| `WCL_CONTEXT_STUB_MIN_CHARS` | `1500` | older tool results larger than this are stubbed |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` | `10` / `20` / `10` | DB connection pool (shared with the ADK session store) |
| `WCL_GUIDE_MAX_CONCURRENCY` | `2` | background guide / guild-summary generations at once |

### Welcome page and async Warcraft Logs (feature 013)

A new chat opens on **your recent raids**: up to 20 raids your own characters were logged
in, newest first, with zone, date, difficulty, which of your characters took part and boss
kills. Click one to start the bounded raid overview in a new chat; it also becomes a
tracked raid in the sidebar.

- Raids are **stored** per workspace. Opening the page shows them at once and, at most every
  15 minutes (or when your own characters change), refreshes in the background: each
  character's recent reports are listed (from the shared cache when fresh, feature 014),
  then details are fetched only for new or still-live raids. A raid whose log ended over 2 h ago is final and never
  fetched again.
- The refresh claim is a database row, so only one instance refreshes a workspace at a
  time, and a refresh that never finishes is reclaimed after 5 minutes. **Retry** appears
  when a refresh fails.

The side mission (QA PERF-201/211): **WCL access is native async** (httpx). Tools are
coroutines with no worker threads, so an abandoned turn's lookups stop at once, and
background work (guides, the patch lookup, recent raids) runs in a **background lane**
capped at 2 of the 6 WCL slots, so it never queues chat lookups. Each query is bounded at
75 s including the wait for a slot. The cache stores raw response bytes (no deep copies),
and the backend freezes its startup heap out of the GC so large payloads don't stall
streaming.

| Variable | Default | Meaning |
|---|---|---|
| `WCL_BACKGROUND_CONCURRENCY` | `2` | WCL slots background work may hold (1 … `WCL_MAX_CONCURRENCY`-1) |
| `WCL_QUERY_TIMEOUT_S` | `75` | upper bound for one WCL query, including the wait for a slot |
| `RECENT_RAIDS_REFRESH_MIN_S` | `900` | minimum seconds between recent-raid refreshes |
| `RECENT_RAIDS_STALE_S` | `300` | when a stuck refresh may be reclaimed |

`WCL_TOOL_THREADS` is gone. On Cloud Run, see `documentation/deployment.md` (background
refreshes).

**Production frontend.** `docker compose` runs the Vite dev server (`target: dev`, hot
reload). For a production build, build the `prod` target, which serves the minified bundle
with nginx and proxies `/api` and `/ws` to the `backend` service (`frontend/nginx.conf`):

```bash
docker build --target prod -t wcl-frontend frontend/
```

Or set `target: prod` and `ports: ["8080:80"]` on the `frontend` service in
`docker-compose.yml`.

### Shared Warcraft Logs cache in Redis (feature 014)

Warcraft Logs data is public, so it is cached **once for everyone** in Redis instead of per
process (this replaces the old in-process cache and its per-tenant scoping). Seven key
families, each with its own freshness, reached only through `wcl_agent.cache.get_or_load`:

| Family | What | Fresh for |
|---|---|---|
| `char_id` | name/realm/region → character id ("not found" remembered 60 s) | 24 h |
| `char_overview` | a character's zone / boss rankings | 10 min |
| `char_reports` | a character's recent reports (welcome page) | 5 min |
| `report_summary` | a report's fights, kills/wipes and roster | 24 h (2 min while still being logged) |
| `report_player` | one player's table in a report | 24 h (2 min while still being logged) |
| `oauth_token` | the WCL API token | until 60 s before it expires |
| `world_zones` | zones, encounters, difficulties (patch label, encounter lookup) | 1 h |

Leaderboards, whole-raid tables, events, graphs and `run_wcl_graphql` are **not** cached.

- **Redis is optional.** Without `REDIS_URL` (or with `WCL_CACHE_ENABLED=false`) every
  lookup goes to Warcraft Logs; if Redis goes down mid-run, lookups fall back to Warcraft
  Logs within 250 ms and stop trying Redis for 5 s.
- Ten simultaneous misses on one entry make **one** Warcraft Logs request (a short lock).
- "Check again" / "refresh" makes the agent bypass the cache for that character — at most
  once a minute per user and character.
- Every real request logs its API cost: `wcl_cost op=… points_this_hour=… delta=…`.
  Rate-limit (429) and server errors are retried twice with backoff.
- **Stats** (platform admins): `GET /api/admin/cache-stats?days=7` — per-family hits, misses,
  hit rate, average load time and an `ok` / `review` status, plus Redis memory and evictions.

`docker compose up` starts Redis (`redis:8-alpine`, 256 MB, LRU eviction, no persistence)
and points the backend at it. Settings (all optional, defaults in `.env.example`):
`REDIS_URL`, `WCL_CACHE_ENABLED`, `WCL_CACHE_TTL_<FAMILY>`, `WCL_CACHE_UNFINISHED_TTL`,
`WCL_CACHE_JITTER`, `WCL_CACHE_LOCK_MS`, `WCL_CACHE_LOCK_WAIT_MS`, `WCL_NEG_CACHE_TTL`,
`WCL_METRICS_RETENTION_DAYS`. Design: [documentation/redis_cache_spec.md](documentation/redis_cache_spec.md);
spec: `specs/014-redis-wcl-cache/`.

### Grounded Raid and Mythic+ guides (feature 015)

Each spec has **two independent guides — Raid and Mythic+** — in the shared Class Guides
library. A guide's main output is the **coaching brief** the agent coaches from; the readable
guide is rendered from the same verified claims.

- **How a guide is made** (`backend/app/services/guide_pipeline/`): a briefing with the real
  date, the exact live build (Blizzard's version endpoint), the latest hotfix, raid tier and
  Mythic+ season → a Warcraft Logs **data sheet** from logs-only top rankings (casts per
  minute, shortest gaps between cooldowns, uptimes, stats, talent builds) → **research**
  from search, filtered in code (no PTR/beta/Classic, no older patch, no other spec or
  content type, nothing older than a hotfix to the spec; sources tiered, forums never
  cited) → a tool-less **author** that writes claims citing evidence ids → deterministic
  **checks** → a different, stronger **reviewer** that judges each claim only against its
  evidence, for up to 3 rounds. Passing guides publish; others are **held for review** and
  the last verified guide stays in use. Unknown patch ⇒ the run is postponed.
- **The agent** gets whole briefs (never cut, never drafts) for the content type a message
  is about — inline in the turn context (12 000-character budget) or via the
  `get_coaching_brief` tool; `get_cooldown_usage` uses the brief of the report's content
  type. Its clock (`<CURRENT_TIME>`) is live.
- **Roster** comes from Warcraft Logs game data (Devourer included), with a static fallback.
- **Freshness**: a new patch, Mythic+ season or a hotfix to the class marks guides stale; ones
  in use (opened, a saved character's spec, or given to the agent in the last 14 days)
  regenerate at once, others when next opened. Users can **report an inaccuracy**; the next
  update judges it (admins: `GET /api/admin/guide-reports?status=open`).
- **Accuracy check** (maintainer-run, live models + WCL):
  `uv run python -m backend.evals.guides run [--baseline] [--live-generate] [--specs Mage/Fire] [--content raid,mplus] [--skip-coaching]`
  scores patch accuracy, claim support, source leakage, facts, adversarial cases and coaching
  against `backend/evals/guides/reports/baseline.json`; exit code 0 = release gate passed.
  `uv run python -m backend.evals.guides datasheet Mage/Fire raid` prints one data sheet.
- Settings (optional, see `.env.example`): `WCL_GUIDE_REVIEW_MODEL`,
  `WCL_GUIDE_MAX_REVIEW_ROUNDS`, `WCL_GUIDE_BRIEF_MAX_CHARS`,
  `WCL_GUIDE_PREAMBLE_BRIEFS_MAX_CHARS`, `WCL_GUIDE_DATASHEET_MIN_SAMPLE`,
  `WCL_GUIDE_INUSE_DAYS`, `WCL_GUIDE_REPORT_PER_MINUTE`, `WCL_GUIDE_RESEARCH_FETCH_ENABLED`
  (off until the maintainer has reviewed the guide sites' terms), `WCL_GUIDE_TALENT_NAMES_URL`,
  `WOW_VERSION_URL`, `WOW_NEWS_URL`. Migration `0011_guide_content_types` keeps existing
  guides as Raid guides marked `legacy`. Spec: `specs/015-grounded-class-guides/`.

### Proper PDF reports (feature 017)

Both PDF downloads (whole conversation and single answer) are rendered from the findings
document as **Markdown → sanitised HTML → print CSS → PDF**, replacing the old hand-written
ReportLab converter that left `**`, `#` and tags on the page.

- **Text**: markdown-it-py (CommonMark + tables, strikethrough, task lists) renders every
  element properly, and links are clickable. Equations are typeset with matplotlib
  mathtext as SVG; anything it can't parse falls back to plain text. "$5" stays as text.
- **Safety**: raw HTML in model output is cleaned with nh3 (basic formatting kept, scripts
  and frames dropped). Remote images become their alt text. WeasyPrint may only load
  `data:` URLs, so nothing is fetched from the network or the server's disk.
- **Layout**: a title block (title, scope, UTC time, the question for a single answer, and a
  note when the answer was interrupted), a running header from page 2, "Page X of Y",
  headings kept with their content, table headers repeated after page breaks, and long
  codes and URLs wrapped inside the margins. One clean style with tavern-brown accents.
- **Charts**: a Charts section on a new page after the findings, numbered and captioned
  ("Figure 1 — …", with a source link). Charts are vector SVG; series differ by line
  style, marker or hatch, so they still read in black and white. A chart that can't be
  drawn shows "Chart unavailable" instead of failing the report.
- Each render logs `pdf rendered scope=… pages=… figures=… ms=…`. Spec:
  `specs/017-proper-pdf-generation/`.

## Quick checks

```bash
# Verify imports resolve
uv run python -c "import google.adk, httpx, pandas"

# Smoke-test the WCL API (no LLM) — prints your hourly points budget
uv run python -c "import asyncio; from dotenv import load_dotenv; load_dotenv(); \
from wcl_agent.wcl_client import acheck_rate_limit; print(asyncio.run(acheck_rate_limit()))"
```

## Notes

- Warcraft Logs v2 is a GraphQL API using OAuth2 client credentials
  (`https://www.warcraftlogs.com/api/v2/client`). Requests cost "points"; the
  agent can call a `check_rate_limit` tool to see the remaining budget.
- Class/spec filters use PascalCase, space-free names (e.g. `Hunter` /
  `Marksmanship`) — handled for you in `wcl_agent/constants.py`.
- The agent uses `gemini-3.6-flash` by default; change it with `WCL_DEFAULT_MODEL`
  (shared by the backend config and the `wcl_agent` CLI, so they can't drift). The
  web app's selectable list is discovered at startup (see
  [Model discovery](#model-discovery-feature-016)). ADK drives Claude on Vertex
  natively (registered in `wcl_agent/agent.py`).
- Planned work lives on the Shortcut "Team 1" board and is kept in sync with `todo.md`
  (constitution Principle VIII). Run `/shortcut-sync` in Claude Code to reconcile them;
  add `dry-run` to preview the changes.

## Model discovery (feature 016)

The chat model dropdown is built at startup from Vertex's Model Garden catalog, so a new
model release needs no `.env` edit:

1. Both publisher catalogs (Google, Anthropic) are listed from the global endpoint.
2. Each entry is sorted into a class: Gemini `pro`, `flash`, `flash-lite`; Claude
   `haiku`, `sonnet`, `opus`. TTS, image, live, embedding and experimental models are
   dropped. Newer versions come first; a preview outranks an older GA model (so
   `gemini-3.1-pro-preview` beats `gemini-2.5-pro`), and GA wins a version tie.
3. The newest few versions of every class get a one-token call with a tool declaration,
   all at once. Per class the newest that answer are kept: `WCL_GEMINI_CLASSES`
   (default `pro:2,flash:2,flash-lite:2`) and `WCL_ANTHROPIC_CLASSES` (default
   `haiku:1,sonnet:1,opus:1`), served in that order. A 404 moves on to an older
   version; a 429 that persists after one retry marks the whole class "no quota".
4. The default is `WCL_DEFAULT_MODEL` if it was kept, else the newest flash.

The startup log names every class's picks or the reason it has none, for example
`claude sonnet: no quota (429)`, and warns when `WCL_GUIDE_MODEL`,
`WCL_GUIDE_REVIEW_MODEL`, `WCL_REPORT_MODEL` or the greeting model is no longer in the
catalog (those are never changed automatically).

- **Claude quota**: Vertex enforces Claude quota per model class. No Claude model
  appears until a quota increase for that class is granted in the Cloud console
  (IAM & Admin → Quotas, "base model: anthropic-claude-…").
- **Shared result**: the result is stored in Redis for 6 h (`WCL_CACHE_TTL_MODEL_CATALOG`,
  `0` = don't store), keyed on project, model location and the class settings, so
  restarts and other workers skip the probes. A fallback or degraded result is never
  stored, and one where a probe hit a likely transient error (a timeout, a 5xx, a Gemini
  429) is kept for 10 minutes only. The default always follows the current
  `WCL_DEFAULT_MODEL`, and a stored value whose ids don't look like catalog ids is
  rediscovered. To re-discover sooner, delete the key and restart:
  `docker compose exec redis redis-cli --scan --pattern 'ext:models:*' | xargs -r docker compose exec -T redis redis-cli del`.
- **Fallbacks**: if the catalog can't be listed, the static `WCL_GEMINI_MODELS` /
  `WCL_ANTHROPIC_MODELS` are probed instead (one warning); if nothing passes,
  `WCL_MODELS` is served with the "degraded" notice. `WCL_MODEL_DISCOVERY=static` always
  uses the static lists.
- **Where models run**: every model call (chat, web search, guides, reports, greeting,
  suggestions, probes) uses `WCL_MODEL_LOCATION` (default `global`); clients are built
  only in `wcl_agent/vertex.py`. `europe-west1` serves only Gemini 2.5 and no Claude,
  and the `eu` multi-region lacks the Pro preview, so `GOOGLE_CLOUD_LOCATION` (default
  `europe-west1`) is left to everything else. `WCL_ANTHROPIC_REGION` is gone.

## Feature 010 — shared UI components (shadcn/ui)

The frontend's forms, buttons, dropdowns, dialogs, tabs, tables, badges and alerts are
built from shadcn/ui primitives generated into `frontend/src/components/ui/` (new-york
style, Tailwind v4 CSS variables, `react-icons` as the icon set, `radix-ui` as the only
added runtime dependency). Three thin app wrappers live beside them:
`ConfirmDialog` (every irreversible delete), `StatusAlert` (error/notice strips) and
`StatusBadge` (status → colour maps). The theme tokens the primitives read are defined in
`frontend/src/index.css` next to the existing Tavern Hearth palette; `styles.css` keeps
only layout and the themed chat elements.

Constitution Principle VII makes this the default for all frontend work: search the
registry through the shadcn MCP server before building a component, use a fitting item,
run the MCP audit checklist afterwards, and record any hand-built exception in the plan.

The profile page (`/profile`) is the reference layout for this: section `Card`s, friend
and spec rows as `Item`s, `Empty` states, `Skeleton` loading, `Spinner` busy buttons, a
per-row raid-role selects (one shared `CharacterList` for your characters and friends) and
one `Dialog` form for own character / friend / guild. Class
accents come from `frontend/src/lib/classColors.ts` (official WoW class colours keyed by
the normalised `CLASS_SPECS` name), the one hand-built piece, since no registry item covers it.

Adding another primitive:

```sh
cd frontend
npx shadcn@latest add <component>
# The CLI mis-resolves this project's aliases: fix `from "cn"` → `from "../../lib/utils"`,
# `from "src/components/ui/x"` → `from "./x"`, drop any `cn` npm package it installed,
# and swap lucide imports for the same-named icon in `react-icons/lu`.
```

Local edits to keep when regenerating a file: `button.tsx` variants are trimmed to
`default | secondary | ghost | destructive` and sizes `default | sm | icon`; `badge.tsx`
has extra `success` / `warning` variants; `dialog.tsx` / `alert-dialog.tsx` have their
`tw-animate-css` classes removed (no animation library) and use `secondary` where the
registry used `outline`.

Audits (from `frontend/`): no hand-styled native controls outside the allowlist in
`specs/010-shadcn-ui-adoption/contracts/ui-components.md`
(`grep -rnE '<(button|input|select|textarea)\b|confirm\(' src --include='*.tsx' --exclude-dir=ui`),
no neutral/indigo utilities (`grep -rnE 'neutral-|indigo-|red-[0-9]' src`), no `lucide-react`.
