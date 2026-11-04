# Quickstart: 055 proofs

Each script starts its own compose project, runs its checks, prints `RESULT PASS|FAIL`, and
removes the project with its volumes (KEEP=1 keeps it). Ansel's runs use:

    export COMPOSE_PROJECT=wcl-obs-ansel ALLOY_OTLP_GRPC_PORT=25317 ALLOY_OTLP_HTTP_PORT=25318 ALLOY_UI_PORT=25345 GRAFANA_PORT=25000

- `observability/test/board.sh`: entries in Loki with trace ids and allowlisted labels, seeded secret masked, backfill after Loki data loss.
- `observability/test/red.sh`: spanmetrics/servicegraph series, exemplars, no id labels, RED aliases.
- `observability/test/rules.sh`: rule files load, `cc:*` and cost aliases evaluate; cost arithmetic for one Claude and one Gemini model.
- `observability/test/dashboards.sh`: D1/D2 provision; every metric panel uses an alias.
- Unit tests: `python3 .claude/team/check.py run backend/tests/test_team_board.py backend/tests/test_team_teamstats.py backend/tests/test_team_pricing.py --as ansel`.
