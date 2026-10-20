# Contract: Report download endpoints (unchanged)

FR-018 says this feature must not change these endpoints in any way the frontend or the player can see. This file pins them down so the tests can hold the line.

## `GET /api/conversations/{conv_id}/report.pdf`

- **Auth**: session cookie (`require_session`) and tenant scoping. No change.
- **200**: `Content-Type: application/pdf` and `Content-Disposition: attachment; filename="wcl-report-{conv_id[:8]}.pdf"`. The body starts with `%PDF`.
- **404** `{"detail": "not_found"}`: the conversation is unknown or belongs to another tenant.
- **500** `{"detail": "pdf_generation_failed"}`: the findings rewrite failed, timed out or came back empty, **or rendering failed**. No partial body is sent.

## `GET /api/conversations/{conv_id}/messages/{message_id}/report.pdf`

- The same auth and response rules as above, with `filename="wcl-message-{message_id[:8]}.pdf"`.
- **404**: the message is unknown, belongs to another conversation, or is a user message.
- Content scope is unchanged: the target agent message, the user message just before it, and the graphs and artifacts with `message_seq == message.seq` (FR-021).

## What changes behind the endpoints

- The `_synthesize_and_render(...)` helper builds a `ReportDocument` (see data-model.md) and passes it to `render_report_pdf` through `asyncio.to_thread`.
- The per-message endpoint also passes `question` and `partial=(msg.status == "partial")`.
- One INFO log line is added on success, emitted by the renderer (`backend.app.services.pdf_report`), which knows the page count: `pdf rendered scope=<scope> pages=<n> figures=<n> ms=<render ms>`.

## Frontend

No change. `frontend/src/api/restClient.ts` (`/report.pdf` fetchers, lines ~236 and ~251) and the progress indicator from story 151 keep working as they are.
