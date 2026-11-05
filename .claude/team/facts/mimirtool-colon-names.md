---
id: mimirtool-colon-names
anchors: [file:observability/mimir/rules/anonymous/, file:observability/test/rules.sh, comp:mimir]
by: dev-1 Ansel, dev-3 Nils
source: meta/sprints/2026-11-04b/board.jsonl #58; meta/sprints/2026-11-05/board.jsonl #46
verified: b9cf9a3 2026-11-05
---
`mimirtool rules check` rejects record names without the `level:metric:operation` colons.
`cost.yaml`'s `llm_price_usd_per_token` and the Grafana-named service-graph copies in
`runtime.yaml` are deliberate exceptions. `rules.sh` lints only `build.yaml` and `red.yaml`
and proves cost.yaml loads and evaluates in Mimir. A new colon-less rule needs a comment
saying why.
