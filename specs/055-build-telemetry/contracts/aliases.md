# Recording-rule aliases owned by 055 (tenant `anonymous`)

| File | Alias | Labels | Meaning |
|---|---|---|---|
| red.yaml | `app:http_requests:rate5m` | service_name, http_route, status_code | server-span calls per second; `status_code="STATUS_CODE_ERROR"` marks errors |
| red.yaml | `app:http_latency:p95` | service_name, http_route | p95 server-span duration (s); excludes `/ws/chat` and `.*/generate` |
| build.yaml | `cc:cost_usd:rate5m`, `cc:cost_usd:rate1h` | model, agent_name | Claude Code reported cost, USD/s |
| build.yaml | `cc:tokens:rate5m` | model, type, agent_name | tokens/s |
| build.yaml | `cc:cache_hit_ratio` | (none) | cacheRead / all tokens, 5m |
| build.yaml | `cc:sessions:rate5m`, `cc:commits:rate5m`, `cc:pull_requests:rate5m` | (none) | per second |
| build.yaml | `cc:active_time_seconds:rate5m` | type | active seconds per second |
| build.yaml | `cc:lines_of_code:rate5m` | type | lines/s |
| build.yaml | `cc:edit_decisions:rate5m` | decision, language | decisions/s |
| cost.yaml | `llm_price_usd_per_token` | gen_ai_request_model, gen_ai_token_type | list price, generated from pricing.yaml |
| cost.yaml | `genai:cost_usd:rate5m` | gen_ai_request_model, gen_ai_agent_name | runtime LLM cost, USD/s |

Range totals: `sum_over_time(<alias>[$__range]) * 60` (rules evaluate every 1 m).
