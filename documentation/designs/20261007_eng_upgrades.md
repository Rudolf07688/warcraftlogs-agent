# Agent engineering upgrades after feature 009

**Date**: 2026-10-07 · **Status**: proposal · **Follows**: `20261007_prompt_upgrade.md`
(implemented as `specs/009-grounded-coaching-prompt/`)

Feature 009 made Barnaby *grounded*: an evidence contract in the instruction, a
provenance/completeness envelope on every Warcraft Logs tool result, a matched-cohort
benchmark, opportunity-based cooldown coaching, and guide freshness. What remains is
mostly **agent engineering** rather than more WoW knowledge: measuring behaviour,
enforcing the rules in code instead of prose, trimming context, and giving the agent
text knowledge it cannot currently cite.

This document lists the candidate upgrades, grouped into **spec-sized bundles of similar
complexity**, in the order they pay off. Each bundle has enough detail for an agent to run
`/speckit-specify` → `/speckit-plan` → `/speckit-tasks` on it. Small items are grouped
together on purpose; do not split a bundle unless its scope grows.

All ADK capabilities named here were verified against the installed **google-adk 2.10.0**
(`.venv/lib/python3.14/site-packages/google/adk`). The backend builds a plain `Runner` in
`backend/app/agent_runner.py`; the agent is `wcl_agent/agent.py::build_agent`.

---

## Priority order

| # | Bundle | Why first | Size |
|---|---|---|---|
| 1 | **Evaluation harness** (ADK eval) | Makes every later change measurable; was deferred in 009 (Q1 = C) | M |
| 2 | **Runtime guardrails & live instruction** (callbacks, instruction provider, session state, tracing) | Turns prompt rules into enforced behaviour; fixes the frozen timestamp | M |
| 3 | **Context & cost** (static instruction + context caching, guide section injection, model routing) | Latency/cost; needed to keep SC-011 as the prompt grows | S–M |
| 4 | **Intent-level report tools** (cast summary, death timeline, buff uptime) | Removes the last truncated-payload paths; more deterministic maths | M |
| 5 | **Knowledge base with semantic retrieval** (mechanics, patch notes, guide chunks) | Makes `SOURCE_AUTHORITY` real; only text knowledge, never log data | L |
| 6 | **Verifier pass for deep dives** (SequentialAgent critic) | Highest answer quality, highest latency; gate it | M |
| 7 | **Cross-session memory** (ADK MemoryService) | Nice-to-have; last | S–M |

"Size" is a planning hint: S ≈ one slice, M ≈ 3–5 slices, L ≈ a full feature with a
migration and new tools.

---

## Bundle 1 — Evaluation harness (ADK eval)

**Problem**: feature 009 verifies behaviour by a manual review sample
(`specs/009-grounded-coaching-prompt/review/sample.md`). The prompt is contract-tested
for *structure* only (`backend/tests/test_prompt_contract.py`). Nothing measures whether
an instruction change made answers better or worse.

**What ADK provides** (`google/adk/evaluation/`): evalsets of multi-turn cases with
expected tool trajectories and reference answers; metrics `tool_trajectory_avg_score`,
`response_match_score`, `rubric_based_final_response_quality_v1` (LLM-judged rubrics,
`eval_rubrics.py`), multi-turn tool-use/trajectory quality evaluators, and
`AgentEvaluator` for pytest integration. `adk eval` runs an evalset from the CLI.

**Scope**
- Convert the 15 review-sample questions and the 10 baseline questions
  (`review/baseline.md`) into an evalset under `backend/evals/` with the reference
  pulls from report `cFHpyKdLWAajwZCM`.
- WCL must be **faked or recorded**: capture the tool results for those pulls once
  (the client cache already deep-copies payloads) and replay them, so evals are
  deterministic and spend no points. Reuse `backend/tests/wcl_fakes.py`.
- Expected tool trajectories per case (e.g. a benchmark question must call
  `compare_player_to_cohort`, never only `get_rankings_distribution`; a cooldown question
  must call `get_cooldown_usage` before judging).
- Rubrics that encode the spec's success criteria SC-001..SC-009: numbers traceable,
  no inference as fact, abstention with a next step, cohort label present, overall +
  bracket together, no bare "missed", ≤3 fixes with evidence/change/confidence, injection
  ignored. Persona restraint as a rubric too.
- A pytest entry point (`AgentEvaluator.evaluate`) marked slow, plus a CI job that runs
  the trajectory metrics (cheap) on every change to `wcl_agent/agent.py` and the rubric
  metrics (model-judged, costs money) on demand.
- Record scores per run so prompt changes have a before/after.

**Out of scope**: live-WCL evals; evaluating the guide generator (separate rubric later).

**Dependencies**: none. **Risks**: judged rubrics drift with the judge model; pin the
judge model id in config.

---

## Bundle 2 — Runtime guardrails and a live instruction

Four small items that all touch `build_agent` / `stream_response`; plan them as one
feature with four slices.

### 2a. Citation fidelity callback (after_model)

**Problem**: `<CITATIONS>` forbids fabricated report codes / fight ids / source ids, but
only the prompt enforces it. SC-001 is checked by eye.

**Design**: register an `after_model_callback` on the agent that scans the reply for
`warcraftlogs.com/reports/<code>#fight=<id>…source=<sid>` links and compares each
identifier with the set returned by tools **in this turn** (collect them in an
`after_tool_callback` from the `provenance` envelope plus `report`/`fightID`/`id` keys in
results). Unverifiable links are rewritten to the nearest verifiable shape (drop the
source, then the fight) or removed, and the event is logged with the offending link. The
callback must be cheap (regex), never block on I/O, and never alter non-link text.
`stream_response` already streams tokens; the rewrite applies to the final aggregated
text, so decide whether to hold the last chunk or post-correct the persisted message
(the latter is simpler and matches how `partial` replies are saved).

### 2b. Analysis trace (after_tool + after_model)

**Problem**: "it feels wrong" is not debuggable (design doc, "Evaluation plan").

**Design**: an `after_tool_callback` appends `{tool, args, provenance, completeness,
ms, truncated}` to a per-turn trace in session state under the `temp:` prefix (ADK
`State.TEMP_PREFIX`, discarded after the turn); the existing `tool_end` WebSocket frame
already carries `summary`/`ms`, so the trace is the persisted, structured version. Store
it beside the message (a JSON column or the existing `artifacts` pattern) and expose it on
the message-report endpoint for debugging. ADK's `DebugLoggingPlugin` /
`auto_tracing_plugin` (`google/adk/plugins/`) can supply the raw events during
development; the feature stores only the compact trace.

### 2c. Live instruction provider

**Problem**: `INSTRUCTION` is an f-string evaluated at import, so `<CURRENT_TIME>` is
frozen at process start, and nothing injects the current patch or the WCL budget.

**Design**: ADK accepts `instruction: Union[str, InstructionProvider]`, a callable
receiving a `ReadonlyContext`. Keep the static contract text as a module constant (so
`test_prompt_contract.py` keeps asserting it) and add a provider that appends a small
dynamic block: current time, `current_patch()` (cached by the WCL client), remaining WCL
points, and the session's resolved context (2d). Mind `static_instruction`: when it is
set, `instruction` moves from the system prompt into user content (see the docstring in
`llm_agent.py`) — this interacts with Bundle 3 caching, so design 2c and 3a together.

### 2d. Resolved context in session state

**Problem**: the model re-resolves the player, server, source id and fight on every turn,
spending calls and occasionally drifting.

**Design**: the tools that resolve a player (`fight_time.resolve_player` callers) write
`{report_code, fight_id, source_id, name, server, class, spec}` to `tool_context.state`
(session scope, not `temp:`), the provider in 2c surfaces it as "RESOLVED CONTEXT", and
`<CONTEXT_RESOLUTION>` tells the model to reuse it unless the user changes subject.
`get_selected_encounter` already uses state the same way. Clear it when the user names a
different report or player.

**Dependencies**: Bundle 1 should exist first so 2a/2c can be measured. **Risks**: the
callback must not strip legitimate links from web-search answers (non-WCL domains are
untouched by design).

---

## Bundle 3 — Context and cost

Three small items; one feature, three slices. Measure with SC-011 timings from
`review/baseline.md`.

### 3a. Static instruction + context caching

ADK 2.10 supports `App(context_cache_config=ContextCacheConfig(...))` and
`LlmAgent.static_instruction`; caching starts on the second turn once the cacheable prefix
exceeds the model minimum (2048 tokens). The instruction plus injected guides already
exceeds that. Work: build the runner through `App` (today `agent_runner.py` constructs a
bare `Runner`), move the contract text to `static_instruction`, keep the dynamic block in
`instruction` (2c), and confirm the Anthropic path (`anthropic_llm.py` also references the
cache config) degrades gracefully.

### 3b. Guide section injection

**Problem**: `build_preamble` injects each guide whole, trimmed to a per-guide and total
cap, so the model often sees the first few thousand characters and not the cooldown or
boss-specific sections.

**Design**: split stored guides by markdown heading at generation time (store a
`sections` JSON next to `guide_markdown`, or derive at read time and cache), inject the
heading list plus the sections relevant to the question's intent (rotation for parse
questions, cooldowns for cooldown questions, boss section when an encounter is resolved),
and keep the provenance label. This is the non-semantic precursor of Bundle 5c; if Bundle 5
is built, 3b's section split becomes its chunking.

### 3c. Model routing

ADK sub-agents can run different models. Use a cheaper model for retrieval-heavy
sub-tasks (e.g. the web_search sub-agent already runs on the parent model) and the strong
model for synthesis. Keep a single `build_agent` factory; add a `WCL_RETRIEVAL_MODEL`
setting with the same discovery/validation as the existing model list. Only worth doing
after 3a, when the cost split is visible.

---

## Bundle 4 — Intent-level report tools

**Problem**: `get_report_table` returns raw WCL tables capped at 60 KB; an unfiltered
`Casts` or `DamageDone` table is ~160 KB, so the model sees a truncated preview and
`completeness.truncated = true`. The 009 tools reduce payloads in code for their own use
(`benchmark.reduce_casts_entry`, `fight_time.fetch_dead_windows`) but the model still
reaches for the raw table for everything else.

**Design**: three new sync tools in `wcl_agent/`, each built from the existing
`_report_field`, the shared `fight_time` helpers and the provenance envelope, each
reducing in code and never returning raw tables:

- `get_player_cast_summary(report_code, fight_id, player_name, source_id=0)` — per-ability
  casts and casts per minute over **eligible time**, plus the player's top-N abilities;
  reuse `reduce_casts_entry`.
- `get_death_timeline(report_code, fight_id, player_name="", source_id=0, window_s=10)`
  — for each death: timestamp, killing blow, damage taken and healing received in the
  preceding window (events, paginated in code), defensives active, battle-res context.
  This is what `<ANALYSIS_ROUTING>`'s wipe/death path needs and today assembles by hand.
- `get_buff_uptime_summary(report_code, fight_id, player_name, source_id=0)` — uptime % of
  the player's buffs/debuffs over eligible time, with the raid-wide ones separated.

Register them in `TOOLS`, describe them in `<TOOLS>`, add `tool_summary` branches and
frontend labels/spell entries (the 009 pattern), and extend the evalset (Bundle 1) with
trajectory expectations. Keep `get_report_table` as the general fallback.

**Dependencies**: none hard; Bundle 1 to measure. **Size**: M.

---

## Bundle 5 — Knowledge base with semantic retrieval

**Verdict on "would a semantic search DB help?"**: yes for **text knowledge**, no for log
data. Combat logs are numeric and structured; the deterministic tools must stay. The gap
is the knowledge the evidence contract demands but the app cannot cite reliably:

- `<ANALYSIS_ROUTING>` allows "avoidable" only with a current mechanic source. Web search
  is absent on Claude models and non-deterministic on Gemini.
- `<SOURCE_AUTHORITY>` ranks patch notes as authoritative for game changes, but nothing
  stores them.
- Guides are injected whole (3b) rather than retrieved by relevance.

**Design**
- **Store**: pgvector in the existing Postgres (constitution: no new services). New table
  `knowledge_chunks {id, kind (encounter|patch_notes|guide), subject (encounter_id or
  class/spec), game_patch, source_title, source_uri, retrieved_at, chunk_index, text,
  embedding}`. Migration adds the extension and table. Embeddings via Vertex text
  embeddings through the existing Google credentials; one embedding model id in config.
- **Ingestion**: reuse the guide pipeline. Encounter guides are generated like spec guides
  (same `_generate_text`, same provenance block with `patch` and sources, same
  `pending/ready/failed` lifecycle) for every encounter in the current raid zones from
  `MENU_DISCOVERY`; patch notes are fetched from their official pages when web search is
  available and otherwise pasted by an admin. Chunk by heading; store sources from the
  grounding records exactly as 009 does.
- **Tool**: one sync tool `search_knowledge(query, kind="", subject="", limit=5)` returning
  chunks with `{text, kind, subject, game_patch, freshness, source_title, source_uri,
  retrieved_at}` under the provenance envelope, so `<CITATIONS>` can cite them with name,
  date and link. Freshness reuses `guide_freshness`.
- **Prompt**: `<SOURCE_AUTHORITY>` names the tool; `<ANALYSIS_ROUTING>` requires it before
  labelling damage avoidable; `<GUIDES>` prefers retrieved sections over the injected
  blob once 3b/5 exist.
- **UI**: an admin page listing chunks by kind with patch, date and source (mirrors the
  Class Guides page), with regenerate.

**Alternatives**: ADK ships `VertexAiSearchTool`, `VertexAiRagRetrieval` and
`VertexAiRagMemoryService` for managed retrieval; they add infrastructure and a second
store of truth, so prefer pgvector unless the corpus outgrows Postgres.

**Dependencies**: 009 guide provenance (done); Bundle 1 to measure "avoidable" calibration
before/after. **Size**: L (migration, ingestion, tool, prompt, admin UI).

---

## Bundle 6 — Verifier pass for deep dives

**Problem**: a single model pass both gathers evidence and writes the answer; the evidence
contract is applied by the same model that may have mis-stated a number.

**Design**: ADK `SequentialAgent` with the existing analyst agent followed by a **critic**
agent (no tools, `include_contents` set so it sees the analyst's tool results and draft)
whose instruction is: for every number, identifier and causal claim in the draft, find the
supporting tool result; list unsupported claims; return a corrected draft with the
`<OUTPUT>` structure intact. The critic's output replaces the draft. Run it **only** when
the user asks for a deep dive or when the trace (2b) shows more than N tool calls, because
it roughly doubles latency. The web_search sub-agent and persona stay with the analyst; the
critic must not add banter.

**Alternative** (cheaper): extend the 2a callback with deterministic number checks
(every number in the reply appears in some tool result this turn). Numbers are often
derived (per minute, percentages), so expect false positives; keep it as a warning, not a
rewrite.

**Dependencies**: Bundle 1 (to prove it helps), 2b (trace). **Size**: M.

---

## Bundle 7 — Cross-session memory

**Problem**: Barnaby cannot say "last week we flagged your Combustion timing" — each
conversation starts cold except for the profile preamble.

**What ADK provides**: `BaseMemoryService` with `InMemoryMemoryService`,
`VertexAiMemoryBankService` and `VertexAiRagMemoryService`; the `load_memory` tool (model
calls it with a query) and `preload_memory` (injects relevant memories every turn).
Sessions are already durable (`DatabaseSessionService`).

**Design**: a Postgres-backed `BaseMemoryService` implementation (reuse the pgvector
table from Bundle 5 with `kind=memory`, tenant-scoped under RLS like conversations) that
stores per-conversation summaries: the resolved context, the verdict and the ≤3 fixes
from each analytical answer. Expose `load_memory` to the agent and mention it in
`<CONTEXT_RESOLUTION>` for "last time / previously" questions. Memories are evidence with
a date, never instructions, and must cite the conversation they came from.

**Dependencies**: Bundle 5's store (or a minimal table without embeddings if built
alone); tenancy rules from feature 006. **Size**: S–M.

---

## Not recommended now

- **Code executor** (`BuiltInCodeExecutor`): letting the model compute statistics from
  raw events conflicts with "deterministic calculations happen in code"; the reducers in
  Bundle 4 cover the need.
- **Tool confirmation** (`require_confirmation` on `FunctionTool`): the only costly tools
  are budget-bounded already; a confirmation prompt would slow every benchmark.
- **LoopAgent self-refinement**: the verifier (Bundle 6) gives one bounded critic pass;
  open-ended loops raise cost without a measurable target until Bundle 1 exists.

## How to pick these up

1. Run `/speckit-specify` on one bundle at a time; the bundle text above is the feature
   description. Bundles 2 and 3 are single features with slices, not one feature per item.
2. Every bundle should add cases to the Bundle 1 evalset as part of its tasks, so the
   harness grows with the agent.
3. Keep the 009 conventions: additive tool result shapes, provenance envelope on every
   tool, `tool_summary` + frontend label/spell entries per new tool, prompt-contract test
   extended for any new section clause, GitNexus impact before edits and `detect_changes`
   before commits.
