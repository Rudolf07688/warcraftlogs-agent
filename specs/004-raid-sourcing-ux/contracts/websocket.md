# Contract: WebSocket frames (`/ws/chat`)

**Transport decision (US6):** the app keeps its **WebSocket** frame protocol — no SSE migration.
The spellcasting/streaming UI is driven by these frames (see `ui-polish.md` for the mapping).

This feature adds **one** new frame (`encounters`), **extends** `tool_end` with optional
`summary`/`ms`, and adds **one optional** frame (`tool_progress`). All other existing frames
(`meta`, `token`, `tool_start`, `grounding`, `raid_tracked`, `suggestions`, `done`, `error`)
are unchanged and remain in the `Frame` union.

## Edited: `tool_end` (server → client)

Gains two optional fields to drive resolved spell chips (US6/FR-032):

```json
{ "type": "tool_end", "name": "get_report_table", "ok": true,
  "summary": "DamageDone — 23 abilities for 1 player", "ms": 812 }
```

- `summary` ≤ 140 chars, human-readable, produced server-side from the tool result.
- `ms` is the tool call's elapsed duration.
- Both optional/additive — clients that ignore them still work.

## New (optional): `tool_progress` (server → client)

Emitted only by tools that can report progress, to upgrade a cast bar from indeterminate to
determinate:

```json
{ "type": "tool_progress", "id": "call_abc", "done": 2, "total": 5, "note": "page 2/5" }
```

## New: `encounters` (server → client)

Emitted from `_handle_tool_end` immediately after the `tool_end` frame for a **successful**
`get_report_fights` call, when the report has at least one distinct, non-trash encounter (US4).

```json
{
  "type": "encounters",
  "report_code": "aBcDeFgH",
  "encounters": [
    { "encounter_id": 2902, "name": "Ulgrax the Devourer", "difficulty": 5, "kill": true },
    { "encounter_id": 2917, "name": "Sikran",              "difficulty": 5, "kill": false }
  ]
}
```

Rules:
- `encounters` is **deduped by `encounter_id`**; repeated pulls of the same boss appear once.
- Trash pulls / entries with a null `encounterID` are excluded.
- `kill` is `true` if any pull of that encounter was a kill.
- Omitted entirely when there are no qualifying encounters (never send an empty list).
- The frame is additive; clients that ignore it continue to work.

### Client handling (frontend)

- Attach the encounters to the agent turn that surfaced them and render an `EncounterPicker`
  (checkbox group) beneath that message.
- Selecting bosses folds their names into the **next** user message text (visible), e.g. the
  composed prompt gains a trailing `(Focus on: Ulgrax the Devourer, Sikran)`.
- Selection state resets per turn (no stale reapplication — FR-020).

## Ordering within a turn (unchanged, for reference)

`meta` → (`tool_start` / `tool_progress`? / `tool_end` / **`encounters`** / `grounding` /
`token` …)* → optional `suggestions` → `done`. On failure: `error` instead of `done`.
