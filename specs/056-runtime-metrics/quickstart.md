# Quickstart: 056

- Tests: `python3 .claude/team/check.py run backend/tests/test_telemetry_metrics.py --as nils`
- Rules lint: `docker run --rm -v $PWD/observability/mimir/rules/anonymous:/r grafana/mimirtool:<pinned> rules lint /r/runtime.yaml`
- Live (team-lead, merged tip): stack up, one chat turn with a knowledge search; Grafana → Explore Mimir: `gen_ai_client_token_usage`, `app_cache_requests`, `app_llm_stream_ttft`, `rag:retrieval_latency:p95`; open D6, D7, D8.
