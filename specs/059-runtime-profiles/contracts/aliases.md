# Contract: 059 recording-rule aliases (runtime.yaml)

| Alias | Meaning | Panel |
|---|---|---|
| `app:http_latency:p50`, `app:http_latency:p99` | as `app:http_latency:p95` (red.yaml), same exclusions | D6 |
| `genai:finish_reasons:rate5m` | responses/s by `gen_ai_request_model`, `app_llm_finish_reason` | D7 |
| `genai:turns_per_conversation:p50`, `:p95` | depth quantiles by `gen_ai_agent_name` | D7 |
| `rag:embedding_latency:p95` | by `gen_ai_request_model`, `app_embedding_task` | D8 |
| `rag:embedding_batch_size:avg5m` | texts per request, same labels | D8 |

Service graph: Grafana's Tempo service map reads `traces_service_graph_request_total`, `..._failed_total`, `..._server_seconds` / `..._client_seconds` from the `serviceMap` datasource directly (fixed names; no alias possible).
