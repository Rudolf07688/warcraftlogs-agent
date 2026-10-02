# WebSocket Contract — feature 005

Additive to the existing frame protocol (see 004 `contracts/websocket.md`). The transport stays the
same WebSocket; one new server→client frame is introduced. All other frames are unchanged.

## New frame: `artifact` (US2)

Emitted from `ws._handle_tool_end` when a `create_chart` tool call succeeds. Carries the ready-to-render
Plotly figure (built on the server from the agent's chart spec).

```python
class ArtifactFrame(BaseModel):
    type: Literal["artifact"] = "artifact"
    artifact_id: uuid.UUID        # persisted Artifact row id
    kind: str                     # "line" | "bar" | "scatter" | "area"
    title: str
    figure: dict                  # Plotly figure JSON: {"data": [...], "layout": {...}}
```

```ts
// frontend Frame union (wsClient.ts) gains:
| { type: "artifact"; artifact_id: string; kind: string; title: string; figure: { data: unknown[]; layout: Record<string, unknown> } }
```

### Ordering & timing
- Emitted **only** on a complete, successful `tool_end` for `create_chart` — never mid-stream, so no
  partial/broken chart can render (FR-009).
- `message_seq` is **not** on the frame (the agent message doesn't exist yet). The client accumulates
  artifacts for the in-flight turn (exactly like `encounters`) and attaches them to the agent message
  on `done`. Persisted `message_seq` is assigned server-side at turn end and surfaced on reload via
  `GET /api/conversations/{id}` (`ArtifactOut.message_seq`).

### Client handling (App.tsx)
- `case "artifact"`: push `{artifact_id, kind, title, figure}` into `pendingArtifactsRef`.
- `case "done"`: attach `pendingArtifactsRef.current` to the new agent message (`Message.artifacts`),
  then clear it (mirrors the `encounters` flow).
- `case "error"`: clear `pendingArtifactsRef`.

## Unchanged frames
`meta`, `token`, `tool_start`, `tool_end` (+`summary`/`ms`), `tool_progress`, `grounding`,
`raid_tracked`, `encounters`, `suggestions`, `done`, `error` — all as today. A `create_chart` call still
also produces the normal `tool_start`/`tool_end` spell-card frames (it renders as a spell like any tool).

## Capture path (server)
On `create_chart` `tool_end`:
1. Validate the result's `chart` into a `ChartSpec`.
2. `services/charts.chart_spec_to_plotly(spec)` → `figure`.
3. `repo.add_artifact(session, conversation_id, kind, title, spec_json)` → `artifact_id`; commit
   (same immediate-commit discipline as raid/graph capture, so a later stream error can't lose it).
4. `await _send(ws, ArtifactFrame(...))`.

This rides the existing `_handle_tool_end` alongside raid capture, graph capture, and encounters — one
backbone, consistent with 004.
