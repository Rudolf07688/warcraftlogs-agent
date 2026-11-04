# Quickstart: 054 backend telemetry

Tests (no network): `python3 .claude/team/check.py run backend/tests/test_telemetry_*.py --as nils`

Live (team-lead, stack from 053 up):
1. Backend with `OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4318`, `WCL_ENVIRONMENT=dev`.
2. Send one chat message that calls a WCL tool. In Grafana → Tempo, search `service.name=api`,
   span name `chat turn`: one trace with invoke_agent → generate_content/execute_tool → POST
   (WCL) → SQL → Redis spans.
3. Loki: `{service_name="api"}` → open a line's trace via its trace id.
4. Start a new conversation (title call): a `chat <model>` span with tokens; repeat on a
   Gemini and a Claude model.
5. With `WCL_ENVIRONMENT` unset, repeat 2: no gen_ai input/output messages on the spans and no
   content-stream records.
