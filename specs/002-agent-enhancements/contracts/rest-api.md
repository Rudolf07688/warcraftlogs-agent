# REST API Contract — Agent App Enhancements (delta over 001)

Base URL (local): `http://localhost:8000`. Only new/changed endpoints are listed;
`001`'s `/api/conversations*` endpoints are unchanged.

## GET /api/models  *(changed — US4)*

Serve the **validated** model set computed at startup (research §5). No longer a static
config echo.

**200 Response**

```json
{
  "models": ["gemini-3.6-flash", "gemini-3.6-flash", "claude-sonnet-4@vertex"],
  "default": "gemini-3.6-flash",
  "degraded": false
}
```

- `models`: model ids that passed the startup responsiveness probe.
- `default`: the configured default if it passed, else the first validated model.
- `degraded` (new): `true` when discovery/validation could not run and a fallback
  default set is being served (FR-016) — the UI shows a notice. Never returns an empty
  `models` array.

## GET /api/raids  *(new — US1)*

List tracked raids, most-recently-asked first (FR-003).

**200 Response**

```json
{
  "raids": [
    {
      "report_code": "aBcD1234wXyZ",
      "label": "My Guild — Liberation of Undermine — 2026-09-28",
      "zone": "Liberation of Undermine",
      "guild": "My Guild",
      "report_started_at": "2026-09-28T19:02:00Z",
      "last_asked_at": "2026-10-01T18:40:11Z",
      "first_seen_at": "2026-09-29T20:10:00Z"
    }
  ]
}
```

- Ordered by `last_asked_at` DESC. Empty list → `{"raids": []}`.

## POST /api/raids/{report_code}/investigate  *(new — US1 / FR-004)*

Start a **new conversation** that auto-investigates the given raid. The server creates
the (empty) conversation and returns the ids plus the server-owned kickoff prompt. It
does **not** persist any message — the client then sends the kickoff as a normal first
turn over the WebSocket, which persists it exactly like any other turn (no special-case
idempotency needed).

**Request body**

```json
{ "model": "gemini-3.6-flash" }
```

- `model` optional; defaults to the server default model if omitted. Validated against
  the startup model set (400 `invalid_model` otherwise).

**201 Response**

```json
{
  "conversation_id": "7b1f…",
  "model": "gemini-3.6-flash",
  "kickoff_prompt": "Please investigate this raid (report aBcD1234wXyZ) and highlight any important findings."
}
```

**Client flow**: on 201, open/ensure the WS, then send a `ChatTurn`
(`conversation_id`, `model`, `content = kickoff_prompt`). The WS handler persists this
first user message and streams the response through the normal path — there is no
pre-persisted message and therefore no double-persist case to guard against.

> Design note: the server owns the exact kickoff wording (one source of truth) and the
> report-code→prompt mapping, so the frontend never hardcodes the prompt. The
> conversation is created empty so the standard turn path handles persistence.

**Errors**: `404 not_found` (unknown report_code), `400 invalid_model`.

## GET /api/conversations/{id}/report.pdf  *(new — US5)*

Generate and download a PDF for the conversation: header (raid label + generation
date), the agent's written analysis, and captured graphs rendered as charts
(FR-017–019). Runs rendering off the event loop.

**200 Response**

- `Content-Type: application/pdf`
- `Content-Disposition: attachment; filename="wcl-report-<short-id>.pdf"`
- Body: the PDF bytes (streamed).

**Behavior**

- No captured graphs → analysis-only PDF still generated (edge case).
- `404 not_found` if the conversation doesn't exist.
- `500` with `{"detail": "pdf_generation_failed"}` on render failure (FR-020); the
  client shows a clear error and remains usable (no partial file presented as complete).

## Validation & conventions (unchanged from 001)

- All bodies are typed Pydantic models; invalid input → `422`.
- Single-user, no auth; CORS restricted to the configured frontend origin.
- Timestamps are ISO-8601 UTC.
