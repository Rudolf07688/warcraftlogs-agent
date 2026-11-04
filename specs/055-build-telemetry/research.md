# Research: 055

## Mimir ruler, local storage
- Decision: `ruler_storage.backend: local`, `local.directory: /etc/mimir/rules`; rule files at `<dir>/<tenant>/<namespace>.yaml`; tenant `anonymous` (`-auth.no-auth-tenant` default, verified with `mimir:3.2.4 -help-all`); `ruler.rule_path: /data/ruler`; `ruler.poll_interval: 1m` so a pricing commit loads without a restart.
- Alternatives: object storage + mimirtool upload (needs a sync step, state outside git): rejected.

## Board tail into the redaction chain
- Decision: `local.file_match` (only `*.jsonl` in the mounted dir, so `cursors/` and `active` are skipped) → `loki.source.file` → `loki.process` (JSON fields to labels, entry `ts` as timestamp, body = entry text) → `otelcol.receiver.loki` → board transform (resource attributes, trace_id/span_id from traceparent) → `otelcol.processor.memory_limiter.default` (the shared chain). Never `loki.write`.
- Labels inside Alloy become OTLP log attributes, which Loki stores as structured metadata; index labels come only from the resource allowlist in loki.yaml.
- Backfill: Alloy keeps tail positions on its data volume; after Loki data loss, delete the board component's positions file with Alloy stopped and start it again.

## Spanmetrics and servicegraph
- Decision: `otelcol.connector.spanmetrics` with the §4.2 dimensions (plus the old-semconv `http.status_code` the 0.63b1 FastAPI instrumentation still emits), explicit buckets in seconds, exemplars on; `otelcol.connector.servicegraph` with the default client/server pairing. Both fed from the redact output (after redaction, before any sampling) and send into `metric_labels` (banned label drop) so the hygiene rule covers them too.
- Rejected: Tempo's metrics-generator (would need Tempo remote-write config and runs after Tempo ingest, not "before sampling").

## Pricing
- Decision: generated recording rules (see board scope:055:pricing).
