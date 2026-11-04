# Research: 053 telemetry stack

## Content events routed to the 7-day stream
Claude Code puts the short name in log attribute `event.name` (monitoring docs). Content-bearing:
`user_prompt` (prompt), `assistant_response` (response), `tool_result` (tool_input, tool_parameters),
`tool_decision` (tool_parameters), `api_request_body`/`api_response_body` (raw bodies; wrapper
leaves them off). Tool output is a span event `tool.output` on traces (OTEL_LOG_TOOL_CONTENT),
so it lands in Tempo (7 days). GenAI semantic-convention events: any `event.name` starting
`gen_ai.`. Backend logs with content carry `app.content="true"` (054).

## Redaction engine
`otelcol.processor.redaction` is experimental in Alloy v1.21 and does not document span
events or resource attributes. `otelcol.processor.transform` (OTTL) covers every context:
`replace_all_patterns(attributes, "value", …)`, `replace_pattern(log.body, …)` and
`SHA256(…)` for known keys.

## Export queue
`sending_queue { storage = otelcol.storage.file.queue.handler, sizer = "bytes", queue_size = N }`
with `retry_on_failure { max_elapsed_time = "0s" }` (retry forever). `otelcol.storage.file`
is public preview: `--stability.level=public-preview`.

## Retention
Loki: compactor `retention_enabled`, `retention_period: 720h`, `retention_stream`
`{content="true"}` 168h. Tempo: `compactor.compaction.block_retention: 168h`. Mimir:
`compactor_blocks_retention_period: 9490h` (~13 months).
