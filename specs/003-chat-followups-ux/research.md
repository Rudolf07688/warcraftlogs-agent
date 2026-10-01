# Phase 0 Research: Chat Follow-ups & UX Enhancements

All Technical Context unknowns are resolved below. Each decision records what was
chosen, why, and the alternatives considered.

## R1. How to produce follow-up suggestions (US1)

**Decision**: Generate suggestions in a **separate, post-turn, non-streaming structured
call** (`generate_followups(model, question, answer) -> list[str]`, ≤3) after the
answer's `done`-worthy text is assembled, and emit them as a new `suggestions` frame
before `DoneFrame`. The helper reuses the turn's model (or a cheap default) with a tight
prompt and returns a parsed, de-duplicated, length-capped list; it returns `[]` when the
answer is trivial (greeting/error).

**Rationale**:
- Keeps the streamed answer byte-for-byte clean — no fragile in-band delimiter parsing
  of a live token stream, and no risk of a half-emitted JSON block reaching the user.
- Deterministic shape: we can hard-enforce "max 3", drop empties, and strip the panel
  when nothing useful comes back (FR-002, FR-004).
- Isolated and testable (`test_suggestions.py`) without running a full chat turn.
- Latency is hidden: suggestions are computed after the answer is fully streamed, so
  first-token and reading time are unaffected; the buttons simply appear a beat later.

**Alternatives considered**:
- *In-band trailing block* (agent appends a `<suggestions>` JSON after its answer):
  rejected — requires buffering/stripping the live stream and leaks partial markup on
  interruption; brittle with streaming SSE.
- *ADK structured-output / response schema on the main turn*: rejected for MVP — couples
  suggestions to the primary generation and complicates the streaming path; revisit only
  if the extra call proves too costly.

**Persistence**: MVP shows suggestions for the current/latest agent turn only (live,
association by turn — FR-005). They are **not** persisted or restored on reload (the spec
success criteria do not require it). If desired later, add a `suggestions` JSON column to
`messages` and include it in `MessageOut` — noted, not built.

## R2. Confirming/ improving parallel tool calls + shared disk (US2)

**Decision**:
1. **Confirm concurrency**: ADK already dispatches multiple `function_call`s from one
   model turn through its own executor (sync WCL tools run on ADK worker threads, per the
   `agent_runner` docstring). Add `test_parallel_tools.py` to *prove* concurrency (two
   tools whose combined wall-clock is < sum of their individual sleeps) rather than assume
   it.
2. **Shared per-turn scratch store** (`scratch.py`): a `tempfile`-based directory created
   per turn; each tool result is written there keyed by `call_id`, and the full payload is
   read back by correlation id when the call completes. This is the "shared disk space …
   the agent can pick up when done" from the brief: large outputs (full report tables,
   graph JSON) are preserved intact (FR-008) and handed off to the WS capture services and
   the agent without being bound by any in-transit frame size.
3. **Partial-failure handling** (FR-009): a single failed tool must surface as a normal
   error-shaped tool result the model can see and report, and must not raise out of the
   turn. The existing `_handle_turn` already wraps the stream in try/except and persists a
   partial message; extend tests to assert that one failing concurrent tool leaves the
   others' results usable and names the failure.

**Rationale**: Minimal change that satisfies the stated requirement — reuses the existing
`pending_args` correlation and the WS capture services; the scratch dir is one small module
and is torn down per turn (no persistence, no new service). Keeps blocking I/O off the event
loop (tools already run on worker threads).

**Alternatives considered**:
- *In-memory only*: current behavior; rejected because it does not address the explicit
  "shared disk" request and risks context bloat for large payloads.
- *ADK ArtifactService*: heavier and ADK-version-coupled; a plain per-turn temp dir is
  simpler (YAGNI) and fully under our control. Revisit if cross-turn artifacts are needed.
- *Rewrite WCL client to native async httpx*: already flagged as a "later improvement" in
  the codebase; out of scope here — concurrency via worker threads is sufficient for the
  low concurrency this app sees.

## R3. Fixing fixed-looking response panels (US3)

**Decision**: Replace the fixed `max-width: 820px` / agent `max-width: 860px` on
`.message` with a **responsive width** (e.g. `max-width: min(860px, 100%)` within the
flex `.message-list`, or a `clamp()`), and verify the `.message-list` (`flex: 1;
overflow-y: auto`) continues to own vertical scrolling so long answers expand and scroll
rather than clipping. No height is pinned on message panels.

**Rationale**: The "fixed size" perception comes from the absolute pixel `max-width` caps
— on wide windows or after the side panel is narrowed, answers don't use the available
width. A relative cap fixes it with a pure-CSS change (lowest risk), and composes with the
resizable side panel (R6) because the chat column is already `1fr; min-width: 0`.

**Alternatives considered**: JS-measured heights/virtualization — rejected as unnecessary
complexity for the message volumes here (YAGNI).

## R4. Barnaby persona (US4)

**Decision**: Edit the single-source `Personality` block in `wcl_agent/agent.py` to name
the assistant **"Barnaby"**, a tavern/innkeeper and guild MC, who is warm and funny but
blunt — explicitly calling out mistakes in good humor — while the existing
"base every answer only on tool data" rules remain unchanged (FR-015).

**Rationale**: One authoritative prompt string drives every model variant (DRY). No code
or tool changes. Run `gitnexus_impact` on the prompt/`build_agent` path before editing per
constitution VI.

**Alternatives considered**: per-model persona overrides — rejected (needless divergence,
violates single-source).

## R5. Resizable side panel (US5)

**Decision**: Convert the `.app` grid's fixed `260px` column to a CSS variable
`--sidebar-width` (default 260px). Add a thin drag handle between the sidebar and main;
on drag, update `--sidebar-width` within a `min`/`max` clamp (e.g. 200–480px) and persist
the chosen width to `localStorage`, restoring it on load.

**Rationale**: Frontend-only, no backend/API change; `localStorage` matches the app's
single-user local nature and needs no schema. The clamp prevents the panel from hiding the
chat or its own handle (edge cases).

**Alternatives considered**: server-side preference store — rejected (no multi-device need;
adds API + DB surface for a cosmetic setting, YAGNI).

## R6. Togglable background image (US6)

**Decision**:
- **Source asset**: move/copy `morgan-howell-img-1760.jpg` from `frontend/dist/assets/`
  (build output) into a **source** location (`frontend/public/` or `src/assets/`) so Vite
  includes it deterministically in future builds; keep the previous background available
  too.
- **Config-driven default** (`frontend/src/config.ts`): a background registry with the new
  image as the default; the body background is set from the selected option and layered
  with a dark scrim/overlay so chat text stays legible over either image. A user-facing
  toggle (`BackgroundToggle`) persisting to `localStorage` is included as the ergonomic
  surface over the same config (minimum requirement = configurable default + retained
  fallback).
- **Graceful fallback**: if the image fails to load, fall back to the existing solid
  `--bg` color.

**Rationale**: Satisfies "use the new background but keep it in and make it togglable from
config" with the smallest footprint. Putting the asset in source fixes the latent problem
that it currently only exists in `dist/` (which a rebuild would overwrite).

**Alternatives considered**: hard-coding the new image only — rejected (brief requires the
old one retained + togglable).

## Cross-cutting notes

- **Contract additions** are additive and backward-compatible: a new `suggestions` frame;
  existing clients ignore unknown frames. No breaking changes to REST or existing frames.
- **Testing reality**: backend slices (US1, US2) get pytest coverage; frontend slices
  (US3, US5, US6) and persona voice (US4) are verified via the quickstart manual steps,
  since there is no frontend test harness (noted, not introduced — YAGNI).
