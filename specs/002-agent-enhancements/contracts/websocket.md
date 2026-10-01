# WebSocket Contract — Agent App Enhancements (delta over 001)

Endpoint `/ws/chat` is unchanged in shape; this documents **new/enriched frames** and
behaviors for US1 (raid capture signalling), US2 (partial persistence), US3 (grounding),
and US5 (graph capture). The client→server `ChatTurn` is unchanged
(`{conversation_id?, model, content}`).

## Server → client frames

### `tool_start` *(enriched — US1/US5)*

```json
{ "type": "tool_start", "name": "get_report_graph", "report_code": "aBcD1234wXyZ" }
```

- Adds optional `report_code` when the tool is report-scoped (surfaced for UI context).
  Other args remain server-side only. Back-compatible: existing clients ignore the extra
  field.

### `tool_end` *(enriched — US1/US5)*

```json
{ "type": "tool_end", "name": "get_report_graph", "ok": true }
```

- `ok` reflects the tool result `status` (`success` → `true`). Unchanged wire shape; the
  server additionally uses the full result internally to (a) upsert a TrackedRaid on a
  successful report retrieval and (b) capture graph JSON for PDF — these persistence
  actions are **not** separate frames.

### `grounding` *(new — US3 / FR-011)*

```json
{ "type": "grounding", "used": true }
```

- Emitted once per turn when the model used native web grounding (detected via event
  `grounding_metadata`). The UI shows a "used web search" indicator. Absent when no
  grounding occurred or the model doesn't support it (graceful — FR-012). Optional
  `sources` (list of {title,uri}) MAY be included if available.

### `raid_tracked` *(new, optional — US1)*

```json
{ "type": "raid_tracked", "report_code": "aBcD1234wXyZ", "label": "My Guild — Liberation of Undermine — 2026-09-28" }
```

- Emitted after a raid is upserted so the UI can refresh its sidebar Raids section
  without a full re-fetch. Optional; clients may instead re-call `GET /api/raids` on
  `done`.

### `token`, `meta`, `done`, `error` *(unchanged shapes)*

- `token`: `{type, text}` — streamed answer chunk.
- `meta`: `{type, conversation_id, seq}` — turn opened.
- `done`: `{type, message_id}` — reply complete and persisted.
- `error`: `{type, code, message}` — see interruption behavior below.

## Behavior changes

### Partial persistence on interruption (US2 / FR-009)

If the stream errors or the socket disconnects mid-reply, the server persists the
accumulated tokens as an `agent` message with `status="partial"` (see data-model) before
emitting `error` (code `agent_error` or `interrupted`). The partial content is never
presented as a completed `done`. On a clean finish the message is stored
`status="complete"` and `done` is sent as today.

### Investigate-raid turns (US1 / FR-004)

`POST /api/raids/{code}/investigate` creates an **empty** conversation and returns the
kickoff prompt without persisting any message. The client sends that prompt as a normal
first `ChatTurn`, and the WS handler persists it and streams the reply through the
standard path. There is no pre-persisted message, so **no double-persist guard or
seq-0 special case exists** — the investigate kickoff is just an ordinary first turn.

### Model validation *(US4)*

`turn.model` is validated against the **startup-validated** model set (app.state), not a
static config list. Unknown/invalid model → `error` frame `invalid_model`.

## Compatibility

All additions are new optional frames or new optional fields on existing frames; a 001
client continues to function (it ignores unknown frames/fields). No frame was removed or
had a field repurposed.
