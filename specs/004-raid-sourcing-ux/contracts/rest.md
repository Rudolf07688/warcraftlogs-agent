# Contract: REST endpoints

One new endpoint (greeting) and one edited response body (`RaidOut`). Existing conversation,
raid, model, and report endpoints are otherwise unchanged.

## New: `GET /api/greeting`

Returns a cached, persona-consistent Barnaby greeting for new chats (US5).

**Query params**
- `model` (optional): model id to produce the greeting for. Defaults to the server's current
  default model when omitted.

**200 Response** — `GreetingResponse`:

```json
{ "greeting": "Ahh, welcome back to the tavern, friend! Pull up a stool…" }
```

Behavior:
- Served from the in-process `app.state.greeting_cache` (primed at startup for the default
  model); generated on cache miss by running the agent over a disposable session with the
  hidden `"Greetings, Barnaby!"` kickoff, then cached (FR-023).
- The hidden kickoff is **never** returned to the client — only Barnaby's greeting (FR-022).
- On generation failure, returns `{ "greeting": "" }` (or 204) so the client opens a clean
  empty chat rather than blocking (FR-024). Never 500s the new-chat flow.

**Client handling**: `newChat()` fetches this and injects the text as a **display-only** agent
message (no conversation row is created yet). If the user starts typing before it arrives, the
input wins and a late greeting is ignored.

## Edited: `GET /api/raids` — `RaidOut`

`RaidOut` gains an `encounters` array so the sidebar can show the raid's boss(es) (US2).
`report_started_at` is already present and is now the field the UI displays as the raid's
date/time.

```json
{
  "report_code": "aBcDeFgH",
  "label": "My Guild — Nerub-ar Palace — 2026-09-28",
  "zone": "Nerub-ar Palace",
  "guild": "My Guild",
  "report_started_at": "2026-09-28T19:32:00Z",
  "last_asked_at": "2026-10-02T14:10:00Z",
  "first_seen_at": "2026-09-28T20:05:00Z",
  "encounters": [
    { "encounter_id": 2902, "name": "Ulgrax the Devourer", "difficulty": 5, "kill": true }
  ]
}
```

- `encounters` defaults to `[]` for raids tracked before this field existed or captured via a
  non-fight tool.
- List ordering is unchanged (`last_asked_at desc`); the **displayed** timestamp changes to
  `report_started_at` (date + time, date-only fallback).

## Unchanged (recap)

`POST /api/raids/{report_code}/investigate`, `GET /api/conversations`,
`GET /api/conversations/{id}`, `DELETE /api/conversations/{id}`,
`GET /api/conversations/{id}/report.pdf` (behavior unchanged; **rendering fidelity** improves
per `agent-output.md`), `GET /api/models`, `/health`.
