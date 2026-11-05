---
id: servicegraph-virtual-server-latency
anchors: [file:observability/mimir/rules/anonymous/runtime.yaml, comp:alloy]
by: dev-1 Ansel
verified: 32010a6 2026-11-05
---
Alloy's servicegraph connector records server latency 0 for a virtual_node edge with a real
client (api -> redis: no server spans), so Grafana's node average (server_seconds_sum /
request_total over the edges into the node) reads 0.00 ms/r. The runtime.yaml copy takes
client_* for those edges. A virtual client is always named 'user' and keeps its real server
side. Database edges (db.name, connection_type database) get real server latency. Grafana's
math: graphTransform.ts in the tempo plugin's module.js.map inside the Grafana image.
