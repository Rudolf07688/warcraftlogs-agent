# Data model: instruments, attributes, aliases

## Instruments (new)

| Name | Kind | Unit | Attributes | Defined in |
|---|---|---|---|---|
| `app.cache.requests` | counter | `{request}` | `app.cache.name` (CacheFamily value), `app.cache.result` (hit, miss, error) | `wcl_agent/cache/cache.py` |
| `app.rag.retrieval.duration` | histogram | s | `app.rag.index` (wcl, guide, chat, all), `app.rag.strategy` (hybrid, keyword_only, vector, keyword) | `backend/app/telemetry/metrics.py` |
| `app.rag.retrieved_chunks` | histogram | `{chunk}` | `app.rag.index` | metrics.py |
| `app.rag.top_score` | histogram | 1 | `app.rag.index` (only when hits > 0) | metrics.py |
| `app.rag.empty_results` | counter | `{search}` | `app.rag.index` | metrics.py |
| `app.llm.stream.ttft` | histogram | s | `gen_ai.request.model`, `gen_ai.agent.name` | metrics.py |

Result mapping (cache `Outcome` → `app.cache.result`): hit, neg_hit → hit; miss, lock_timeout, redis_error → miss; error → error.

## Allowlist additions (`setup.METRIC_ATTRIBUTES`)

`app.cache.name`, `app.cache.result`, `app.rag.index`, `app.rag.strategy`. Never `session.id`, `gen_ai.conversation.id` or any id.

## Recording rules (`observability/mimir/rules/anonymous/runtime.yaml`, group `runtime`)

| Alias | Expression (sketch) |
|---|---|
| `genai:tokens:rate5m` | `sum by (gen_ai_request_model, gen_ai_agent_name, gen_ai_token_type) (histogram_sum(rate(gen_ai_client_token_usage[5m])))` |
| `genai:invoke_agent_latency:p95` | `histogram_quantile(0.95, sum by (gen_ai_agent_name) (rate(gen_ai_invoke_agent_duration[5m])))` |
| `rag:retrieval_latency:p95` | `histogram_quantile(0.95, sum by (app_rag_index, app_rag_strategy) (rate(app_rag_retrieval_duration[5m])))` |
| `cache:hit_ratio` | hits / all of `app_cache_requests` by `app_cache_name`, 5m |

Further D7/D8 aliases as needed (same file, same naming): per-invocation calls, TTFT p95, chunks, top score, empty ratio.
