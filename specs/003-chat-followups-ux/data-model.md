# Phase 1 Data Model: Chat Follow-ups & UX Enhancements

This feature adds no new database tables. It introduces one new stream payload, one
transient filesystem structure, and two client-side preferences. Persistent DB entities
(conversations, messages, raids, ADK sessions) are unchanged.

## Entities

### FollowUpSuggestion (transient, per turn)

A short natural-language question the agent predicts the user may ask next.

| Field | Type | Rules |
|-------|------|-------|
| text | string | 1–120 chars (display truncates longer; full text is submitted on click). Non-empty. |

- Produced as an ordered `list[FollowUpSuggestion]` of length **0–3** per agent turn.
- De-duplicated (case-insensitive) and trimmed; empty list means "show no buttons".
- Associated with exactly one agent turn; never carried onto a later turn (FR-005).
- **Not persisted** in MVP (live-only; see research R1). Carried over the wire in the
  `SuggestionsFrame` and held in frontend state on the latest agent `Message`.

### SuggestionsFrame (WebSocket, server → client)

New typed frame emitted once per turn, immediately before `DoneFrame`, when ≥1 suggestion
exists. Omitted entirely when the list is empty.

| Field | Type | Rules |
|-------|------|-------|
| type | literal `"suggestions"` | discriminator |
| suggestions | `list[str]` | length 0–3, each 1–120 chars |

### ToolCallResult + TurnScratch (transient, per turn)

The complete output of one tool call within a turn, plus the shared per-turn scratch space
that holds large outputs for reliable handoff.

| Field | Type | Rules |
|-------|------|-------|
| turn_id | string | the conversation/turn correlation key for the scratch dir |
| call_id | string | ADK function-call id; correlates `function_call` ↔ `function_response` (reuses existing `pending_args`) |
| name | string | tool name |
| ok | bool | `result["status"] == "success"` |
| result | dict / file | full payload; large payloads stored on disk in the turn scratch dir and read back by `call_id` |

- **Lifecycle**: the scratch dir is created at turn start and removed at turn end (success,
  error, or disconnect). No cross-turn persistence.
- **Guarantees**: every successful tool's full result is readable by the WS capture
  services and the agent before the answer is composed (FR-007); large results are not
  truncated (FR-008); a failed tool yields an error-shaped result and does not abort the
  turn (FR-009).

### UIPreference (client-side, `localStorage`)

User presentation settings persisted per browser; no server involvement.

| Key | Type | Rules / Default |
|-----|------|-----------------|
| sidebarWidth | number (px) | clamped to [MIN, MAX] (e.g. 200–480); default 260 |
| background | string (id) | one of the configured background ids; default = new image (`morgan-howell-img-1760`) |

### BackgroundOption (client config)

Static registry in `frontend/src/config.ts` describing selectable backgrounds.

| Field | Type | Rules |
|-------|------|-------|
| id | string | stable key stored in `UIPreference.background` |
| label | string | human label for the toggle |
| src | string | asset URL (from source assets, not `dist/`); may be empty for "solid color" |
| default | bool | exactly one option is the default (the new image) |

## Relationships

- An **Agent turn** has 0–3 **FollowUpSuggestion**s (delivered via one `SuggestionsFrame`)
  and 0–N **ToolCallResult**s (held in one **TurnScratch**).
- **UIPreference.background** references one **BackgroundOption.id**.

## Validation summary (maps to FRs)

- ≤3 suggestions enforced server-side before emit (FR-002); empty → no frame (FR-004).
- Suggestions tied to the current turn in frontend state, cleared on new turn (FR-005).
- Scratch results keyed by `call_id`; completeness + large-output + partial-failure rules
  (FR-007/008/009).
- `sidebarWidth` clamped (FR-018); persisted + restored (FR-017).
- Exactly one default background; legibility scrim always applied; load-failure → solid
  fallback (FR-019/020/021).
