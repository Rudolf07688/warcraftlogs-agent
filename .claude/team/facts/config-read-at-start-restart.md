---
id: config-read-at-start-restart
anchors: [comp:alloy, comp:mimir, comp:grafana, comp:loki]
by: lead
source: lead memory; sprint 2026-11-04, 2026-11-05 live passes
verified: 32010a6 2026-11-05
---
Alloy, Mimir, Loki, Tempo and Grafana read their config at start. docker compose up -d --build
leaves them on the old config, so a live check after a config change must first run docker
compose restart for those services. Twice a check read stale config and gave a wrong verdict.
