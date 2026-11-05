---
id: adk-content-event-semconv
anchors: [file:backend/app/telemetry/policy.py, comp:alloy, comp:loki]
by: dev-3 Nils
source: meta/sprints/2026-11-04/board.jsonl #24
verified: b9cf9a3 2026-11-05
---
With `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` (set by `policy.py`), ADK 2.10
emits prompt and response content as the log event
`gen_ai.client.inference.operation.details` (with `gen_ai.input.messages`, `output.messages`,
`system_instructions` and `tool.definitions`) and on `generate_content` spans. The stable
semconv would emit `gen_ai.user.message`/`gen_ai.choice` instead. Alloy routes any
`^gen_ai\.` event to the content stream, so both land there.
