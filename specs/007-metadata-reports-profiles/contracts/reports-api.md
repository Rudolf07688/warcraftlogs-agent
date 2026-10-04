# Contract: Reports API — findings synthesis (US2/US3)

Base: `/api/conversations` (`backend/app/api/reports.py`). The **URLs, auth, response media type, and download behavior are unchanged** (FR-021). What changes is the PDF **body**: a synthesized findings document instead of the transcript.

## Endpoints (unchanged signatures)

### `GET /{conv_id}/report.pdf` — conversation findings report (US2)
- Still `200 application/pdf`, `Content-Disposition: attachment; filename="wcl-report-<id8>.pdf"`.
- Input slice unchanged: **all** messages + all captured graphs + all artifacts for the conversation; header title still prefers a `TrackedRaid.label` (FR-020).
- **New**: before rendering, the message slice is passed through `synthesize_findings(...)`; the returned findings markdown becomes the PDF body.

### `GET /{conv_id}/messages/{message_id}/report.pdf` — per-message findings report (US3)
- Still `200 application/pdf`, `filename="wcl-message-<id8>.pdf"`; `404 not_found` when the message isn't an agent reply of this conversation/tenant.
- Input slice unchanged: the one agent reply + nearest preceding user question (context) + only that reply's `message_seq`-matched graphs/artifacts (FR-015).
- **New**: synthesize findings from that reply (with the originating question as context), render as the body.

## Internal pipeline (shared — FR-016)

```
endpoint
  → build in-scope `messages` slice (as today)          # differs per endpoint
  → findings_md = await _synthesize_and_render(...)      # ONE shared helper
        ├─ md = await report_synthesis.synthesize_findings(messages, scope=..., question=...)
        │       (asyncio.wait_for(to_thread(genai generate), timeout=~60s))
        ├─ if md is empty/whitespace → md = NO_FINDINGS_DOC
        └─ return await _render(title=..., messages=[{role:"agent", content:md, status:"complete"}],
                                graphs=..., artifacts=..., ctx=...)
```

- `_render` is the **existing** fail-closed wrapper (`reports.py:81-93`) → `500 pdf_generation_failed` on any exception, timeout, or render error (FR-018). No partial file is ever returned.
- `render_report_pdf` is **unchanged**: it renders the single synthetic agent message's markdown as the body and attaches the graphs/artifacts exactly as today.

## `synthesize_findings` service contract (`backend/app/services/report_synthesis.py`)

```python
async def synthesize_findings(
    messages: list[dict],          # [{"role","content","status"}] in-scope slice
    *,
    scope: str,                    # "conversation" | "message" (prompt tuning only)
    question: str | None = None,   # originating user question for per-message scope
) -> str:                          # findings markdown ("" only if the model returns nothing)
```
- Model: `settings.wcl_report_model` (default `gemini-3.6-flash`); one-shot `genai` call via `asyncio.to_thread`, **no web search**.
- Prompt directs: extract **findings/discoveries** (what was learned: parses/percentiles, rankings, per-boss/per-player results, recommendations), organize by topic/encounter, **not** a transcript; if there are no substantive findings, say so briefly (FR-017).
- Input is char-capped (truncate oldest-first) to stay within model limits on long conversations (edge case).
- Output markdown MUST use only constructs the existing renderer supports (headings, GFM tables, bullet/numbered lists, `$…$`/`$$…$$` math) — FR-010 / renderer reuse.

## Config
- `wcl_report_model: str = "gemini-3.6-flash"` added to `Settings` (`backend/app/config.py`), overridable via env.

## Acceptance mapping
- FR-012 synthesis not transcript; FR-013 sections; FR-014 charts still attached (unchanged scoping); FR-015 per-message scope; FR-016 shared pipeline; FR-017 no-findings doc; FR-018 fail-closed; FR-019 off-loop + timeout; FR-020 title; FR-021 unchanged entry points (frontend untouched).
