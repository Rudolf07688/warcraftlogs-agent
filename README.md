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
   # (GOOGLE_CLOUD_LOCATION defaults to the global endpoint)
   ```
4. **Install deps with uv** (Python >= 3.10):
   ```bash
   uv sync
   ```

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
  if Vertex is unreachable. Configure candidates with `WCL_GEMINI_MODELS` /
  `WCL_ANTHROPIC_MODELS` (see `.env.example`).
- **PDF export** — download any conversation as a PDF with the written analysis
  plus the graphs the agent fetched (rendered with matplotlib + reportlab).

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
`turn stats model=gemini-3.6-flash requests=4 rounds=3 retries=1 waited_s=4.3 outcome=answered`.

## Quick checks

```bash
# Verify imports resolve
uv run python -c "import google.adk, requests, pandas"

# Smoke-test the WCL API (no LLM) — prints your hourly points budget
uv run python -c "from dotenv import load_dotenv; load_dotenv(); \
from wcl_agent.wcl_client import check_rate_limit; print(check_rate_limit())"
```

## Notes

- Warcraft Logs v2 is a GraphQL API using OAuth2 client credentials
  (`https://www.warcraftlogs.com/api/v2/client`). Requests cost "points"; the
  agent can call a `check_rate_limit` tool to see the remaining budget.
- Class/spec filters use PascalCase, space-free names (e.g. `Hunter` /
  `Marksmanship`) — handled for you in `wcl_agent/constants.py`.
- The agent uses `gemini-3.6-flash` by default; change it with `WCL_DEFAULT_MODEL`
  (shared by the backend config and the `wcl_agent` CLI, so they can't drift). The
  web app's selectable list comes from `WCL_GEMINI_MODELS` / `WCL_ANTHROPIC_MODELS`
  probed at startup. ADK drives Claude on Vertex natively (registered in
  `wcl_agent/agent.py`).

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
