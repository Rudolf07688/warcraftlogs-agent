# Phase 0 Research: Agent App Enhancements

All product-level ambiguities were resolved in the spec's Clarifications. This file
records the **technical** decisions needed to implement them against the existing
`001` codebase. No open `NEEDS CLARIFICATION` remain.

## 1. Detecting a "successful report retrieval" for raid tracking (US1 / FR-001)

**Decision**: Detect raids inside the ADK event stream in `agent_runner.stream_response`.
For every `function_response` part, read the tool `name`, the originating
`function_call.args` (to get `report_code`), and the result payload's `status`. When a
**report-scoped tool** (`get_report_fights`, `get_report_table`, `get_report_events`,
`get_report_graph`, `get_report_rankings`, `get_report_player_details`,
`get_report_master_data`) returns `status == "success"` for a `report_code`, emit a
structured signal the WS handler persists via `services/raids.upsert_tracked_raid`.

**Rationale**: Report codes only enter the system through these tools' `report_code`
argument, and each tool already returns a `{"status": ...}` dict (see
`report_tools.py`). Keying off a *successful* response guarantees the log is real and
accessible (the clarified requirement) and avoids entries from typos/hypotheticals.

**Label resolution**: add `get_report_metadata(report_code)` to `report_tools.py`
(one GraphQL call: `reportData.report { title, zone { name }, guild { name },
startTime }`). Resolve the label (e.g. `"<guild> — <zone> — <date>"`) lazily on first
capture, run via `asyncio.to_thread`. If metadata can't be resolved, fall back to the
report code (FR edge case). Reuses the existing `WCLClient`/`get_client` (DRY).

**Alternatives considered**: (a) Parsing report codes out of raw user text — rejected,
captures inaccessible/typo logs (contradicts clarification). (b) A dedicated "track
this raid" tool the model must call — rejected, relies on model discipline and adds a
tool; passive detection is simpler and reliable.

## 2. Richer tool framing in the agent runner (DRY backbone)

**Decision**: Extend `stream_response` to yield tool frames carrying `args` (at
`tool_start`) and `status`/`ok` (at `tool_end`), plus the raw result for internal
consumers. The WS layer forwards the user-safe subset (name + ok) and routes the full
record to the raid + graph capture services.

**Rationale**: US1 (report_code + status) and US5 (graph JSON) both need tool
call/result detail. Capturing it once in the runner is the single source of truth
(Principle I) and keeps `ws.py` thin.

**Alternatives considered**: Separate post-hoc re-parse of messages — rejected, the
tool results aren't in the persisted transcript and re-running tools wastes the WCL
rate budget.

## 3. Durable agent sessions & context restore (US2 / FR-006–008)

**Decision**: Replace `InMemorySessionService` with ADK's **`DatabaseSessionService`**,
pointed at the same PostgreSQL instance via a **sync** SQLAlchemy URL
(`postgresql+psycopg://…` derived from the existing `DATABASE_URL`). Session id stays
the conversation UUID string (already the case). All ADK session calls
(`get_session`/`create_session`/`run_async` internals) are invoked from async code;
the service's sync I/O is acceptable for a single-user app and the heavy startup
`create_all` runs once. Where we call blocking session methods directly, wrap in
`asyncio.to_thread`.

**Rationale**: This literally satisfies todo item 2 ("SessionId … saved to the db")
and restores true model context (tool history + turns), not just the transcript, after
a restart. It is ADK's built-in, DRY persistence — no bespoke replay logic.

**Partial-output persistence (FR-009)**: in `ws.py`, on exception or disconnect
mid-stream, persist the accumulated tokens as an `agent` message flagged partial
(new `status` column on `messages`, default `"complete"`, set `"partial"` here) and
send an `error`/`done` frame indicating interruption. No silent loss.

**Alternatives considered**: (a) Keep in-memory + re-seed from `messages` on reopen —
simpler deps but loses tool/grounding context and duplicates ADK behavior; documented
and rejected in plan Complexity Tracking. (b) ADK `VertexAiSessionService` — ties
sessions to a managed Vertex Agent Engine resource, heavier than needed locally.

## 4. Web access via native grounding (US3 / FR-010–012)

**Decision**: Enable Gemini **native Google Search grounding** on Vertex through ADK's
built-in `google_search` tool, added to the agent **only for Gemini models that
support it**. `build_agent(model)` selects the toolset: Gemini → WCL tools *plus*
grounding; Anthropic (and any non-grounding model) → WCL tools only. Grounding usage is
detected via `grounding_metadata` on streamed events and surfaced to the UI as a
`grounding` frame / indicator (FR-011). On no grounding support or empty results, the
agent proceeds normally (FR-012).

**Key constraint to honor**: some Gemini generations disallow combining the built-in
`google_search` tool with many custom function tools in a single agent. **Mitigation**:
if the running Gemini model rejects the combined toolset, fall back to exposing
grounding via a **search sub-agent tool** (an `AgentTool` wrapping a grounding-only
Gemini agent) — this matches the todo's literal "web-search *subagent* as a tool"
phrasing and keeps the 16 WCL function tools intact. Pick the combined path if the
target Gemini model supports it; otherwise the sub-agent path. Decided during the US3
slice against the actual default model.

**Rationale**: Matches the clarified choice (model-native grounding), provider-aware so
Anthropic models simply run without web access, and the sub-agent fallback both
resolves the tool-combination limitation and honors the original wording.

**Alternatives considered**: Dedicated external search API (Tavily/Bing) — rejected by
clarification (native grounding chosen) and would add a credential.

## 5. Dynamic, validated model discovery (US4 / FR-013–016)

**Decision**: At **backend startup** (per clarification), `wcl_agent/models.py`:
1. Builds a **candidate set** = configured Gemini ids + configured Anthropic-on-Vertex
   ids (env: `WCL_GEMINI_MODELS`, `WCL_ANTHROPIC_MODELS`), optionally augmented by a
   Vertex publisher-model listing when available.
2. **Validates** each candidate with a minimal probe: a one-token "hello" generation
   (health-check API used if the provider exposes one; otherwise the probe). Gemini via
   the genai/Vertex client; Anthropic via the Vertex Anthropic client.
3. Keeps only responsive models; stores the validated list + default in
   `app.state` during lifespan. `GET /api/models` serves from there (no per-request
   probing). `ws.py` and `conversations.py` validate requested models against this set.
   The `app.state` **`default` is the single runtime source of truth** for the default
   model: it is `WCL_DEFAULT_MODEL` if that passed validation, else the first validated
   model. To remove the pre-existing drift between `backend/app/config.py`
   (`gemini-3.6-flash`) and `wcl_agent/agent.py` (`DEFAULT_MODEL = "gemini-3.6-flash"`),
   `build_agent`'s own default is only a last-resort fallback; the backend always passes
   an explicit, validated model from `app.state`. Align the config default and
   `agent.DEFAULT_MODEL` to the same id so the fallback agrees with the runtime default.
4. **Fallback (FR-016)**: if discovery/validation can't run (Vertex unreachable), serve
   a documented default set from config and include a `degraded: true` flag so the UI
   can inform the user; never return an empty list.

**Anthropic-on-Vertex in ADK**: ADK runs Claude on Vertex via its model registry
(`google-adk[anthropic]`, using `anthropic[vertex]`). `build_agent` maps an Anthropic
model id to the registered Claude model class; Gemini ids pass through as strings.
Single factory, one branch (DRY).

**Rationale**: A true "list every Vertex model" crawl is brittle (Anthropic models are
publisher/Model-Garden entries without a clean enumerate-and-use API). Candidate-list +
responsiveness probe is simple, honors the "try a hello and see if it responds"
instruction exactly, and is run once so there's no request-path cost (YAGNI, startup-only
per clarification).

**Alternatives considered**: On-demand probing per selector open (rejected by
clarification — adds latency); background TTL refresh (rejected — more complexity than a
single-user app needs).

## 6. PDF export with graphs (US5 / FR-017–020)

**Decision**: Capture graph data during the conversation, render it at download time.
- **Capture**: when `get_report_graph` returns success, `services/graphs.py` stores the
  returned `graph` JSON (plus data_type/report_code/fight/source) in a new
  `captured_graphs` table linked to the conversation (fed by the richer tool framing,
  §2). This realizes "the graphs it retrieved during that conversation."
- **Render**: `GET /api/conversations/{id}/report.pdf` builds the PDF in a worker thread
  (`asyncio.to_thread`): a header (raid label + generation date), the agent's written
  analysis (agent messages → `markdown` → PDF flowables via **reportlab**), and each
  captured graph rendered to a PNG with **matplotlib** and embedded. No captured graphs
  → analysis-only PDF (edge case). Returns `application/pdf` as a streaming download;
  on failure returns a clear error (FR-020).

**Why render from captured JSON, not re-call tools**: WCL's `get_report_graph` returns
time-series **JSON**, not an image. Re-calling at export time would spend rate budget
and might miss the exact filters used. Capturing the JSON the agent already fetched is
faithful and cheap.

**Library choice**: `reportlab` (pure-Python PDF, no system libs) + `matplotlib`
(charts; `pandas` already present) + `markdown`. Chosen over WeasyPrint/Chromium
HTML→PDF to avoid heavy container system dependencies (cairo/pango/headless browser).

**Alternatives considered**: (a) Client-side PDF (jsPDF) — can't easily embed
server-held graph data or match analysis formatting; rejected. (b) Persisting rendered
PNGs during chat — wastes storage/CPU for graphs that may never be exported; render on
demand instead.

## 7. Blocking work under asyncio (Principle V)

**Decision**: Offload all blocking/CPU-bound work via `asyncio.to_thread`: ADK
`DatabaseSessionService` direct calls, startup model probes, `get_report_metadata`, and
PDF/chart rendering. This preserves the non-blocking request path mandated by the
constitution while integrating inherently sync libraries.

## 8. Dependencies & migrations

**New deps** (via `uv add`): `psycopg[binary]`, `google-adk[anthropic]` (or
`anthropic[vertex]`), `reportlab`, `matplotlib`, `markdown`. **System libs**: reportlab
+ matplotlib need no browser; matplotlib may need `libfreetype`/`libpng` in the backend
image — add to the Dockerfile if the slim base lacks them.

**Schema**: v1 uses `Base.metadata.create_all` on startup (no Alembic yet, consistent
with 001). This creates the **new tables** (`tracked_raids`, `captured_graphs`) fine, and
ADK owns its session tables. **However** `create_all` does **not** alter existing tables,
so the new `messages.status` **column on the pre-existing `messages` table will not be
added** on a database first created by 001. Handle it with a small, idempotent startup
migration run in the lifespan right after `create_all`:

```sql
ALTER TABLE messages ADD COLUMN IF NOT EXISTS status VARCHAR(10) NOT NULL DEFAULT 'complete';
```

This is safe to run every boot (Postgres `IF NOT EXISTS`) and backfills existing rows via
the default. A proper migration tool (Alembic) remains a documented later improvement; this
keeps the v1 "create on startup" convention while fixing the ALTER gap.
