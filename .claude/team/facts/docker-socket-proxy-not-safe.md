---
id: docker-socket-proxy-not-safe
anchors: [file:docker-compose.yml, comp:compose, comp:alloy]
by: dev-1 Ansel, po Maren
source: meta/team/dev-1.md L20; meta/team/po.md L35; meta/sprints/2026-11-05/board.jsonl #32, #61, #62
verified: 32010a6 2026-11-05
---
A "GET-only" Docker socket proxy (tecnativa, POST=0) still serves container archive/export
and `/containers/*/json`, which includes every container's env (DSNs). Since 058, Alloy has no
Docker access at all (the Postgres log comes from the `pglog` volume). Keep it that way:
Alloy parses browser (Faro) payloads. Mounting a socket `:ro` restricts nothing.
