# Brief 032 — Provider switch and Anthropic API client for the chat agent

- **Feature:** 032 · **Branch:** `032-llm-provider-switch` (set `GIT_BRANCH_NAME=032-llm-provider-switch` for `/speckit-specify`; spec dir `specs/032-llm-provider-switch/`)
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (track A), detached at the base. Deps synced.
- **Base ref:** `sprint-2026-10-31` @ `b963463`
- **Story:** sc-249 (5) LLM provider switch (`WCL_LLM_PROVIDER`) and Anthropic API client for the chat agent. Epic 248. Move it to **In Progress** when you start.
- **Peer:** track B developer `dev-b-034` (epic-203 QA fixes; no file overlap with you).
- **Sprint files:** plan `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/plan.md` (section 032, the overlap table, the sprint-level e2e checks), decisions `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/decisions.md` (D1–D5 binding; D1–D3 pending the owner's review), ownership `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/ownership.md`.
- **Load the `claude-api` skill** for Anthropic SDK facts and current Claude model ids.

## OWNER GATE (binding)

You may run `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` and write `checkpoint.md`.
**No `/speckit-implement` and no code** until the scrum master relays the owner's thumbs-up
("OWNER GO"). If the owner changes D1–D3 you'll get updated ACs before implementing.

## Acceptance criteria (verbatim from plan.md)

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

## Contract you must publish early (blocks 033 and 035)

At the end of `/speckit-plan`, send the scrum master a **provider-layer contract** (it goes
verbatim to the 035 developer, who specifies against it while you build):
module path; public function names + signatures (active provider, client factory, id-shape
check/normalisation, role → model resolution); the model-role names; per-provider default
ids per role; how a non-agent call site gets a client (035 will write the provider-neutral
text-generation entry point on top of yours; **don't build that entry point yourself**, it
belongs to 035). Mark anything still uncertain.

## Footprint (tentative; becomes the grant after /speckit-plan)

`wcl_agent/llm/vertex.py`, a new provider module under `wcl_agent/llm/`,
`wcl_agent/llm/model_retry.py` (`RetryingClaude._anthropic_client`, `is_anthropic_model`),
`wcl_agent/agent.py` (model factory), `backend/app/config.py` (provider, key, role defaults),
`backend/app/main.py` (startup provider/key check only — 033 owns `_load_models` later),
`backend/app/model_state.py` / the WS model resolution (stale chat model), `.env.example`,
`README.md` (provider section), `docker-compose.yml` (only if the ADC mount must become
optional), tests, `specs/032-llm-provider-switch/**`.

**Not yours:** `wcl_agent/llm/models.py` (033), `suggestions.py`, `conversation_titles.py`,
`report_synthesis.py`, `guide_pipeline/*` (035), `schemas.py`, `App.tsx`, proposal files (034).
Discovery against the Anthropic Models API and the 429 → sibling path for API ids are **033's**
(sc-250); keep 032 to the switch, the client and the roles.

## Known risk to check first in your plan

ADK's `Claude` model class is built around `AnthropicVertex`. `RetryingClaude` already
overrides `_anthropic_client`; confirm a plain `AsyncAnthropic` works there (or what more is
needed) before committing to the design. Run GitNexus impact on `RetryingClaude`,
`is_anthropic_model`, the agent model factory and the config loader; report HIGH/CRITICAL.

## Working rules

- Ports for any throwaway app or DB: app **18032**, Postgres **15432**, Redis **16332**. Your own
  `docker run` containers only (never `docker compose` or the default ports).
- Never read the owner's `.env`; no live LLM/WCL calls (no `ANTHROPIC_API_KEY`, no Vertex ADC). Fakes only.
- Before impact analysis and change detection, run
  `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --force` in your worktree.
- Sub-agents: send the split (tasks → exact files → model/effort) to the scrum master first.
- No scope creep: sc-249 only. Extras go to the scrum master as Backlog suggestions.
- Reply "ACK <thing>" to each grant/decision. Never push. Restore `CLAUDE.md` and `.specify/feature.json` before each commit.
