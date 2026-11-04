# Quickstart: 056

- Tests: `python3 .claude/team/check.py run backend/tests/test_telemetry_metrics.py --as nils`
- Rules: `docker run --rm -v $PWD/observability/mimir/rules/anonymous:/r:ro grafana/mimirtool:3.2.4 rules check /r/runtime.yaml` and `docker run --rm -v $PWD:/w -w /w --entrypoint promtool prom/prometheus:v3.5.0 test rules specs/056-runtime-metrics/rules-test/runtime_test.yaml`
- Live (team-lead, merged tip): stack up, one chat turn with a knowledge search; Grafana → Explore Mimir: `gen_ai_client_token_usage`, `app_cache_requests`, `app_llm_stream_ttft`, `rag:retrieval_latency:p95`; open D6, D7, D8.
